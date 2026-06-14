"""
节点域路由：/api/node/{id}、/api/node/{id}/neighbors、/api/search
"""
from fastapi import APIRouter, Query, HTTPException

from ..db import execute_read
from ..services.shaper import shape_node, shape_edge, shape_node_detail
from ..services.degree import compute_node_sizes
from ..services.palette import NODE_COLORS, get_node_color
from ..config import CLASS_CN
from ..schemas import NodeDetail, SearchResponse, GraphPayload

router = APIRouter(prefix="/api")


# ─────────────────────────────── /api/node/{id} ────────────────────────────
@router.get("/node/{node_id}", response_model=NodeDetail)
async def get_node_detail(node_id: str):
    """获取节点完整详情（左栏数据源），含 sourceText。"""
    query = """
    MATCH (n)
    WHERE n.event_id = $nid OR n.entity_id = $nid
    RETURN n, size([(n)-[r]-() WHERE r IS NOT NULL | 1]) AS degree
    LIMIT 1
    """
    records = execute_read(query, {"nid": node_id})
    if not records:
        raise HTTPException(status_code=404, detail=f"节点 {node_id} 未找到")

    rec = records[0]
    return shape_node_detail(rec["n"], degree=rec.get("degree", 0))


# ─────────────────────────── /api/node/{id}/neighbors ──────────────────────
@router.get("/node/{node_id}/neighbors", response_model=GraphPayload)
async def get_node_neighbors(
    node_id: str,
    limit: int = Query(default=50, description="邻居节点上限"),
):
    """返回中心节点 + 1 跳邻居及连边。"""
    limit = min(max(limit, 1), 200)

    # 获取中心节点
    center_query = """
    MATCH (c) WHERE c.event_id = $nid OR c.entity_id = $nid
    RETURN c
    LIMIT 1
    """
    center_recs = execute_read(center_query, {"nid": node_id})
    if not center_recs:
        raise HTTPException(status_code=404, detail=f"节点 {node_id} 未找到")

    center = center_recs[0]["c"]

    # 获取邻居及度数
    neighbor_query = """
    MATCH (c) WHERE c.event_id = $nid OR c.entity_id = $nid
    WITH c LIMIT 1
    MATCH (c)-[r]-(m)
    RETURN m, type(r) AS rel_type, r.relation_cn AS rel_cn,
           size([(m)-[r2]-() WHERE r2 IS NOT NULL | 1]) AS deg
    """
    records = execute_read(neighbor_query, {"nid": node_id})

    # 整形所有节点
    nodes: list[dict] = []
    node_ids: set = set()
    edges: list[dict] = []

    # 中心节点
    c_shaped = shape_node(center)
    nodes.append(c_shaped)
    node_ids.add(c_shaped["id"])

    # 邻居（按度数截断）
    neighbor_entries = []
    for rec in records:
        m = rec["m"]
        deg = rec.get("deg", 0)
        m_shaped = shape_node(m, degree=deg)
        if m_shaped["id"] not in node_ids:
            neighbor_entries.append((m_shaped, rec.get("rel_cn", ""), deg))

    neighbor_entries.sort(key=lambda x: x[2], reverse=True)
    truncated_neighbors = len(neighbor_entries) > limit
    neighbor_entries = neighbor_entries[:limit]

    for m_shaped, _, _ in neighbor_entries:
        if m_shaped["id"] not in node_ids:
            nodes.append(m_shaped)
            node_ids.add(m_shaped["id"])

    # 边：中心 ↔ 邻居
    edge_set = set()
    for rec in records:
        m = rec["m"]
        m_id = shape_node(m)["id"]
        if m_id in node_ids:
            e = {
                "id": f"{c_shaped['id']}--{m_id}",
                "source": c_shaped["id"],
                "target": m_id,
                "type": rec.get("rel_type", ""),
                "type_cn": rec.get("rel_cn", ""),
            }
            if e["id"] not in edge_set:
                edge_set.add(e["id"])
                edges.append(e)

    # 重算尺寸
    from ..services.degree import compute_subgraph_degrees
    sub_degrees = compute_subgraph_degrees(nodes, edges)
    sizes = compute_node_sizes(sub_degrees)
    for node in nodes:
        nid = node["id"]
        s = sizes.get(nid, {"size": 24.0, "degree": 0})
        node["degree"] = s["degree"]
        node["size"] = s["size"]

    return GraphPayload(
        nodes=nodes,
        edges=edges,
        meta={
            "returned": len(nodes),
            "truncated": truncated_neighbors,
            "totalCandidates": len(node_ids),
        },
    )


# ─────────────────────────────── /api/search ───────────────────────────────
@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., description="搜索关键词"),
    types: str = Query(default="", description="限制搜索的 Label（逗号分隔）"),
    limit: int = Query(default=20),
):
    """关键词检索（按 name CONTAINS），支持自动补全。"""
    limit = min(max(limit, 1), 100)
    q = q.strip()
    if not q:
        return SearchResponse(results=[])

    if types:
        allowed_labels = [t.strip() for t in types.split(",") if t.strip() in NODE_COLORS]
    else:
        allowed_labels = list(NODE_COLORS.keys())

    if not allowed_labels:
        return SearchResponse(results=[])

    label_filter = "|".join(allowed_labels)
    query = f"""
    MATCH (n:{label_filter})
    WHERE n.name CONTAINS $q
    RETURN n, size([(n)-[r]-() WHERE r IS NOT NULL | 1]) AS degree
    ORDER BY degree DESC
    LIMIT $limit
    """
    records = execute_read(query, {"q": q, "limit": limit})

    results = []
    for rec in records:
        node = rec["n"]
        labels = list(node.labels)
        label = _top_label(labels)
        results.append({
            "id": node.get("event_id") or node.get("entity_id", ""),
            "name": node.get("name", ""),
            "label": label,
            "type_cn": CLASS_CN.get(label, label),
            "subtype_cn": node.get("entity_type_cn") or node.get("event_type_cn", ""),
            "degree": rec.get("degree", 0),
            "color": get_node_color(label),
        })

    return SearchResponse(results=results)


def _top_label(labels: list[str]) -> str:
    priority = [
        "Event", "Person", "Place", "Organization", "Object",
        "Document", "AbstractNorm", "TemporalInterval",
    ]
    for p in priority:
        if p in labels:
            return p
    return labels[0] if labels else "Unknown"
