"""这个文件负责把用户问题规划成图谱检索与推理计划。"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from ..answer_slots import default_slots_for_task, normalize_slot_list, normalize_slot_name
from ..graph import normalize_text
from ..logging_utils import log_event
from ..model_defs import QuestionPlan, SubQuestion
from .llm_client import call_json_agent


def _unique(items: Iterable[str], limit: int | None = None) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        if text not in seen:
            seen.add(text)
            out.append(text)
            if limit and len(out) >= limit:
                break
    return out


def schema_preview(store) -> Dict[str, List[str]]:
    return {
        "entity_types": sorted(store.get("schema_types", []))[:80],
        "relation_types": sorted(store.get("schema_relation_types", []))[:80],
        "attribute_keys": sorted(store.get("schema_attribute_keys", []))[:60],
        "event_types": sorted({event.get("event_type", "") for event in store.get("events", {}).values() if event.get("event_type")})[:60],
        "community_kinds": sorted({community.get("kind", "") for community in store.get("communities", {}).values() if community.get("kind")})[:30],
    }


def matched_surface_names(question: str, store, limit: int = 12) -> List[str]:
    normalized_question = normalize_text(question)
    matches: List[str] = []
    for entity_id, surfaces in store.get("entity_surfaces", {}).items():
        entity = store.get("entities", {}).get(entity_id, {})
        for surface in surfaces:
            norm_surface = normalize_text(surface)
            if len(norm_surface) >= 2 and norm_surface in normalized_question:
                matches.append(entity.get("name", surface))
                break
    for event_id, surfaces in store.get("event_surfaces", {}).items():
        event = store.get("events", {}).get(event_id, {})
        for surface in surfaces:
            norm_surface = normalize_text(surface)
            if len(norm_surface) >= 4 and norm_surface in normalized_question:
                matches.append(event.get("name", surface))
                break
    return _unique(matches, limit=limit)


def fallback_plan(question: str, store) -> QuestionPlan:
    seed_queries = matched_surface_names(question, store, limit=10) or [question]
    subq = SubQuestion(
        text=question,
        purpose="Use the graph schema to perform a general graph-first retrieval.",
        target_types=["Event", "Entity", "Document"],
        answer_slot="target_events",
        seed_queries=seed_queries,
    )
    return QuestionPlan(
        source="fallback",
        original_question=question,
        task_type="graph_qa",
        reasoning_style="schema-constrained graph-first",
        target_slots=default_slots_for_task("overview"),
        seed_queries=seed_queries,
        schema_focus=sorted(store.get("schema_types", []))[:12],
        subquestions=[subq],
    )


def subquestions_from_data(data: Dict[str, Any], fallback_question: str, max_subquestions: int) -> List[SubQuestion]:
    subquestions: List[SubQuestion] = []
    for item in data.get("subquestions", [])[:max_subquestions]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("sub_question") or item.get("question") or "").strip()
        if not text:
            continue
        subquestions.append(
            SubQuestion(
                text=text,
                purpose=str(item.get("purpose", "")),
                target_types=[str(x) for x in item.get("target_types", []) if str(x).strip()],
                answer_slot=normalize_slot_name(str(item.get("answer_slot", "") or "target_events")),
                seed_queries=[str(x) for x in item.get("seed_queries", []) if str(x).strip()],
                preferred_relations=[str(x) for x in item.get("preferred_relations", []) if str(x).strip()],
            )
        )
    if not subquestions:
        subquestions = [
            SubQuestion(
                text=fallback_question,
                purpose="Fallback to the original question when the planner returns no subquestions.",
                target_types=["Event", "Entity", "Document"],
                answer_slot="target_events",
                seed_queries=[fallback_question],
            )
        ]
    return subquestions


def plan_to_payload(plan: QuestionPlan) -> Dict[str, Any]:
    return {
        "source": plan.source,
        "original_question": plan.original_question,
        "task_type": plan.task_type,
        "reasoning_style": plan.reasoning_style,
        "target_slots": plan.target_slots,
        "seed_queries": plan.seed_queries,
        "preferred_entity_types": plan.preferred_entity_types,
        "preferred_event_types": plan.preferred_event_types,
        "schema_focus": plan.schema_focus,
        "relation_policy": plan.relation_policy,
        "subquestions": [
            {
                "text": subq.text,
                "purpose": subq.purpose,
                "target_types": subq.target_types,
                "answer_slot": subq.answer_slot,
                "seed_queries": subq.seed_queries,
                "preferred_relations": subq.preferred_relations,
            }
            for subq in plan.subquestions
        ],
    }


def create_plan(question: str, store, api_key: str, run_id: str, max_subquestions: int = 3) -> QuestionPlan:
    fallback = fallback_plan(question, store)
    if not api_key:
        log_event(run_id, "plan.fallback", {"task_type": fallback.task_type})
        return fallback

    prompt = f"""
You are a schema-aware graph planner inspired by agentic GraphRAG systems.
Plan graph retrieval tasks using only the graph schema and the question. Do not invent external facts.

Question: {question}
Graph schema summary: {json.dumps(schema_preview(store), ensure_ascii=False)}
Surface candidates matched directly in the graph: {json.dumps(matched_surface_names(question, store, limit=20), ensure_ascii=False)}

Return JSON:
{{
  "task_type": "event_overview|entity_enumeration|attribute_lookup|timeline_tracking|cross_event_reasoning|overview|aggregation|timeline|graph_qa",
  "reasoning_style": "schema-constrained graph-first",
  "target_slots": ["standard answer slots"],
  "seed_queries": ["surface names or graph-grounded seed phrases"],
  "preferred_entity_types": ["entity types from schema"],
  "preferred_event_types": ["event types from schema"],
  "schema_focus": ["types or relations central to this question"],
  "relation_policy": [
    {{"relation": "relation type from schema", "priority": 0-10, "reason": "why it matters"}}
  ],
  "subquestions": [
    {{
      "text": "graph-searchable subquestion",
      "purpose": "why this subquestion exists",
      "target_types": ["Event|Entity|Document|Community"],
      "answer_slot": "primary slot to fill",
      "seed_queries": ["seed names"],
      "preferred_relations": ["relation names from schema"]
    }}
  ]
}}

Constraints:
1. At most {max_subquestions} subquestions.
2. Use relation names only from the schema.
3. Prefer event-centric decomposition.
4. If the question asks for overview, do not turn it into a timeline unless the wording explicitly asks for order or sequence.
5. First identify explicit hard constraints from the question, especially time range, place, main subject, and event scope. Preserve them in every relevant subquestion.
6. If the question contains a historical period, dynasty, reign title, date range, place name, or “近代/清代/民国”等时段词, treat them as mandatory filters rather than optional context.
7. Do not broaden the target from a constrained subset to a larger related set. For example, a question about events in a specific period/place should not become a general question about all related events.
8. Prefer seed queries that are exact surface forms of the hard constraints. Avoid vague seeds like “事件”“大事” unless combined with constrained entities or periods.
9. If the question asks “哪些事件/哪些大事”, the primary target slot should still be events; time and documents are supporting slots, not substitutes for the main answer.
"""
    data = call_json_agent(
        prompt,
        api_key,
        run_id,
        "plan",
        system_prompt="You are a precise schema-constrained graph reasoning agent. Always return strict JSON.",
        max_tokens=1800,
    )
    if not isinstance(data, dict) or not data:
        log_event(run_id, "plan.fallback_after_error", {"reason": "empty or invalid LLM plan"})
        return fallback

    subquestions = subquestions_from_data(data, question, max_subquestions=max_subquestions)
    seed_queries = _unique(
        list(data.get("seed_queries", [])) + matched_surface_names(question, store, limit=20) + [q for subq in subquestions for q in subq.seed_queries],
        limit=20,
    )
    valid_relations = set(store.get("schema_relation_types", set()))
    relation_policy = []
    for item in data.get("relation_policy", [])[:20]:
        if not isinstance(item, dict):
            continue
        relation = str(item.get("relation", "")).strip()
        if relation and relation in valid_relations:
            relation_policy.append(
                {
                    "relation": relation,
                    "priority": float(item.get("priority", 0) or 0),
                    "reason": str(item.get("reason", "")),
                }
            )

    task_type = str(data.get("task_type") or fallback.task_type)
    plan = QuestionPlan(
        source="llm",
        original_question=question,
        task_type=task_type,
        reasoning_style=str(data.get("reasoning_style") or "schema-constrained graph-first"),
        target_slots=normalize_slot_list(data.get("target_slots", [])) or default_slots_for_task(task_type),
        entity_hints=seed_queries,
        relation_hints=[item["relation"] for item in relation_policy],
        time_hints=[],
        place_hints=[],
        schema_focus=_unique(data.get("schema_focus", []), limit=30),
        seed_queries=seed_queries,
        preferred_entity_types=_unique(data.get("preferred_entity_types", []), limit=30),
        preferred_event_types=_unique(data.get("preferred_event_types", []), limit=30),
        relation_policy=relation_policy,
        subquestions=subquestions[:max_subquestions],
    )
    return plan
