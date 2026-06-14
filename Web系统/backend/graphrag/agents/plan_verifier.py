"""这个文件负责复核问题规划结果是否满足任务约束。"""

from __future__ import annotations

import json

from ..answer_slots import default_slots_for_task, normalize_slot_list
from ..model_defs import QuestionPlan
from .llm_client import call_json_agent
from .planner import plan_to_payload, subquestions_from_data


def _fallback_verify_task_type(question: str, task_type: str, subquestions) -> str:
    q = question.strip()
    timeline_markers = ["什么时候", "何时", "时间线", "先后", "之后", "先", "后", "经过"]
    enumeration_markers = ["哪些", "哪几", "主要有哪些", "发生了哪些", "哪些大事", "哪些事件"]
    comparison_markers = ["比较", "对比", "异同", "区别"]
    causal_markers = ["为什么", "原因", "为何", "怎么导致"]

    if any(marker in q for marker in comparison_markers):
        return "cross_event_reasoning"
    if any(marker in q for marker in causal_markers):
        return "cross_event_reasoning"
    if any(marker in q for marker in timeline_markers):
        return "timeline_tracking"
    if any(marker in q for marker in enumeration_markers):
        if any(marker in q for marker in ["机构", "人物", "哪些人", "哪些机构"]):
            return "entity_enumeration"
        return "event_overview"

    if task_type in {"timeline", "timeline_tracking"}:
        subq_text = " ".join(subq.text for subq in subquestions)
        if not any(marker in subq_text for marker in timeline_markers):
            return "event_overview"
    return task_type


def verify_plan(question: str, draft_plan: QuestionPlan, api_key: str, run_id: str, max_subquestions: int = 3) -> QuestionPlan:
    if not api_key:
        return draft_plan
    prompt = f"""
You are the second-pass verifier for a graph planner.
Do not create a brand new plan from scratch. Check whether the existing plan is consistent with the original question.

Focus:
1. Is task_type correct?
2. Are target_slots aligned with the actual answer goal?
3. Are subquestions centered on the primary problem instead of a secondary dimension?
4. Use timeline only when the question explicitly asks for order, sequence, "when", "after that", or a timeline.
5. Questions like "what major events happened" under a time range should usually be event_overview or entity_enumeration, not timeline.
6. Check whether all explicit hard constraints in the original question are preserved: time range, place, main subject, event class, and historical scope.
7. Reject plans whose subquestions silently drop or weaken those hard constraints.
8. Supporting subquestions may clarify time or sources, but they must not replace the primary constrained event-retrieval subquestion.

Original question: {question}
Draft plan: {json.dumps(plan_to_payload(draft_plan), ensure_ascii=False)}

Return JSON:
{{
  "decision": "keep|revise",
  "task_type": "corrected task type",
  "target_slots": ["corrected slots"],
  "seed_queries": ["corrected seeds"],
  "subquestions": [
    {{
      "text": "subquestion",
      "purpose": "purpose",
      "target_types": ["Event|Entity|Document|Community"],
      "answer_slot": "main slot",
      "seed_queries": ["seed"],
      "preferred_relations": ["relation"]
    }}
  ],
  "issues": ["issues found"],
  "reason": "why"
}}

If the draft plan is too broad, revise it to become narrower and constraint-preserving.
"""
    data = call_json_agent(
        prompt,
        api_key,
        run_id,
        "plan.verify",
        system_prompt="You are a strict verifier for graph planning. Always return JSON.",
        max_tokens=1400,
    )
    if not isinstance(data, dict) or not data:
        return draft_plan

    verified_task_type = str(data.get("task_type", "")).strip() or draft_plan.task_type
    verified_task_type = _fallback_verify_task_type(question, verified_task_type, draft_plan.subquestions)
    decision = str(data.get("decision", "keep")).strip().lower()
    if decision != "revise" and verified_task_type == draft_plan.task_type:
        return draft_plan

    subquestions = subquestions_from_data(data, question, max_subquestions=max_subquestions)
    target_slots = normalize_slot_list(data.get("target_slots", [])) or draft_plan.target_slots or default_slots_for_task(verified_task_type)
    seed_queries = list(dict.fromkeys(list(data.get("seed_queries", [])) + [q for subq in subquestions for q in subq.seed_queries] + draft_plan.seed_queries))

    return QuestionPlan(
        source=f"{draft_plan.source}+verified",
        original_question=draft_plan.original_question,
        task_type=verified_task_type,
        reasoning_style=draft_plan.reasoning_style,
        target_slots=target_slots,
        entity_hints=seed_queries,
        relation_hints=draft_plan.relation_hints,
        time_hints=draft_plan.time_hints,
        place_hints=draft_plan.place_hints,
        schema_focus=draft_plan.schema_focus,
        seed_queries=seed_queries,
        preferred_entity_types=draft_plan.preferred_entity_types,
        preferred_event_types=draft_plan.preferred_event_types,
        relation_policy=draft_plan.relation_policy,
        subquestions=subquestions[:max_subquestions] if subquestions else draft_plan.subquestions,
    )
