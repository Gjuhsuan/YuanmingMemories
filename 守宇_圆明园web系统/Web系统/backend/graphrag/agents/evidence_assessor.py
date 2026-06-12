"""这个文件负责评估候选事件和证据是否值得保留。"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from ..answer_slots import normalize_slot_name
from ..model_defs import EvidenceAssessment
from .llm_client import call_json_agent


def _normalize_slots(raw_slots: Any) -> Dict[str, List[str]]:
    if not isinstance(raw_slots, dict):
        return {}
    normalized: Dict[str, List[str]] = {}
    for key, value in raw_slots.items():
        slot_name = normalize_slot_name(key)
        if not slot_name:
            continue
        if isinstance(value, list):
            normalized[slot_name] = [str(x) for x in value if str(x).strip()]
        elif value is not None and str(value).strip():
            normalized[slot_name] = [str(value)]
    return normalized


def _normalize_claims(raw_claims: Any) -> List[str]:
    if isinstance(raw_claims, list):
        return [str(x) for x in raw_claims if str(x).strip()]
    if raw_claims is not None and str(raw_claims).strip():
        return [str(raw_claims)]
    return []


def _normalize_item_list(raw_items: Any) -> List[Dict[str, Any]]:
    if isinstance(raw_items, dict):
        return [raw_items]
    if not isinstance(raw_items, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, dict):
            normalized.append(item)
        elif isinstance(item, list):
            normalized.extend([sub for sub in item if isinstance(sub, dict)])
    return normalized


def assess_evidence(
    question: str,
    subquestion: str,
    target_slots: List[str],
    evidence_items: List[Dict[str, Any]],
    api_key: str,
    run_id: str,
    stage: str,
    min_relevance: float = 5.0,
    fallback_keep_limit: int = 3,
) -> List[EvidenceAssessment]:
    if not api_key or not evidence_items:
        keep_event_ids = {item.get("event_id", "") for item in evidence_items[: max(1, fallback_keep_limit)]}
        return [
            EvidenceAssessment(
                event_id=item.get("event_id", ""),
                relevance=float(item.get("score", 0.0)),
                necessity=0.0,
                support_level="unverified",
                keep=item.get("event_id", "") in keep_event_ids,
                reason="fallback scoring without LLM evidence assessment",
            )
            for item in evidence_items
            if item.get("event_id")
        ]

    prompt = f"""
You are an evidence-assessment agent.
Judge whether each candidate event should be retained in the final evidence graph.

Original question: {question}
Current subquestion: {subquestion}
Target answer slots: {json.dumps(target_slots, ensure_ascii=False)}
Candidate evidence: {json.dumps(evidence_items[:30], ensure_ascii=False)}

Return JSON:
{{
  "items": [
    {{
      "event_id": "event id",
      "relevance": 0-10,
      "necessity": 0-10,
      "support_level": "direct|indirect|background|weak|irrelevant",
      "keep": true,
      "reason": "why",
      "slots": {{"slot_name": ["values"]}},
      "claims": ["claims supported by this evidence"]
    }}
  ]
}}

Rules:
1. Use only the supplied evidence.
2. Background-related but non-answering events should be marked background or weak.
3. Prefer keep=true only for direct or indirect evidence with relevance >= {min_relevance}.
4. Treat explicit hard constraints in the question as mandatory filters, especially time range, place, dynasty/reign/period, and main subject.
5. If an event violates a hard constraint, mark it weak or irrelevant and set keep=false even if it is topically related.
6. Distinguish between “same topic” and “same constrained answer set”. Topical similarity alone is not enough.
7. Use the slots field to record which hard constraints this evidence satisfies, such as time, place, subject, or event type.
"""
    data = call_json_agent(
        prompt,
        api_key,
        run_id,
        stage,
        system_prompt="You are a strict graph evidence judge. Always return JSON.",
        max_tokens=8192,
    )
    assessments: List[EvidenceAssessment] = []
    valid_ids = {item.get("event_id") for item in evidence_items}
    for item in _normalize_item_list(data.get("items", [])):
        event_id = str((item or {}).get("event_id", "")).strip()
        if event_id not in valid_ids:
            continue
        support_level = str((item or {}).get("support_level", "weak") or "weak")
        relevance = float((item or {}).get("relevance", 0) or 0)
        default_keep = support_level in {"direct", "indirect"} and relevance >= min_relevance
        assessments.append(
            EvidenceAssessment(
                event_id=event_id,
                relevance=relevance,
                necessity=float((item or {}).get("necessity", 0) or 0),
                support_level=support_level,
                keep=bool((item or {}).get("keep", default_keep)),
                reason=str((item or {}).get("reason", "")),
                slots=_normalize_slots((item or {}).get("slots", {})),
                claims=_normalize_claims((item or {}).get("claims", [])),
            )
        )
    if not assessments:
        keep_event_ids = {item.get("event_id", "") for item in evidence_items[: max(1, fallback_keep_limit)]}
        return [
            EvidenceAssessment(
                event_id=item.get("event_id", ""),
                relevance=float(item.get("score", 0.0)),
                support_level="unverified",
                keep=item.get("event_id", "") in keep_event_ids,
                reason="LLM assessment failed; kept by fallback rank",
            )
            for item in evidence_items
            if item.get("event_id")
        ]
    return assessments
