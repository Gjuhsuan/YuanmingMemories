"""这个文件负责在证据不足时生成下一步反思与追问动作。"""

from __future__ import annotations

import json
from typing import Dict, List

from ..model_defs import ReflectionStep, SearchAction
from .llm_client import call_json_agent


def reflect_on_evidence(
    question: str,
    context_text: str,
    slot_snapshot: Dict[str, List[str]],
    target_slots: List[str],
    api_key: str,
    run_id: str,
    step_index: int,
) -> ReflectionStep:
    prompt = f"""
You are a reflection agent for graph QA.
Decide whether the current evidence graph is sufficient. If not, propose machine-executable search actions instead of vague follow-up prompts.

Original question: {question}
Target slots: {json.dumps(target_slots, ensure_ascii=False)}
Current slot snapshot: {json.dumps(slot_snapshot, ensure_ascii=False)}
Current evidence summary: {context_text[:7000]}

Return JSON:
{{
  "enough": true|false,
  "missing_slots": ["slot names"],
  "missing_aspects": ["aspects still unresolved"],
  "need_user_clarification": false,
  "user_question": "",
  "search_actions": [
    {{
      "query": "next graph retrieval subquestion",
      "purpose": "why to search",
      "seed_queries": ["graph-grounded seeds"],
      "preferred_relations": ["relations from schema"],
      "target_slots": ["slots to fill"]
    }}
  ],
  "note": "short note"
}}

Rules:
1. Judge sufficiency against the original hard constraints, not just topical overlap.
2. If current evidence mixes multiple periods, places, or subjects, treat that as insufficiency rather than sufficiency.
3. Proposed search_actions should become narrower and more constraint-preserving, not broader.
4. Prefer actions that tighten time/place/subject filtering before actions that expand generic context.
"""
    data = call_json_agent(
        prompt,
        api_key,
        run_id,
        f"reflection_{step_index}",
        system_prompt="You are a graph reflection agent. Always return JSON.",
        max_tokens=8192,
    )
    enough_raw = data.get("enough", None)
    actions: List[SearchAction] = []
    for item in data.get("search_actions", [])[:3]:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query", "")).strip()
        if not query:
            continue
        actions.append(
            SearchAction(
                query=query,
                purpose=str(item.get("purpose", "")),
                seed_queries=[str(x) for x in item.get("seed_queries", []) if str(x).strip()],
                preferred_relations=[str(x) for x in item.get("preferred_relations", []) if str(x).strip()],
                target_slots=[str(x) for x in item.get("target_slots", []) if str(x).strip()],
            )
        )
    return ReflectionStep(
        step_index=step_index,
        question=question,
        enough=bool(enough_raw) if enough_raw is not None else False,
        missing_slots=[str(x) for x in data.get("missing_slots", [])],
        missing_aspects=[str(x) for x in data.get("missing_aspects", [])],
        follow_up_questions=[str(x) for x in data.get("follow_up_questions", [])][:2],
        search_actions=actions,
        need_user_clarification=bool(data.get("need_user_clarification", False)),
        user_question=str(data.get("user_question", "")),
        note=str(data.get("note", "")),
    )
