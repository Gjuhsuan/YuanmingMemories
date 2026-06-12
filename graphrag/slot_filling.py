"""这个文件负责根据证据子图补全过程中的答案槽位信息。"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List

from .answer_slots import default_slots_for_task, normalize_slot_name
from .model_defs import EvidenceAssessment


ENTITY_TYPE_GROUPS = {
    "organizations": ("org", "agency", "institution", "office", "ministry", "bureau", "government"),
    "persons": ("person", "official", "emperor", "minister", "artisan", "eunuch", "consort", "prince"),
    "places": ("place", "building", "site", "region", "location", "complex"),
    "objects": ("artifact", "material", "object", "item", "stone", "wood"),
    "time_points": ("time", "date", "calendar", "temporal"),
    "documents": ("document", "archive", "archival"),
    "titles": ("title", "rank", "position", "office_title"),
}


def default_target_slots() -> List[str]:
    return default_slots_for_task("overview")


def _append_unique(bucket: List[str], value: str, limit: int = 16) -> None:
    value = str(value or "").strip()
    if value and value not in bucket and len(bucket) < limit:
        bucket.append(value)


def _entity_name(store: Dict, entity_id: str) -> str:
    return store.get("entities", {}).get(entity_id, {}).get("name", entity_id)


def _entity_type(store: Dict, entity_id: str) -> str:
    return store.get("entities", {}).get(entity_id, {}).get("entity_type", "").lower()


def _slot_for_entity_type(entity_type: str) -> str:
    entity_type = (entity_type or "").lower()
    for slot, keys in ENTITY_TYPE_GROUPS.items():
        if any(key in entity_type for key in keys):
            return slot
    return "target_entities"


def merge_slots(slot_dicts: Iterable[Dict[str, List[str]]], limit_per_slot: int = 24) -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = defaultdict(list)
    for slots in slot_dicts:
        for key, values in (slots or {}).items():
            slot_name = normalize_slot_name(key)
            if not slot_name:
                continue
            if not isinstance(values, list):
                values = [values]
            for value in values:
                _append_unique(merged[slot_name], str(value), limit=limit_per_slot)
    return dict(merged)


def slots_from_assessments(assessments: Iterable[EvidenceAssessment]) -> Dict[str, List[str]]:
    return merge_slots([assessment.slots for assessment in assessments if assessment.keep])


def fill_slots_from_units(units: Iterable) -> Dict[str, List[str]]:
    return merge_slots([getattr(unit, "slot_fills", {}) for unit in units])


def fill_slots(question: str, store: Dict, units: Iterable, task_type: str, target_slots: List[str] | None = None) -> Dict[str, List[str]]:
    """Schema/type based fallback slot filling.

    This function intentionally does not inspect domain keywords in the question.
    It merges LLM-provided slots first; if absent, it creates conservative slots
    from event names, source docs and entity schema types.
    """
    del question
    slots: Dict[str, List[str]] = defaultdict(list)
    target_slots = [normalize_slot_name(slot) for slot in (target_slots or default_slots_for_task(task_type)) if normalize_slot_name(slot)]

    for unit in units:
        for key, values in getattr(unit, "slot_fills", {}).items():
            slot_name = normalize_slot_name(key)
            if not slot_name:
                continue
            for value in values:
                _append_unique(slots[slot_name], value)

        for assessment in getattr(unit, "evidence_assessments", []):
            if not assessment.keep:
                continue
            for key, values in assessment.slots.items():
                slot_name = normalize_slot_name(key)
                if not slot_name:
                    continue
                for value in values:
                    _append_unique(slots[slot_name], value)

        for event_id in getattr(unit, "event_ids", []):
            event = store.get("events", {}).get(event_id, {})
            if event.get("name"):
                _append_unique(slots["target_events"], event["name"], limit=24)
            if event.get("date_text"):
                _append_unique(slots["time_points"], event["date_text"], limit=16)
            doc_id = event.get("doc_id", "")
            title = store.get("entries", {}).get(doc_id, {}).get("title", "")
            if doc_id and title:
                _append_unique(slots["documents"], f"{doc_id}:{title}", limit=16)

        for entity_id in getattr(unit, "entity_ids", []):
            entity_name = _entity_name(store, entity_id)
            entity_type = _entity_type(store, entity_id)
            slot_name = _slot_for_entity_type(entity_type)
            _append_unique(slots[slot_name], entity_name, limit=24)

            entity = store.get("entities", {}).get(entity_id, {})
            for attr_key, attr_value in list(entity.get("attributes", {}).items())[:4]:
                attr_value = str(attr_value)
                if attr_value:
                    _append_unique(slots[f"attribute::{attr_key}"], attr_value, limit=16)

    if target_slots:
        for slot in target_slots:
            normalized_slot = normalize_slot_name(slot)
            if normalized_slot:
                slots.setdefault(normalized_slot, [])
    return {key: values for key, values in slots.items() if values or key in target_slots}
