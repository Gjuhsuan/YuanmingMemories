"""这个文件暴露 GraphRAG 包对外使用的核心入口。"""

from .graph import GraphSubstrate, build_graph_substrate
from .model_defs import (
    EvidenceAssessment,
    EvidenceGraph,
    EvidenceSlotState,
    GraphRAGConfig,
    PipelineResult,
    QuestionPlan,
    RelationChoice,
    RelationPolicyItem,
    RetrievalUnit,
    ReflectionStep,
    SearchAction,
    SubQuestion,
    SubgraphUnit,
)
from .graph import build_graph_substrate as build_index
from .runtime.pipeline import run_pipeline

__all__ = [
    "build_graph_substrate",
    "build_index",
    "EvidenceAssessment",
    "EvidenceGraph",
    "EvidenceSlotState",
    "GraphSubstrate",
    "GraphRAGConfig",
    "PipelineResult",
    "QuestionPlan",
    "RelationChoice",
    "RelationPolicyItem",
    "RetrievalUnit",
    "ReflectionStep",
    "SearchAction",
    "SubQuestion",
    "SubgraphUnit",
    "run_pipeline",
]
