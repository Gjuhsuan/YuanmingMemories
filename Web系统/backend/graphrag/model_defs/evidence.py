"""这个文件定义证据图和槽位状态等中间数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class EvidenceSlotState:
    slot_name: str
    values: List[str] = field(default_factory=list)
    support_level: str = "unknown"
    source_unit_ids: List[str] = field(default_factory=list)
    source_event_ids: List[str] = field(default_factory=list)


@dataclass
class EvidenceGraph:
    node_ids: List[str] = field(default_factory=list)
    edge_keys: List[str] = field(default_factory=list)
    supporting_event_ids: List[str] = field(default_factory=list)
    supporting_entity_ids: List[str] = field(default_factory=list)
    supporting_doc_ids: List[str] = field(default_factory=list)
    slots: Dict[str, EvidenceSlotState] = field(default_factory=dict)
    direct_claims: List[str] = field(default_factory=list)
    indirect_claims: List[str] = field(default_factory=list)
    background_claims: List[str] = field(default_factory=list)
