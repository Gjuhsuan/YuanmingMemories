"""这个文件负责为每个子问题选择优先使用的图谱关系。"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from ..model_defs import RelationChoice
from .llm_client import call_json_agent


def schema_preview(store, relation_types: Iterable[str] | None = None) -> Dict[str, Any]:
    rels = sorted(set(relation_types or store.get("schema_relation_types", [])))
    return {
        "entity_types": sorted(store.get("schema_types", []))[:80],
        "relation_types": rels[:80],
        "attribute_keys": sorted(store.get("schema_attribute_keys", []))[:60],
        "event_types": sorted({event.get("event_type", "") for event in store.get("events", {}).values() if event.get("event_type")})[:60],
    }


def select_relations(
    question: str,
    subquestion: str,
    store,
    seed_node_summaries: List[Dict[str, str]],
    candidate_relations: List[Dict[str, Any]],
    api_key: str,
    run_id: str,
    stage: str,
    relation_limit: int,
) -> List[RelationChoice]:
    if not api_key or not candidate_relations:
        return [
            RelationChoice(relation=item.get("relation", ""), priority=float(item.get("count", 0)), reason="fallback")
            for item in candidate_relations[:relation_limit]
            if item.get("relation")
        ]

    prompt = f"""
You are a relation-selection agent for graph retrieval.
Choose only from the candidate relation types below. Do not invent new relations.

Original question: {question}
Current subquestion: {subquestion}
Seed nodes: {json.dumps(seed_node_summaries[:20], ensure_ascii=False)}
Candidate relations: {json.dumps(candidate_relations[:80], ensure_ascii=False)}
Schema preview: {json.dumps(schema_preview(store, [item.get('relation', '') for item in candidate_relations]), ensure_ascii=False)}

Return JSON:
{{
  "selected_relations": [
    {{"relation": "candidate relation", "priority": 0-10, "reason": "why it matters"}}
  ],
  "blocked_relations": ["relations to avoid"],
  "note": "short note"
}}

Constraints:
1. Choose at most {relation_limit} relations.
2. Prefer relations that can produce answer-bearing evidence paths.
3. Avoid generic expansion relations if they mainly add noise.
4. Respect explicit hard constraints from the question and subquestion, especially time range, place, historical period, and target subject.
5. Favor relations that help enforce those constraints before relations that only add general context.
6. If a relation mainly expands to adjacent but weakly constrained material, block it.
"""
    data = call_json_agent(
        prompt,
        api_key,
        run_id,
        stage,
        system_prompt="You are a strict graph relation selector. Always return JSON.",
        max_tokens=900,
    )
    choices: List[RelationChoice] = []
    candidate_set = {rel.get("relation") for rel in candidate_relations}
    for item in data.get("selected_relations", [])[:relation_limit]:
        relation = str((item or {}).get("relation", "")).strip()
        if not relation or relation not in candidate_set:
            continue
        choices.append(
            RelationChoice(
                relation=relation,
                priority=float((item or {}).get("priority", 0) or 0),
                reason=str((item or {}).get("reason", "")),
                direction="any",
            )
        )
    if not choices:
        choices = [
            RelationChoice(relation=item.get("relation", ""), priority=float(item.get("count", 0)), reason="fallback")
            for item in candidate_relations[:relation_limit]
            if item.get("relation")
        ]
    return choices[:relation_limit]
