"""这个文件定义运行时返回结果与上下文相关的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .planning import QuestionPlan
from .retrieval import RetrievalUnit, SearchAction


@dataclass
class ReflectionStep:
    step_index: int
    question: str
    enough: bool
    missing_slots: List[str] = field(default_factory=list)
    missing_aspects: List[str] = field(default_factory=list)
    follow_up_questions: List[str] = field(default_factory=list)
    search_actions: List[SearchAction] = field(default_factory=list)
    need_user_clarification: bool = False
    user_question: str = ""
    note: str = ""


@dataclass
class GraphRAGConfig:
    max_subquestions: int = 3
    parallel_workers: int = 3
    max_iterations: int = 2
    seed_limit: int = 8
    relation_limit: int = 5
    max_depth: int = 3
    width: int = 3
    candidate_event_limit: int = 24
    event_limit_per_subquestion: int = 6
    related_event_limit: int = 12
    evidence_limit: int = 8
    min_llm_relevance: float = 5.0
    use_llm_decomposition: bool = True
    use_llm_relation_prune: bool = True
    use_llm_evidence_scoring: bool = True
    use_llm_reflection: bool = True
    use_llm_answer: bool = True
    use_llm_verification: bool = True


@dataclass
class PipelineResult:
    plan: QuestionPlan
    retrieved_units: List[RetrievalUnit]
    reflections: List[ReflectionStep]
    answer: str
    graph_nodes: List[Dict]
    graph_edges: List[Dict]
    context_text: str
    run_id: str
    log_path: str
