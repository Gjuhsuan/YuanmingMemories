"""这个文件定义问答任务统一使用的答案槽位配置。"""

from __future__ import annotations

from typing import Dict, List


STANDARD_ANSWER_SLOTS: List[str] = [
    "target_events",
    "target_entities",
    "organizations",
    "persons",
    "places",
    "objects",
    "time_points",
    "time_ranges",
    "attributes",
    "titles",
    "documents",
    "event_paths",
    "communities",
    "uncertainties",
]


SLOT_ALIASES: Dict[str, str] = {
    "related_events": "target_events",
    "source_doc": "documents",
    "time_expressions": "time_points",
    "supporting_entities": "target_entities",
}


TASK_SLOT_PRIORITIES: Dict[str, List[str]] = {
    "event_overview": ["target_events", "time_ranges", "documents", "communities"],
    "entity_enumeration": ["persons", "organizations", "places", "objects", "documents"],
    "attribute_lookup": ["attributes", "titles", "objects", "documents", "uncertainties"],
    "timeline_tracking": ["target_events", "time_points", "places", "event_paths", "documents"],
    "cross_event_reasoning": ["target_events", "event_paths", "organizations", "persons", "documents", "uncertainties"],
    "comparison": ["target_events", "event_paths", "attributes", "documents", "uncertainties"],
    "overview": ["target_events", "time_ranges", "documents", "communities"],
    "aggregation": ["persons", "organizations", "places", "objects", "documents"],
    "timeline": ["target_events", "time_points", "places", "event_paths", "documents"],
}


def normalize_slot_name(slot: str) -> str:
    text = str(slot or "").strip()
    if not text:
        return ""
    return SLOT_ALIASES.get(text, text)


def all_standard_slots() -> List[str]:
    return list(STANDARD_ANSWER_SLOTS)


def default_slots_for_task(task_type: str) -> List[str]:
    slots = TASK_SLOT_PRIORITIES.get(task_type, [])
    if slots:
        return list(slots)
    return ["target_events", "documents", "uncertainties"]


def normalize_slot_list(slots: List[str]) -> List[str]:
    seen = set()
    normalized: List[str] = []
    for slot in slots:
        text = normalize_slot_name(slot)
        if not text:
            continue
        if text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized
