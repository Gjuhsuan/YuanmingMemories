"""这个文件负责串联完整的 GraphRAG 运行主流程。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

from ..agents import create_plan, reflect_on_evidence, synthesize_answer, verify_answer, verify_plan
from ..logging_utils import get_log_path, log_event, new_run_id
from ..model_defs import GraphRAGConfig, PipelineResult, RetrievalUnit, SubQuestion
from ..retrieval import retrieve_for_subquestion
from ..slot_filling import fill_slots_from_units
from .evidence_organizer import build_answer_support_graph_payload, build_context_text, build_grounded_answer


def _run_subquestions_parallel(index, plan, config: GraphRAGConfig, api_key: str, run_id: str) -> List[RetrievalUnit]:
    if len(plan.subquestions) <= 1:
        return [retrieve_for_subquestion(index, plan, plan.subquestions[0], config, api_key=api_key, run_id=run_id)]

    max_workers = min(max(1, config.parallel_workers), len(plan.subquestions))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(retrieve_for_subquestion, index, plan, subq, config, api_key, run_id)
            for subq in plan.subquestions
        ]
        return [future.result() for future in futures]


def _merge_slot_fills(units: List[RetrievalUnit]) -> Dict[str, List[str]]:
    return fill_slots_from_units(units)


def _subquestions_from_actions(actions, step_idx: int) -> List[SubQuestion]:
    subquestions: List[SubQuestion] = []
    for idx, action in enumerate(actions, start=1):
        subquestions.append(
            SubQuestion(
                text=action.query,
                purpose=action.purpose or "reflection search action",
                target_types=["Event", "Entity", "Document", "Relation", "Community"],
                answer_slot=f"reflection_{step_idx}_{idx}",
                seed_queries=action.seed_queries,
                preferred_relations=action.preferred_relations,
            )
        )
    return subquestions


def run_pipeline(index, driver, question: str, api_key: str, config: GraphRAGConfig,
                 event_callback=None) -> PipelineResult:
    """运行完整 GraphRAG 管线。event_callback(event_type, data) 用于流式推送进度。"""
    del driver
    run_id = new_run_id()
    log_path = get_log_path()
    log_event(run_id, "pipeline.start", {"question": question})

    def _emit(evt: str, data: dict):
        if event_callback:
            try:
                event_callback(evt, data)
            except Exception:
                pass

    # ── Step 1-2: 问题规划 ──
    _emit("plan", {"stage": "decompose", "message": "正在分解问题..."})
    draft_plan = create_plan(question, index, api_key if config.use_llm_decomposition else "", run_id, max_subquestions=config.max_subquestions)
    plan = verify_plan(question, draft_plan, api_key if config.use_llm_decomposition else "", run_id, max_subquestions=config.max_subquestions)

    # 语义索引信息
    emb = getattr(index, "emb_index", None)
    emb_info = {"available": bool(emb), "item_count": len(emb) if emb else 0}

    _emit("plan", {
        "stage": "done",
        "task_type": plan.task_type,
        "target_slots": plan.target_slots,
        "seed_queries": plan.seed_queries,
        "subquestions": [{"text": q.text, "purpose": q.purpose} for q in plan.subquestions],
        "entity_hints": plan.entity_hints,
        "relation_hints": plan.relation_hints,
        "time_hints": plan.time_hints,
        "place_hints": plan.place_hints,
        "source": plan.source,
        "embedding_index": emb_info,
    })
    log_event(run_id, "plan.final", {"task_type": plan.task_type, "target_slots": plan.target_slots,
        "seed_queries": plan.seed_queries, "subquestions": [q.text for q in plan.subquestions]})

    # ── Step 3: 逐个子问题检索 ──
    all_units: List[RetrievalUnit] = []
    for idx, subq in enumerate(plan.subquestions):
        _emit("retrieve_start", {
            "sub_idx": idx + 1,
            "total": len(plan.subquestions),
            "question": subq.text,
            "purpose": subq.purpose,
        })
        unit = retrieve_for_subquestion(index, plan, subq, config, api_key=api_key, run_id=run_id)
        all_units.append(unit)

        # 推送检索详情
        assessments = []
        for a in unit.evidence_assessments:
            assessments.append({
                "event_id": a.event_id,
                "relevance": a.relevance,
                "necessity": a.necessity,
                "support_level": a.support_level,
                "keep": a.keep,
                "reason": a.reason[:200] if a.reason else "",
            })

        _emit("retrieve_done", {
            "sub_idx": idx + 1,
            "seed_entities": unit.seed_entities[:20],
            "seed_events": unit.seed_events[:20],
            "selected_relations": unit.selected_relations,
            "candidate_events": len(unit.event_ids),
            "kept_events": len([a for a in unit.evidence_assessments if a.keep]),
            "assessments": assessments,
            "path_lines": unit.path_lines[:10],
            "evidence_lines": unit.evidence_lines[:10],
            "slot_fills": {k: v[:10] for k, v in unit.slot_fills.items()},
            "score": unit.score,
        })

    units = all_units
    reflections = []

    # ── Step 4: 反思循环 ──
    context_text = build_context_text(index, question, units, reflections)
    if api_key and config.use_llm_reflection:
        for step_idx in range(1, config.max_iterations + 1):
            _emit("reflection", {"stage": "thinking", "iteration": step_idx, "max": config.max_iterations})
            slot_snapshot = _merge_slot_fills(units)
            reflection = reflect_on_evidence(
                question, context_text, slot_snapshot, plan.target_slots,
                api_key, run_id, step_idx,
            )
            reflections.append(reflection)

            _emit("reflection", {
                "stage": "done",
                "iteration": step_idx,
                "enough": reflection.enough,
                "missing_slots": reflection.missing_slots,
                "missing_aspects": reflection.missing_aspects,
                "follow_up_questions": reflection.follow_up_questions,
                "note": reflection.note,
                "need_user_clarification": reflection.need_user_clarification,
            })

            if reflection.enough:
                break
            if reflection.need_user_clarification and not reflection.search_actions:
                break
            new_subquestions = _subquestions_from_actions(reflection.search_actions, step_idx)
            if not new_subquestions:
                break
            for s_idx, subq in enumerate(new_subquestions, start=1):
                total_new = len(new_subquestions)
                _emit("retrieve_start", {
                    "sub_idx": s_idx,
                    "total": total_new,
                    "question": subq.text,
                    "purpose": subq.purpose,
                    "from_reflection": step_idx,
                })
                unit = retrieve_for_subquestion(index, plan, subq, config, api_key=api_key, run_id=run_id)
                units.append(unit)
                assessments = []
                for a in unit.evidence_assessments:
                    assessments.append({
                        "event_id": a.event_id, "relevance": a.relevance,
                        "necessity": a.necessity, "support_level": a.support_level,
                        "keep": a.keep, "reason": a.reason[:200] if a.reason else "",
                    })
                _emit("retrieve_done", {
                    "sub_idx": s_idx,
                    "total": total_new,
                    "from_reflection": step_idx,
                    "seed_entities": unit.seed_entities[:20],
                    "seed_events": unit.seed_events[:20],
                    "selected_relations": unit.selected_relations,
                    "candidate_events": len(unit.event_ids),
                    "kept_events": len([a for a in unit.evidence_assessments if a.keep]),
                    "assessments": assessments,
                    "path_lines": unit.path_lines[:10],
                    "evidence_lines": unit.evidence_lines[:10],
                    "slot_fills": {k: v[:10] for k, v in unit.slot_fills.items()},
                    "score": unit.score,
                })
            context_text = build_context_text(index, question, units, reflections)

    # ── Step 5: 支撑图 ──
    graph_nodes, graph_edges = build_answer_support_graph_payload(index, units, max_events=config.related_event_limit)
    _emit("support_graph", {
        "nodes": len(graph_nodes),
        "edges": len(graph_edges),
        "graph": {"nodes": graph_nodes, "edges": graph_edges},
    })

    # ── Step 6-7: 答案合成 + 验证 ──
    context_text = build_context_text(index, question, units, reflections)
    merged_slots = _merge_slot_fills(units)
    _emit("slots", {"slots": merged_slots})
    log_event(run_id, "slots.snapshot", {"slots": merged_slots})

    if api_key and config.use_llm_answer:
        _emit("answer", {"stage": "synthesizing"})
        answer = synthesize_answer(question, context_text, api_key, run_id)
        if config.use_llm_verification:
            _emit("answer", {"stage": "verifying"})
            answer = verify_answer(question, answer, context_text, api_key, run_id)
        _emit("answer", {"stage": "done", "text": answer})
    else:
        answer = build_grounded_answer(question, index, units, plan.task_type)
        _emit("answer", {"stage": "done", "text": answer, "grounded": True})

    log_event(run_id, "pipeline.end", {
        "task_type": plan.task_type, "subquestion_count": len(plan.subquestions),
        "retrieval_units": len(units), "graph_nodes": len(graph_nodes),
        "graph_edges": len(graph_edges),
    })

    result = PipelineResult(
        plan=plan, retrieved_units=units, reflections=reflections, answer=answer,
        graph_nodes=graph_nodes, graph_edges=graph_edges, context_text=context_text,
        run_id=run_id, log_path=log_path,
    )
    _emit("done", {"run_id": run_id, "total_units": len(units), "total_reflections": len(reflections)})
    return result
