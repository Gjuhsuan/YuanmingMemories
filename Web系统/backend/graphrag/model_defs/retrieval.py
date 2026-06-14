"""这个文件定义子图检索与排序阶段使用的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RelationChoice:
    relation: str
    priority: float = 0.0
    reason: str = ""
    direction: str = "any"


@dataclass
class SearchAction:
    query: str = ""
    purpose: str = ""
    seed_queries: List[str] = field(default_factory=list)
    preferred_relations: List[str] = field(default_factory=list)
    target_slots: List[str] = field(default_factory=list)


@dataclass
class EvidenceAssessment:
    event_id: str
    relevance: float = 0.0
    necessity: float = 0.0
    support_level: str = "weak"
    keep: bool = True
    reason: str = ""
    slots: Dict[str, List[str]] = field(default_factory=dict)
    claims: List[str] = field(default_factory=list)


@dataclass
class SubgraphUnit:
    unit_id: str
    unit_type: str
    summary: str = ""
    seed_nodes: List[str] = field(default_factory=list)
    node_ids: List[str] = field(default_factory=list)
    edge_keys: List[str] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)
    entity_ids: List[str] = field(default_factory=list)
    doc_ids: List[str] = field(default_factory=list)
    community_ids: List[str] = field(default_factory=list)
    path_lines: List[str] = field(default_factory=list)
    score: float = 0.0
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class RetrievalUnit:
    subquestion: str
    purpose: str
    seed_entities: List[str] = field(default_factory=list)
    seed_events: List[str] = field(default_factory=list)
    community_hits: List[str] = field(default_factory=list)
    selected_relations: List[str] = field(default_factory=list)
    path_lines: List[str] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)
    entity_ids: List[str] = field(default_factory=list)
    doc_ids: List[str] = field(default_factory=list)
    evidence_lines: List[str] = field(default_factory=list)
    evidence_assessments: List[EvidenceAssessment] = field(default_factory=list)
    slot_fills: Dict[str, List[str]] = field(default_factory=dict)
    reflection_note: str = ""
    score: float = 0.0
