"""这个文件定义问题规划阶段使用的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SubQuestion:
    text: str
    purpose: str = ""
    target_types: List[str] = field(default_factory=list)
    answer_slot: str = ""
    seed_queries: List[str] = field(default_factory=list)
    preferred_relations: List[str] = field(default_factory=list)


@dataclass
class RelationPolicyItem:
    relation: str
    priority: float = 0.0
    reason: str = ""
    direction: str = "any"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QuestionPlan:
    source: str
    original_question: str
    task_type: str
    reasoning_style: str
    target_slots: List[str] = field(default_factory=list)
    entity_hints: List[str] = field(default_factory=list)
    relation_hints: List[str] = field(default_factory=list)
    time_hints: List[str] = field(default_factory=list)
    place_hints: List[str] = field(default_factory=list)
    schema_focus: List[str] = field(default_factory=list)
    seed_queries: List[str] = field(default_factory=list)
    preferred_entity_types: List[str] = field(default_factory=list)
    preferred_event_types: List[str] = field(default_factory=list)
    relation_policy: List[Dict[str, Any]] = field(default_factory=list)
    subquestions: List[SubQuestion] = field(default_factory=list)
