"""这个文件负责对子图候选中的事件与证据进行排序。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

from ..agents import assess_evidence
from ..answer_slots import normalize_slot_name
from ..graph import token_set
from ..model_defs import EvidenceAssessment


def relation_texts_for_event(store, event_id: str) -> List[str]:
    texts = []
    for rel in store.get("event_relations", {}).get(event_id, []):
        target_id = rel.get("to_id", "")
        target = store.get("events", {}).get(target_id) or store.get("entities", {}).get(target_id, {})
        texts.append(
            " ".join(
                x
                for x in [
                    rel.get("relation_type", ""),
                    target.get("name", target_id),
                    str(rel.get("evidence", "")),
                ]
                if x
            )
        )
    return texts


def event_generic_score(store, event_id: str, question_text: str, selected_relations: Set[str]) -> float:
    event = store.get("events", {}).get(event_id, {})
    doc = store.get("entries", {}).get(event.get("doc_id", ""), {})
    text = " ".join(
        [
            event.get("name", ""),
            event.get("event_type", ""),
            event.get("date_text", ""),
            event.get("source_text", ""),
            doc.get("title", ""),
            " ".join(relation_texts_for_event(store, event_id)),
        ]
    )
    event_tokens = token_set(text, min_ngram=3, max_ngram=4)
    query_tokens = token_set(question_text, min_ngram=2, max_ngram=4)
    overlap = len(event_tokens & query_tokens)
    relation_bonus = 0.0
    if selected_relations:
        event_relations = {rel.get("relation_type", "") for rel in store.get("event_relations", {}).get(event_id, [])}
        relation_bonus = len(event_relations & selected_relations) * 1.5
    return overlap * 0.6 + relation_bonus


def evidence_item(store, event_id: str, score: float) -> Dict[str, Any]:
    event = store.get("events", {}).get(event_id, {})
    doc = store.get("entries", {}).get(event.get("doc_id", ""), {})
    relations = []
    for rel in store.get("event_relations", {}).get(event_id, [])[:12]:
        target_id = rel.get("to_id", "")
        target = store.get("events", {}).get(target_id) or store.get("entities", {}).get(target_id, {})
        relations.append(
            {
                "relation_type": rel.get("relation_type", ""),
                "target_id": target_id,
                "target_name": target.get("name", target_id),
                "target_type": target.get("event_type") or target.get("entity_type", ""),
                "evidence": str(rel.get("evidence", ""))[:220],
            }
        )
    return {
        "event_id": event_id,
        "event_name": event.get("name", event_id),
        "event_type": event.get("event_type", ""),
        "date_text": event.get("date_text", ""),
        "source_text": event.get("source_text", "")[:500],
        "doc_id": event.get("doc_id", ""),
        "doc_title": doc.get("title", ""),
        "score": score,
        "relations": relations,
    }


def evidence_lines_from_item(item: Dict[str, Any], assessment: EvidenceAssessment | None = None) -> List[str]:
    prefix = "[Event]"
    if assessment:
        prefix = f"[Event|{assessment.support_level}|rel={assessment.relevance}]"
    lines = [
        f"{prefix} {item.get('event_name', '')} | type: {item.get('event_type', '')} | time: {item.get('date_text', '')} | doc: {item.get('doc_title', '')}",
    ]
    if item.get("source_text"):
        lines.append(f"[Source] {item.get('source_text')}")
    for rel in item.get("relations", [])[:6]:
        lines.append(
            f"[Relation] {rel.get('relation_type', '')} -> {rel.get('target_name', '')} ({rel.get('target_type', '')}) | evidence: {rel.get('evidence', '')}"
        )
    if assessment and assessment.claims:
        for claim in assessment.claims[:3]:
            lines.append(f"[SupportedClaim] {claim}")
    if assessment and assessment.reason:
        lines.append(f"[Assessment] {assessment.reason}")
    return lines


def rank_and_assess_events(
    store,
    plan,
    subq,
    config,
    api_key: str,
    run_id: str,
    candidate_scores: Dict[str, float],
    selected_relations: Set[str],
) -> Tuple[List[str], List[EvidenceAssessment], List[str], Dict[str, List[str]]]:
    original_question = getattr(plan, "original_question", "") or subq.text
    question_text = f"{original_question} {subq.text} {plan.task_type}"
    for event_id in list(candidate_scores):
        candidate_scores[event_id] += event_generic_score(store, event_id, question_text, selected_relations)

    ranked = sorted(candidate_scores.items(), key=lambda kv: kv[1], reverse=True)[: config.candidate_event_limit]
    evidence_items = [evidence_item(store, event_id, score) for event_id, score in ranked]

    if api_key and config.use_llm_evidence_scoring:
        assessments = assess_evidence(
            question=question_text,
            subquestion=subq.text,
            target_slots=plan.target_slots,
            evidence_items=evidence_items,
            api_key=api_key,
            run_id=run_id,
            stage=f"evidence_score.{subq.answer_slot or 'subq'}",
            min_relevance=config.min_llm_relevance,
            fallback_keep_limit=min(3, config.event_limit_per_subquestion),
        )
    else:
        assessments = [
            EvidenceAssessment(
                event_id=item["event_id"],
                relevance=min(10.0, float(item.get("score", 0.0))),
                support_level="unverified",
                keep=item.get("event_id", "") in {ranked_item[0] for ranked_item in ranked[: min(3, config.event_limit_per_subquestion)]},
                reason="fallback lexical score",
            )
            for item in evidence_items
        ]

    assessment_by_event = {a.event_id: a for a in assessments}
    kept = [
        event_id
        for event_id, _ in ranked
        if assessment_by_event.get(event_id, EvidenceAssessment(event_id=event_id)).keep
    ]
    if not kept:
        kept = [event_id for event_id, _ in ranked[: config.event_limit_per_subquestion]]
    kept = kept[: config.event_limit_per_subquestion]

    item_by_event = {item["event_id"]: item for item in evidence_items}
    evidence_lines: List[str] = []
    kept_assessments: List[EvidenceAssessment] = []
    slot_fills: Dict[str, List[str]] = defaultdict(list)
    for event_id in kept:
        assessment = assessment_by_event.get(event_id)
        if assessment:
            kept_assessments.append(assessment)
            for key, values in assessment.slots.items():
                slot_name = normalize_slot_name(key)
                if not slot_name:
                    continue
                for value in values:
                    text = str(value or "").strip()
                    if text and text not in slot_fills[slot_name]:
                        slot_fills[slot_name].append(text)
        evidence_lines.extend(evidence_lines_from_item(item_by_event[event_id], assessment))
        event = store.get("events", {}).get(event_id, {})
        if event.get("name") and event["name"] not in slot_fills["target_events"]:
            slot_fills["target_events"].append(event["name"])
        doc_id = event.get("doc_id", "")
        title = store.get("entries", {}).get(doc_id, {}).get("title", "")
        if doc_id and title:
            value = f"{doc_id}:{title}"
            if value not in slot_fills["documents"]:
                slot_fills["documents"].append(value)
    return kept, kept_assessments, evidence_lines, dict(slot_fills)
