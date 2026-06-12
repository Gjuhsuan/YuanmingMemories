"""
Pydantic 响应模型 —— 前端契约的唯一来源。
"""
from __future__ import annotations
from pydantic import BaseModel
from typing import Any, Optional


# ── 通用 ──
class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ── 图谱节点 ──
class GraphNode(BaseModel):
    id: str
    idKind: str           # "event" | "entity"
    label: str            # Event / Person / Place / ...
    type_cn: str          # 中文标签
    name: str
    subtype_cn: str
    degree: int
    size: float
    color: str
    date_text: str = ""
    cited: bool = False   # RAG 引用标记


class GraphEdge(BaseModel):
    id: str               # "source->target"
    source: str
    target: str
    type: str             # 关系类型英文
    type_cn: str          # 中文


class GraphPayload(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    meta: dict[str, Any] = {}


# ── Meta ──
class NodeTypeMeta(BaseModel):
    label: str
    cn: str
    count: int
    color: str
    primary: bool = False


class RelationTypeMeta(BaseModel):
    type: str
    cn: str
    count: int


class SubtypeMeta(BaseModel):
    cn: str
    count: int


class MetaResponse(BaseModel):
    nodeTypes: list[NodeTypeMeta]
    relationTypes: list[RelationTypeMeta]
    eventSubtypes: list[SubtypeMeta]
    totals: dict[str, int]


# ── 节点详情 ──
class PropertyItem(BaseModel):
    key: str
    cn: str
    value: Any


class NodeDetail(BaseModel):
    id: str
    idKind: str
    label: str
    type_cn: str
    subtype_cn: str
    name: str
    properties: list[PropertyItem]
    sourceText: str = ""
    degree: int = 0
    documentTitle: str = ""
    images: list[str] = []       # 预留图片字段


# ── 检索 ──
class SearchResult(BaseModel):
    id: str
    name: str
    label: str
    type_cn: str
    subtype_cn: str
    degree: int
    color: str = ""


class SearchResponse(BaseModel):
    results: list[SearchResult]


# ── Cypher ──
class CypherRequest(BaseModel):
    query: str


class CypherResponse(BaseModel):
    graph: GraphPayload | None = None
    table: dict[str, list] | None = None   # {columns: [...], rows: [[...],]}
    meta: dict[str, Any] = {}


# ── Dashboard ──
class DashboardResponse(BaseModel):
    nodeCounts: list[dict[str, Any]]
    relationCounts: list[dict[str, Any]]
    eventSubtypes: list[dict[str, Any]]
    totals: dict[str, int]
    topNodes: list[dict[str, Any]]
    importanceMethod: str


# ── Chat ──
class ChatMessage(BaseModel):
    role: str          # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    sessionId: Optional[str] = None
    question: str
    pinnedNodeIds: list[str] = []
    history: list[ChatMessage] = []
    options: dict[str, Any] = {}


class ChatRetrieveResponse(BaseModel):
    graph: GraphPayload | None = None
    seeds: list[str] = []
    contextText: str = ""
    tookMs: int = 0
