"""这个文件负责把检索证据整理成答案和可视化所需结构。"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

from ..answer_slots import default_slots_for_task
from ..model_defs import AnswerPlan
from ..slot_filling import fill_slots_from_units


def _shorten(text: str, limit: int = 220) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "..."


def build_context_text(store, question: str, units: Iterable, reflections: Iterable) -> str:
    del store
    lines: List[str] = [f"Question: {question}", "", "=== Graph-grounded Evidence ==="]
    for idx, unit in enumerate(units, start=1):
        lines.append(f"{idx}. Subquestion: {unit.subquestion}")
        if unit.purpose:
            lines.append(f"   Purpose: {unit.purpose}")
        if unit.seed_entities:
            lines.append(f"   Seed entities: {', '.join(unit.seed_entities)}")
        if unit.seed_events:
            lines.append(f"   Seed events: {', '.join(unit.seed_events)}")
        if unit.selected_relations:
            lines.append(f"   Selected relations: {', '.join(unit.selected_relations)}")
        if unit.community_hits:
            lines.append(f"   Communities: {', '.join(unit.community_hits)}")
        for path_line in unit.path_lines[:4]:
            if path_line:
                lines.append(f"   Path: {_shorten(path_line)}")
        if unit.slot_fills:
            compact_slots = {k: v[:8] for k, v in unit.slot_fills.items() if v}
            if compact_slots:
                lines.append(f"   Filled slots: {compact_slots}")
        if unit.evidence_assessments:
            for assessment in unit.evidence_assessments[:8]:
                lines.append(
                    f"   Evidence score: event={assessment.event_id}, relevance={assessment.relevance}, support={assessment.support_level}, keep={assessment.keep}, reason={_shorten(assessment.reason, 140)}"
                )
        for evidence in unit.evidence_lines[:12]:
            lines.append(f"   - {_shorten(evidence)}")

    reflection_list = list(reflections)
    if reflection_list:
        lines.append("")
        lines.append("=== Reflection Steps ===")
        for step in reflection_list:
            missing = " | ".join(step.missing_aspects or step.missing_slots) if (step.missing_aspects or step.missing_slots) else "none"
            lines.append(f"step {step.step_index}: enough={step.enough} | missing={missing} | note={_shorten(step.note, 160)}")
            if step.need_user_clarification and step.user_question:
                lines.append(f"   Needs clarification: {step.user_question}")
            for action in step.search_actions:
                lines.append(
                    f"   Search action: {action.query} | purpose={action.purpose} | seeds={action.seed_queries} | rels={action.preferred_relations}"
                )
    return "\n".join(lines)


def _node_group(entity_type: str) -> str:
    lower_type = (entity_type or "").lower()
    if any(key in lower_type for key in ["place", "building", "site", "region", "location"]):
        return "Place"
    if any(key in lower_type for key in ["time", "date", "calendar", "temporal"]):
        return "TemporalInterval"
    if any(key in lower_type for key in ["org", "agency", "institution", "office", "bureau", "government"]):
        return "Organization"
    if any(key in lower_type for key in ["artifact", "material", "object", "item", "title", "rank"]):
        return "Object"
    if "document" in lower_type or "archive" in lower_type:
        return "Document"
    if any(key in lower_type for key in ["person", "official", "emperor", "minister", "artisan", "eunuch"]):
        return "Person"
    return "Entity"


def build_graph_payload(store, event_ids: List[str], entity_ids: List[str]) -> Tuple[List[Dict], List[Dict]]:
    nodes: Dict[str, Dict] = {}
    edges: List[Dict] = []
    seen_edges = set()

    def add_node(node_id: str, label: str, group: str, type_cn: str = "") -> None:
        if not node_id:
            return
        nodes[node_id] = {
            "id": node_id,
            "label": label or node_id,
            "group": group,
            "type_cn": type_cn,
        }

    def add_edge(src: str, dst: str, label: str) -> None:
        if not src or not dst:
            return
        key = (src, dst, label)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"from": src, "to": dst, "label": label})

    def add_known_node(node_id: str) -> None:
        if not node_id or node_id in nodes:
            return
        if node_id in store.get("events", {}):
            event = store.get("events", {}).get(node_id, {})
            add_node(node_id, event.get("name", node_id), "Event", event.get("event_type", ""))
            return
        entity = store.get("entities", {}).get(node_id)
        if entity:
            entity_type = entity.get("entity_type", "Entity")
            add_node(node_id, entity.get("name", node_id), _node_group(entity_type), entity_type)
            return
        community = store.get("communities", {}).get(node_id)
        if community:
            add_node(node_id, community.get("name", node_id), "AbstractNorm", community.get("kind", "community"))
            return
        if node_id.startswith("doc_"):
            raw_doc_id = node_id[4:]
            entry = store.get("entries", {}).get(raw_doc_id, {})
            add_node(node_id, entry.get("title", node_id), "Document", "archive")
            return
        entry = store.get("entries", {}).get(node_id)
        if entry:
            add_node(node_id, entry.get("title", node_id), "Document", "archive")
            return
        meta = store.get("node_meta", {}).get(node_id, {})
        if meta:
            kind = str(meta.get("kind", "Entity"))
            group = "Event" if kind == "Event" else _node_group(kind)
            add_node(node_id, meta.get("label", node_id), group, kind)
            return
        add_node(node_id, node_id, "Entity", "")

    event_set = set(event_ids)
    entity_set = set(entity_ids)

    for event_id in event_ids:
        event = store.get("events", {}).get(event_id)
        if not event:
            continue
        add_node(event_id, event.get("name", event_id), "Event", event.get("event_type", ""))
        doc_id = event.get("doc_id", "")
        entry = store.get("entries", {}).get(doc_id)
        if entry:
            doc_node_id = f"doc_{doc_id}"
            add_node(doc_node_id, entry.get("title", doc_id), "Document", "archive")
            add_edge(event_id, doc_node_id, "IN_DOC")
        for community_id in store.get("event_to_communities", {}).get(event_id, [])[:2]:
            community = store.get("communities", {}).get(community_id, {})
            if community:
                add_node(community_id, community.get("name", community_id), "AbstractNorm", community.get("kind", "community"))
                add_edge(event_id, community_id, "IN_COMMUNITY")

    for entity_id in entity_ids:
        entity = store.get("entities", {}).get(entity_id)
        if not entity:
            continue
        entity_type = entity.get("entity_type", "Entity")
        add_node(entity_id, entity.get("name", entity_id), _node_group(entity_type), entity_type)

    for event_id in event_ids:
        for rel in store.get("event_relations", {}).get(event_id, []):
            to_id = rel.get("to_id", "")
            if to_id in entity_set or to_id in event_set:
                add_known_node(event_id)
                add_known_node(to_id)
                add_edge(event_id, to_id, rel.get("relation_type", ""))

    for entity_id in entity_ids:
        for rel in store.get("entity_relations", {}).get(entity_id, []):
            to_id = rel.get("to_id", "")
            if to_id in entity_set or to_id in event_set:
                add_known_node(entity_id)
                add_known_node(to_id)
                add_edge(entity_id, to_id, rel.get("relation_type", ""))

    return list(nodes.values()), edges


def _support_priority(support_level: str) -> int:
    level = (support_level or "").strip().lower()
    if level == "direct":
        return 3
    if level == "indirect":
        return 2
    if level == "background":
        return 1
    return 0


def build_answer_support_graph_payload(store, units: List, max_events: int = 12) -> Tuple[List[Dict], List[Dict]]:
    scored_events: List[Tuple[int, float, float, str]] = []
    seen_event_ids = set()
    fallback_event_ids: List[str] = []

    for unit in units:
        for event_id in unit.event_ids:
            if event_id and event_id not in seen_event_ids:
                fallback_event_ids.append(event_id)
                seen_event_ids.add(event_id)
        for assessment in unit.evidence_assessments:
            if not assessment.keep:
                continue
            priority = _support_priority(assessment.support_level)
            if priority <= 0:
                continue
            scored_events.append((priority, float(assessment.relevance or 0.0), float(assessment.necessity or 0.0), assessment.event_id))

    scored_events.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)

    selected_event_ids: List[str] = []
    selected_seen = set()
    for _, _, _, event_id in scored_events:
        if not event_id or event_id in selected_seen:
            continue
        selected_seen.add(event_id)
        selected_event_ids.append(event_id)
        if len(selected_event_ids) >= max_events:
            break

    if not selected_event_ids:
        selected_event_ids = fallback_event_ids[:max_events]

    selected_entity_ids = set()
    selected_event_set = set(selected_event_ids)

    for event_id in selected_event_ids:
        selected_entity_ids.update(store.get("event_to_entities", {}).get(event_id, set()))
        for rel in store.get("event_relations", {}).get(event_id, []):
            target_id = rel.get("to_id", "")
            if target_id in store.get("entities", {}):
                selected_entity_ids.add(target_id)
            elif target_id in store.get("events", {}) and target_id in selected_event_set:
                continue

    return build_graph_payload(store, selected_event_ids, list(selected_entity_ids))


def build_answer_plan(question: str, units: List, task_type: str) -> AnswerPlan:
    del question
    slots = fill_slots_from_units(units)
    plan = AnswerPlan(answer_mode=task_type or "overview")
    plan.direct_findings.extend(slots.get("related_events", [])[:8])
    plan.supporting_documents.extend(slots.get("source_doc", [])[:8])
    for slot_name in default_slots_for_task(task_type):
        if slot_name in slots and slot_name not in {"related_events", "source_doc"}:
            plan.indirect_findings.extend([f"{slot_name}: {value}" for value in slots.get(slot_name, [])[:6]])
    if not plan.direct_findings and not plan.indirect_findings:
        plan.unresolved_points.append("No sufficient structured findings were extracted from the current graph evidence.")
    return plan


def build_grounded_answer(question: str, store, units: List, task_type: str) -> str:
    del store
    if not units:
        return "The system could not locate enough relevant events or relations in the current graph."
    answer_plan = build_answer_plan(question, units, task_type)
    lines = ["Based on the current graph evidence, the following grounded answer can be given:"]
    if answer_plan.direct_findings:
        lines.append("Direct findings:")
        for item in answer_plan.direct_findings[:8]:
            lines.append(f"- {item}")
    if answer_plan.indirect_findings:
        lines.append("Supporting structured evidence:")
        for item in answer_plan.indirect_findings[:8]:
            lines.append(f"- {item}")
    if answer_plan.supporting_documents:
        lines.append("Supporting documents:")
        for item in answer_plan.supporting_documents[:6]:
            lines.append(f"- {item}")
    if answer_plan.unresolved_points:
        lines.append("Open points:")
        for item in answer_plan.unresolved_points[:4]:
            lines.append(f"- {item}")
    return "\n".join(lines)
