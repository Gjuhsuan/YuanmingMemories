"""这个文件定义答案组织阶段使用的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AnswerPlan:
    answer_mode: str
    direct_findings: List[str] = field(default_factory=list)
    indirect_findings: List[str] = field(default_factory=list)
    unresolved_points: List[str] = field(default_factory=list)
    supporting_events: List[str] = field(default_factory=list)
    supporting_entities: List[str] = field(default_factory=list)
    supporting_documents: List[str] = field(default_factory=list)
