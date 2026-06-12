"""
RAG 流式问答路由 — SSE 协议（升级版：集成 graphrag 模块的完整管线）。

POST /api/chat          —— 主问答流式接口（SSE）
POST /api/chat/retrieve —— 纯检索（调试/预览用）
POST /api/chat/legacy   —— 旧版简易 RAG（实体链接 + 子图扩展，无规划/证据评估）
"""
import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..schemas import ChatRequest, ChatRetrieveResponse, GraphPayload
from ..services.retrieval import entity_linking, subgraph_expand, serialize_context
from ..services.llm import stream_chat, is_available
from ..services.prompt import (
    SYSTEM_PROMPT,
    build_user_message,
    parse_citations,
    build_pinned_summaries,
    build_context_block,
)
from ..settings import (
    LLM_API_KEY,
    GRAPHRAG_MAX_SUBQUESTIONS,
    GRAPHRAG_EVENT_LIMIT_PER_SUB,
    GRAPHRAG_MAX_ITERATIONS,
    GRAPHRAG_RELATED_EVENT_LIMIT,
    GRAPHRAG_PARALLEL_WORKERS,
)

router = APIRouter(prefix="/api/chat")

# ── 简易内存会话存储 ──
_sessions: dict[str, list[dict]] = {}

# ── 线程池（用于同步 GraphRAG 管线） ──
_pipeline_executor = ThreadPoolExecutor(max_workers=3)


def _get_or_create_session(session_id: str | None) -> str:
    if session_id and session_id in _sessions:
        return session_id
    new_id = session_id or uuid.uuid4().hex[:12]
    if new_id not in _sessions:
        _sessions[new_id] = []
    return new_id


def _load_pinned_node_details(pinned_ids: list[str]) -> list[dict]:
    """加载上下文篮中节点的完整信息用于摘要。"""
    if not pinned_ids:
        return []
    from ..db import execute_read

    results = []
    for nid in pinned_ids:
        query = """
        MATCH (n) WHERE n.event_id = $nid OR n.entity_id = $nid
        RETURN n LIMIT 1
        """
        recs = execute_read(query, {"nid": nid})
        if recs:
            node = recs[0]["n"]
            from ..services.shaper import _node_id, _node_label
            from ..config import CLASS_CN
            n_id, n_kind = _node_id(node)
            label = _node_label(node)
            results.append({
                "id": n_id,
                "name": node.get("name", ""),
                "label": label,
                "type_cn": CLASS_CN.get(label, label),
            })
    return results


# ── GraphRAG 管线辅助函数 ──

TASK_TYPE_LABELS = {
    "event_overview": "事件综述",
    "timeline": "时间线问答",
    "entity_aggregation": "实体聚合",
    "attribute_lookup": "属性查找",
    "graph_qa": "图谱问答",
    "overview": "主题概览",
}


def _task_type_label(task_type):
    return TASK_TYPE_LABELS.get(task_type, task_type or "图谱问答")


def _support_level_priority(level):
    mapping = {"direct": 3, "indirect": 2, "background": 1}
    return mapping.get((level or "").strip().lower(), 0)


def _collect_support_rows(index, result, limit=8):
    """从管线结果中提取支撑事件行。"""
    best_by_event = {}
    events = index.get("events", {})
    entries = index.get("entries", {})

    for unit in result.retrieved_units:
        for assessment in unit.evidence_assessments:
            if not assessment.keep:
                continue
            priority = _support_level_priority(assessment.support_level)
            if priority <= 0:
                continue
            event_id = assessment.event_id
            score = (priority, float(assessment.relevance or 0.0), float(assessment.necessity or 0.0))
            prev = best_by_event.get(event_id)
            if prev and prev["score"] >= score:
                continue

            event = events.get(event_id, {})
            doc = entries.get(event.get("doc_id", ""), {})
            slot_texts = []
            for key, values in (assessment.slots or {}).items():
                if not values:
                    continue
                slot_texts.append(f"{key}: {'、'.join(values[:2])}")
                if len(slot_texts) >= 2:
                    break
            reason = (assessment.reason or "").strip()
            if not reason and assessment.claims:
                reason = "；".join(assessment.claims[:2])
            best_by_event[event_id] = {
                "score": score,
                "event_id": event_id,
                "event_name": event.get("name", event_id),
                "event_date": event.get("date_text", ""),
                "document_title": doc.get("title", ""),
                "support_level": assessment.support_level,
                "reason": reason or "该事件与问题约束匹配，并提供了直接图谱证据。",
                "slot_summary": "；".join(slot_texts),
            }

    rows = sorted(best_by_event.values(), key=lambda item: item["score"], reverse=True)
    return rows[:limit]


def _build_logic_lines(result, support_rows):
    """生成 '答案是如何从图谱中得到的' 中文说明。"""
    constraints = []
    if result.plan.time_hints:
        constraints.append("时间：" + "、".join(result.plan.time_hints[:3]))
    if result.plan.place_hints:
        constraints.append("地点：" + "、".join(result.plan.place_hints[:3]))
    if result.plan.entity_hints:
        constraints.append("主体：" + "、".join(result.plan.entity_hints[:4]))
    if result.plan.relation_hints:
        constraints.append("关系：" + "、".join(result.plan.relation_hints[:4]))

    lines = []
    task_label = _task_type_label(result.plan.task_type)
    lines.append(
        "1. 系统先把问题识别为“" + task_label + "”，并在图谱中锁定相关约束。"
    )
    if constraints:
        lines.append("2. 本次优先使用的图谱约束是：" + "；".join(constraints) + "。")
    else:
        lines.append("2. 本次主要围绕问题中的核心人物、地点、时期和关系在线索图谱中检索。")

    if support_rows:
        event_names = "、".join(row["event_name"] for row in support_rows[:3])
        lines.append(f"3. 系统最终保留了 {len(support_rows)} 个核心支撑事件，答案主要依据这些事件生成，例如：{event_names}。")
    else:
        lines.append("3. 本次没有找到足够强的支撑事件，因此答案会更保守。")
    return lines


def _run_graphrag_pipeline(question: str):
    """在独立线程中运行 GraphRAG 管线。"""
    from ..services.graphrag_index import get_graphrag_index
    from ..graphrag import GraphRAGConfig, run_pipeline

    index = get_graphrag_index()
    # 不传 driver（管线内部不需要），用 index 检索
    # 传入空字符串作为 driver 占位
    config = GraphRAGConfig(
        max_subquestions=GRAPHRAG_MAX_SUBQUESTIONS,
        event_limit_per_subquestion=GRAPHRAG_EVENT_LIMIT_PER_SUB,
        max_iterations=GRAPHRAG_MAX_ITERATIONS,
        related_event_limit=GRAPHRAG_RELATED_EVENT_LIMIT,
        parallel_workers=GRAPHRAG_PARALLEL_WORKERS,
        use_llm_decomposition=bool(LLM_API_KEY),
        use_llm_reflection=bool(LLM_API_KEY),
        use_llm_answer=False,   # 用守宇系统的流式 LLM 来生成答案
        use_llm_verification=False,
    )
    result = run_pipeline(index, None, question, LLM_API_KEY or "", config)
    return result


# ────────────────────────── POST /api/chat (SSE) ──────────────────────────
@router.post("")
async def chat(request: Request, body: ChatRequest):
    """
    RAG 流式问答（升级版），返回 SSE 事件流。

    事件序列：
      session → plan → retrieval → evidence → support_graph → token... → citation → done
    """
    session_id = _get_or_create_session(body.sessionId)
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    if len(question) > 2000:
        raise HTTPException(status_code=400, detail="问题长度超过限制（2000字）")

    async def event_stream():
        t0 = time.time()

        # ── ① 快速检索（立即返回，不阻塞）──
        seeds = entity_linking(question)
        seed_ids = [s["id"] for s in seeds]
        pinned_ids = body.pinnedNodeIds or []
        for pid in pinned_ids:
            if pid not in seed_ids:
                seed_ids.append(pid)

        hops = body.options.get("hops", 1) if body.options else 1
        topk = body.options.get("retrieveTopK", 40) if body.options else 40
        simple_result = subgraph_expand(seed_ids, hops=hops, topk=topk)
        simple_graph = simple_result["graph"]
        context_text = simple_result.get("context", "")

        # 立即发送 session + retrieval，前端秒显图谱
        yield f"event: session\ndata: {json.dumps({'sessionId': session_id})}\n\n"

        took_ms = int((time.time() - t0) * 1000)
        retrieval_data = {
            "graph": simple_graph,
            "seedIds": seed_ids,
            "tookMs": took_ms,
        }
        yield f"event: retrieval\ndata: {json.dumps(retrieval_data, ensure_ascii=False)}\n\n"

        # ── ② 后台启动 GraphRAG 管线（不阻塞 LLM）──
        loop = asyncio.get_event_loop()
        pipeline_future = loop.run_in_executor(
            _pipeline_executor, _run_graphrag_pipeline, question
        )

        # ── ③ 组装消息并流式调用 LLM（与管线并行）──
        allowed_ids = [n["id"] for n in simple_graph["nodes"]]
        pinned_details = _load_pinned_node_details(pinned_ids)
        pinned_summaries = build_pinned_summaries(pinned_details)

        user_message = build_user_message(
            question=question,
            serialized_subgraph=context_text,
            allowed_ids=allowed_ids,
            pinned_summaries=pinned_summaries,
        )

        history = body.history[-12:] if body.history else []
        messages = []
        for h in history:
            messages.append({"role": h.role, "content": h.content})
        messages.append({"role": "user", "content": user_message})

        _sessions[session_id].append({"role": "user", "content": question})

        full_text = ""
        all_citations = []

        if is_available():
            async for event in stream_chat(messages, system=SYSTEM_PROMPT):
                if event["type"] == "token":
                    full_text += event["text"]
                    yield f"event: token\ndata: {json.dumps({'text': event['text']}, ensure_ascii=False)}\n\n"
                elif event["type"] == "done":
                    citations = parse_citations(full_text, allowed_ids)
                    all_citations = citations
                    for c in citations:
                        yield f"event: citation\ndata: {json.dumps(c, ensure_ascii=False)}\n\n"

                    done_data = {
                        'usage': event.get('usage', {}),
                        'citations': citations,
                        'finishReason': event.get('finishReason', 'stop'),
                    }
                    yield f"event: done\ndata: {json.dumps(done_data, ensure_ascii=False)}\n\n"

                    _sessions[session_id].append({
                        "role": "assistant",
                        "content": full_text,
                        "citations": citations,
                    })
                elif event["type"] == "error":
                    yield f"event: error\ndata: {json.dumps({'code': 'LLM_ERROR', 'message': event['message']}, ensure_ascii=False)}\n\n"
        else:
            fallback = f"（LLM 未配置）\n\n共找到 {len(simple_graph['nodes'])} 个相关节点。\n\n{context_text[:500]}"
            for ch in fallback:
                yield f"event: token\ndata: {json.dumps({'text': ch}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'usage': {}, 'citations': [], 'finishReason': 'stop'}, ensure_ascii=False)}\n\n"
            _sessions[session_id].append({"role": "assistant", "content": fallback, "citations": []})

        # ── ④ 管线完成后记日志（不影响前端流）──
        async def _handle_pipeline():
            try:
                result = await pipeline_future
                if result:
                    from ..services.graphrag_index import get_graphrag_index
                    idx = get_graphrag_index()
                    rows = _collect_support_rows(idx, result)
                    print(f"[chat] GraphRAG 管线完成: {len(rows)} 个支撑事件")
            except Exception as e:
                print(f"[chat] GraphRAG 管线失败: {e}")

        asyncio.create_task(_handle_pipeline())

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────── POST /api/chat/retrieve（纯检索） ───────────────────
@router.post("/retrieve", response_model=ChatRetrieveResponse)
async def chat_retrieve(body: ChatRequest):
    """增强版纯检索：运行完整 GraphRAG 管线但跳过 LLM 回答，返回管线检索结果。"""
    seeds = entity_linking(body.question)
    seed_ids = [s["id"] for s in seeds]

    pinned_ids = body.pinnedNodeIds or []
    for pid in pinned_ids:
        if pid not in seed_ids:
            seed_ids.append(pid)

    t0 = time.time()

    # 简易检索（快速获取基础子图）
    hops = body.options.get("hops", 1) if body.options else 1
    topk = body.options.get("retrieveTopK", 40) if body.options else 40
    simple_result = subgraph_expand(seed_ids, hops=hops, topk=topk)

    # 尝试运行完整管线
    pipeline_ok = False
    plan_data = None
    support_rows = []

    try:
        loop = asyncio.get_event_loop()
        pipeline_result = await loop.run_in_executor(
            _pipeline_executor, _run_graphrag_pipeline, body.question
        )
        pipeline_ok = True

        from ..services.graphrag_index import get_graphrag_index
        idx = get_graphrag_index()

        support_rows = _collect_support_rows(idx, pipeline_result)

        plan = pipeline_result.plan
        plan_data = {
            "taskType": plan.task_type,
            "taskTypeCn": _task_type_label(plan.task_type),
            "timeHints": plan.time_hints,
            "placeHints": plan.place_hints,
            "entityHints": plan.entity_hints,
            "relationHints": plan.relation_hints,
            "subquestions": [sq.text for sq in plan.subquestions],
        }

    except Exception as e:
        print(f"[chat/retrieve] 管线失败: {e}")

    took_ms = int((time.time() - t0) * 1000)

    meta = {
        "pipelineOk": pipeline_ok,
        "plan": plan_data,
        "supportRows": support_rows,
    }

    return ChatRetrieveResponse(
        graph=GraphPayload(
            nodes=simple_result["graph"]["nodes"],
            edges=simple_result["graph"]["edges"],
            meta=meta,
        ),
        seeds=seed_ids,
        contextText=simple_result.get("context", ""),
        tookMs=took_ms,
    )


# ─────────────────── POST /api/chat/legacy（旧版简易 RAG） ──────────────────
@router.post("/legacy")
async def chat_legacy(request: Request, body: ChatRequest):
    """
    旧版简易 RAG（不使用 GraphRAG 管线），保留用于对比测试。
    事件序列：session → retrieval → token... → citation → done
    """
    session_id = _get_or_create_session(body.sessionId)
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    async def event_stream():
        seeds = entity_linking(question)
        seed_ids = [s["id"] for s in seeds]

        pinned_ids = body.pinnedNodeIds or []
        for pid in pinned_ids:
            if pid not in seed_ids:
                seed_ids.append(pid)

        t0 = time.time()
        hops = body.options.get("hops", 1) if body.options else 1
        topk = body.options.get("retrieveTopK", 40) if body.options else 40
        result = subgraph_expand(seed_ids, hops=hops, topk=topk)

        took_ms = int((time.time() - t0) * 1000)
        graph = result["graph"]
        context_text = result.get("context", "")

        yield f"event: retrieval\ndata: {json.dumps({'graph': graph, 'seedIds': seed_ids, 'tookMs': took_ms}, ensure_ascii=False)}\n\n"
        yield f"event: session\ndata: {json.dumps({'sessionId': session_id})}\n\n"

        allowed_ids = [n["id"] for n in graph["nodes"]]
        pinned_details = _load_pinned_node_details(pinned_ids)
        pinned_summaries = build_pinned_summaries(pinned_details)

        user_message = build_user_message(
            question=question,
            serialized_subgraph=context_text,
            allowed_ids=allowed_ids,
            pinned_summaries=pinned_summaries,
        )

        history = body.history[-12:] if body.history else []
        messages = []
        for h in history:
            messages.append({"role": h.role, "content": h.content})
        messages.append({"role": "user", "content": user_message})

        _sessions[session_id].append({"role": "user", "content": question})

        full_text = ""
        if is_available():
            async for event in stream_chat(messages, system=SYSTEM_PROMPT):
                if event["type"] == "token":
                    full_text += event["text"]
                    yield f"event: token\ndata: {json.dumps({'text': event['text']}, ensure_ascii=False)}\n\n"
                elif event["type"] == "done":
                    citations = parse_citations(full_text, allowed_ids)
                    for c in citations:
                        yield f"event: citation\ndata: {json.dumps(c, ensure_ascii=False)}\n\n"
                    done_data = {
                        'usage': event.get('usage', {}),
                        'citations': citations,
                        'finishReason': event.get('finishReason', 'stop'),
                    }
                    yield f"event: done\ndata: {json.dumps(done_data, ensure_ascii=False)}\n\n"
                    _sessions[session_id].append({
                        "role": "assistant",
                        "content": full_text,
                        "citations": citations,
                    })
                elif event["type"] == "error":
                    yield f"event: error\ndata: {json.dumps({'code': 'LLM_ERROR', 'message': event['message']}, ensure_ascii=False)}\n\n"
        else:
            fallback = f"（LLM 未配置）\n\n共找到 {len(graph['nodes'])} 个相关节点。\n\n{context_text[:500]}"
            for ch in fallback:
                yield f"event: token\ndata: {json.dumps({'text': ch}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'usage': {}, 'citations': [], 'finishReason': 'stop'}, ensure_ascii=False)}\n\n"
            _sessions[session_id].append({"role": "assistant", "content": fallback, "citations": []})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─────────────────── POST /api/chat/graphrag（全流程流式观察） ───────────────────
@router.post("/graphrag")
async def chat_graphrag(body: ChatRequest):
    """
    GraphRAG 全流程 SSE 流式端点，展示每一步内部细节。
    """
    import asyncio as _asyncio

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    # ── 处理上下文：pinned 节点 + 对话历史 ──
    pinned_ids = body.pinnedNodeIds or []
    history = body.history or []

    # 从索引中查找 pinned 节点的名称，作为额外种子查询
    pinned_names: list[str] = []
    if pinned_ids:
        try:
            from ..services.graphrag_index import get_graphrag_index
            idx = get_graphrag_index()
            for pid in pinned_ids:
                meta = idx.node_meta.get(pid, {})
                name = meta.get("label", "")
                if name and name not in pinned_names:
                    pinned_names.append(name)
        except Exception:
            pass

    # 构建增强问题：含上下文信息
    enhanced_question = question
    if pinned_names:
        enhanced_question = f"{question}\n[上下文：用户已将以下节点加入上下文篮：{', '.join(pinned_names[:8])}]"
    if history:
        # 取最近 3 轮对话作为上下文
        recent = history[-6:]
        history_text = "\n".join(
            f"{'用户' if h.role == 'user' else '助手'}: {h.content[:200]}"
            for h in recent
        )
        if history_text:
            enhanced_question = f"{enhanced_question}\n[对话历史：\n{history_text}\n]"

    # 线程安全事件列表 + 轮询（避免 asyncio.Queue 跨线程问题）
    events: list = []
    import threading as _threading
    lock = _threading.Lock()
    main_loop = _asyncio.get_event_loop()

    def _run():
        def cb(evt: str, data: dict):
            with lock:
                events.append((evt, data))

        try:
            from ..services.graphrag_index import get_graphrag_index
            from ..graphrag import GraphRAGConfig, run_pipeline

            index = get_graphrag_index()
            config = GraphRAGConfig(
                max_subquestions=GRAPHRAG_MAX_SUBQUESTIONS,
                event_limit_per_subquestion=GRAPHRAG_EVENT_LIMIT_PER_SUB,
                max_iterations=GRAPHRAG_MAX_ITERATIONS,
                related_event_limit=GRAPHRAG_RELATED_EVENT_LIMIT,
                parallel_workers=1,
                use_llm_decomposition=bool(LLM_API_KEY),
                use_llm_relation_prune=bool(LLM_API_KEY),
                use_llm_evidence_scoring=bool(LLM_API_KEY),
                use_llm_reflection=bool(LLM_API_KEY),
                use_llm_answer=True,
                use_llm_verification=True,
            )
            result = run_pipeline(index, None, enhanced_question, LLM_API_KEY or "", config, event_callback=cb)
            with lock:
                events.append(("_result", result))
        except Exception as e:
            import traceback
            with lock:
                events.append(("error", {"message": str(e), "trace": traceback.format_exc()}))

    main_loop.run_in_executor(_pipeline_executor, _run)

    async def event_stream():
        sent = 0
        while True:
            with lock:
                pending = events[sent:]
            if pending:
                for evt, data in pending:
                    sent += 1
                    if evt == "_result":
                        pipeline_result = data
                        yield f"event: done\ndata: {json.dumps({'run_id': pipeline_result.run_id, 'total_units': len(pipeline_result.retrieved_units), 'total_reflections': len(pipeline_result.reflections)}, ensure_ascii=False)}\n\n"
                        return
                    if evt == "error":
                        yield f"event: error\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                        return
                    yield f"event: {evt}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            else:
                await _asyncio.sleep(0.3)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ─────────────────────── /api/chat/sessions ───────────────────────
@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="会话未找到")
    return {"sessionId": session_id, "messages": _sessions[session_id]}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    if session_id in _sessions:
        del _sessions[session_id]
    return {"deleted": True}
