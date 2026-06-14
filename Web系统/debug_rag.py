#!/usr/bin/env python3
"""
GraphRAG 全流程流式观察工具 —— 展示多 Agent 管线每一步。
用法：python3 debug_rag.py "你的问题"
"""
import sys, json, httpx, asyncio

BACKEND = "http://127.0.0.1:8000"
DIV = "=" * 70
SUB = "-" * 50


async def main(question: str):
    async with httpx.AsyncClient(timeout=300.0) as client:
        print(f"\n{DIV}")
        print(f"  🔬 GraphRAG 全流程流式观察")
        print(f"{DIV}")
        print(f"\n📝 问题: {question}\n")

        async with client.stream(
            "POST", f"{BACKEND}/api/chat/graphrag",
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            json={"question": question, "sessionId": "debug", "history": [], "pinnedNodeIds": []},
        ) as resp:
            print(f"📡 HTTP {resp.status_code} — GraphRAG 管线启动\n")

            buffer = ""
            step_num = 0

            async for chunk in resp.aiter_bytes():
                buffer += chunk.decode("utf-8")

                while "\n\n" in buffer:
                    block, buffer = buffer.split("\n\n", 1)
                    block = block.strip()
                    if not block:
                        continue

                    lines = block.split("\n")
                    event_type, data_str = "", ""
                    for line in lines:
                        s = line.strip()
                        if s.startswith("event:"):
                            event_type = s[6:].strip()
                        elif s.startswith("data:"):
                            data_str = s[5:].strip()

                    if not data_str:
                        continue
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    # ── plan ──
                    if event_type == "plan":
                        if data.get("stage") == "decompose":
                            print(f"{SUB}")
                            print(f"🧠 [1] 问题规划 — LLM 分解问题...")
                            print(f"{SUB}")
                        else:
                            step_num += 1
                            print(f"  任务类型: {data.get('task_type', '?')}")
                            print(f"  目标槽位: {', '.join(data.get('target_slots', []))}")
                            print(f"  规划来源: {data.get('source', '?')}")
                            if data.get("entity_hints"):
                                print(f"  实体线索: {', '.join(data['entity_hints'])}")
                            if data.get("time_hints"):
                                print(f"  时间线索: {', '.join(data['time_hints'])}")
                            if data.get("place_hints"):
                                print(f"  地点线索: {', '.join(data['place_hints'])}")
                            sqs = data.get("subquestions", [])
                            if sqs:
                                print(f"\n  📋 子问题 ({len(sqs)}):")
                                for i, sq in enumerate(sqs, 1):
                                    print(f"    {i}. {sq['text']}")
                                    print(f"       目的: {sq['purpose']}")
                            print()

                    # ── retrieve_start ──
                    elif event_type == "retrieve_start":
                        print(f"{SUB}")
                        print(f"🔍 [2] 检索 — 子问题 {data.get('sub_idx')}/{data.get('total')}")
                        print(f"{SUB}")
                        print(f"  问题: {data['question']}")
                        print(f"  目的: {data['purpose']}")
                        print(f"  正在检索...")

                    # ── retrieve_done ──
                    elif event_type == "retrieve_done":
                        print(f"\n  ✅ 检索完成 (子问题 {data.get('sub_idx')})")
                        se = data.get("seed_entities", [])
                        sev = data.get("seed_events", [])
                        if se:
                            print(f"  种子实体 ({len(se)}): {', '.join(se[:15])}{'...' if len(se) > 15 else ''}")
                        if sev:
                            print(f"  种子事件 ({len(sev)}): {', '.join(sev[:10])}{'...' if len(sev) > 10 else ''}")
                        rels = data.get("selected_relations", [])
                        if rels:
                            print(f"  选中关系 ({len(rels)}): {', '.join(rels)}")
                        print(f"  候选事件: {data.get('candidate_events', 0)} → 保留: {data.get('kept_events', 0)}")
                        print(f"  检索评分: {data.get('score', 0):.2f}")

                        # 证据评估详情
                        assessments = data.get("assessments", [])
                        if assessments:
                            print(f"\n  📊 证据评估:")
                            for a in assessments:
                                keep_mark = "✓" if a["keep"] else "✗"
                                print(f"    {keep_mark} {a['event_id']}: relev={a['relevance']:.0f} nec={a['necessity']:.0f} [{a['support_level']}] — {a['reason'][:100]}")

                        # 路径
                        paths = data.get("path_lines", [])
                        if paths:
                            print(f"\n  🛤️ 图路径 ({len(paths)}):")
                            for p in paths[:5]:
                                print(f"    {p[:150]}")

                        slot_fills = data.get("slot_fills", {})
                        if slot_fills:
                            print(f"\n  🎯 槽位填充:")
                            for k, v in slot_fills.items():
                                print(f"    {k}: {', '.join(v[:8])}")
                        print()

                    # ── reflection ──
                    elif event_type == "reflection":
                        if data.get("stage") == "thinking":
                            print(f"{SUB}")
                            print(f"🔄 [3] 反思 — 第 {data['iteration']}/{data['max']} 轮")
                            print(f"{SUB}")
                            print(f"  正在评估证据充分性...")
                        else:
                            enough = "✅ 证据充分" if data.get("enough") else "⚠️ 证据不足"
                            print(f"  {enough}")
                            print(f"  缺失槽位: {data.get('missing_slots', [])}")
                            print(f"  缺失方面: {data.get('missing_aspects', [])}")
                            fuq = data.get("follow_up_questions", [])
                            if fuq:
                                print(f"  追问: {fuq}")
                            if data.get("note"):
                                print(f"  备注: {data['note']}")
                            if data.get("need_user_clarification"):
                                print(f"  ⚠️ 需要用户澄清")
                            print()

                    # ── support_graph ──
                    elif event_type == "support_graph":
                        step_num += 1
                        print(f"{SUB}")
                        print(f"📊 [4] 支撑图谱: {data['nodes']} 节点, {data['edges']} 边")
                        print(f"{SUB}\n")

                    # ── slots ──
                    elif event_type == "slots":
                        slots = data.get("slots", {})
                        if slots:
                            print(f"{SUB}")
                            print(f"🎯 [5] 最终槽位填充")
                            print(f"{SUB}")
                            for k, v in slots.items():
                                print(f"  {k}: {', '.join(v[:12])}")
                            print()

                    # ── answer ──
                    elif event_type == "answer":
                        if data.get("stage") == "synthesizing":
                            print(f"{SUB}")
                            print(f"💬 [6] LLM 答案合成中...")
                            print(f"{SUB}")
                        elif data.get("stage") == "verifying":
                            print(f"  🔍 正在验证答案...")
                        else:
                            print(f"\n{'─' * 50}")
                            print(f"📝 最终答案:")
                            print(f"{'─' * 50}")
                            print(data.get("text", ""))
                            print(f"{'─' * 50}\n")

                    # ── error ──
                    elif event_type == "error":
                        print(f"\n❌ 错误: {data.get('message', '?')}")
                        if data.get("trace"):
                            print(f"\n堆栈:\n{data['trace']}")

                    # ── done ──
                    elif event_type == "done":
                        print(f"{DIV}")
                        print(f"  ✅ 管线完成 | 检索单元: {data.get('total_units', '?')} | 反思轮次: {data.get('total_reflections', '?')}")
                        print(f"{DIV}\n")

        # 处理残留 buffer
        if buffer.strip():
            print(f"  ⚠️ 残留 buffer: {buffer[:200]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 debug_rag.py \"你的问题\"")
        print("示例: python3 debug_rag.py \"雍正二年圆明园营造涉及哪些机构？\"")
        sys.exit(1)
    asyncio.run(main(" ".join(sys.argv[1:])))
