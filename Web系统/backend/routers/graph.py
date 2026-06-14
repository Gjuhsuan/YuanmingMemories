"""
图谱域路由：/api/meta、/api/graph、/api/dashboard
"""
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

from ..db import execute_read
from ..services.shaper import shape_node, shape_edge
from ..services.degree import (
    compute_subgraph_degrees,
    compute_node_sizes,
    get_global_top_nodes,
)
from ..services.palette import NODE_COLORS, get_node_color
from ..config import CLASS_CN
from ..schemas import MetaResponse, GraphPayload, DashboardResponse
from ..services import LABEL_CN

router = APIRouter(prefix="/api")


# ── 缓存 ──
_meta_cache: Optional[dict] = None
_dashboard_cache: Optional[dict] = None


# ─────────────────────────────── /api/meta ───────────────────────────────
@router.get("/meta", response_model=MetaResponse)
async def get_meta():
    """返回节点类型、关系类型、事件子类型、总量等元信息。"""
    global _meta_cache
    if _meta_cache:
        return _meta_cache

    # 各 Label 节点数量
    label_counts = {}
    for label in NODE_COLORS:
        result = execute_read(f"MATCH (n:{label}) RETURN count(n) AS cnt")
        label_counts[label] = result[0]["cnt"] if result else 0

    node_types = []
    for label, color in NODE_COLORS.items():
        node_types.append({
            "label": label,
            "cn": CLASS_CN.get(label, label),
            "count": label_counts.get(label, 0),
            "color": color,
            "primary": label == "Event",
        })

    # 关系类型统计
    relation_query = """
    MATCH ()-[r]->() RETURN type(r) AS t, r.relation_cn AS cn, count(r) AS cnt
    ORDER BY cnt DESC
    """
    rel_records = execute_read(relation_query)
    relation_types = [
        {"type": r["t"], "cn": r.get("cn", "") or r["t"], "count": r["cnt"]}
        for r in rel_records
    ]

    # 事件子类型
    event_subtypes_query = """
    MATCH (e:Event) RETURN e.event_type_cn AS cn, count(e) AS cnt ORDER BY cnt DESC
    """
    subtype_records = execute_read(event_subtypes_query)
    event_subtypes = [{"cn": r["cn"] or "未知", "count": r["cnt"]} for r in subtype_records]

    totals = {
        "nodes": sum(label_counts.values()),
        "edges": sum(rt["count"] for rt in relation_types),
    }

    _meta_cache = {
        "nodeTypes": node_types,
        "relationTypes": relation_types,
        "eventSubtypes": event_subtypes,
        "totals": totals,
    }
    return _meta_cache


# ─────────────────────────────── /api/graph ───────────────────────────────
@router.get("/graph", response_model=GraphPayload)
async def get_graph(
    types: str = Query(default="", description="逗号分隔的 Label"),
    limit: int = Query(default=300, description="返回节点数上限"),
    degreeMode: str = Query(default="total", description="total|in|out"),
    centerId: str = Query(default="", description="中心节点ID"),
    hops: int = Query(default=1, description="邻域跳数 1-2"),
):
    """
    获取筛选后的子图数据。
    服务端做类型筛选 + Top-N 截断 + 度数/尺寸计算。
    """
    # 解析类型
    if types:
        allowed_labels = [t.strip() for t in types.split(",") if t.strip() in NODE_COLORS]
    else:
        allowed_labels = list(NODE_COLORS.keys())

    if not allowed_labels:
        raise HTTPException(status_code=400, detail="无效的节点类型")

    # 硬上限
    limit = min(max(limit, 1), 1500)

    # 构建查询
    if centerId:
        hops = min(max(hops, 1), 2)
        label_union = "|".join(allowed_labels)
        # 以 centerId 为中心的 N 跳邻域
        query = f"""
        MATCH (c) WHERE c.event_id = $centerId OR c.entity_id = $centerId
        WITH c LIMIT 1
        MATCH path = (c)-[*1..{hops}]-(m)
        WHERE m:{label_union}
        WITH DISTINCT m, m AS node
        RETURN node, size([(node)-[r]-() WHERE r IS NOT NULL | 1]) AS degree
        """
        records = execute_read(query, {"centerId": centerId})
        # 包含中心节点本身
        center_query = """
        MATCH (c) WHERE c.event_id = $centerId OR c.entity_id = $centerId
        RETURN c AS node
        """
        center_rec = execute_read(center_query, {"centerId": centerId})
        all_records = center_rec + records
    else:
        label_union = "|".join(allowed_labels)
        query = f"""
        MATCH (n:{label_union})
        RETURN n AS node, size([(n)-[r]-() WHERE r IS NOT NULL | 1]) AS degree
        ORDER BY degree DESC
        LIMIT $limit
        """
        all_records = execute_read(query, {"limit": limit})

    # 整形节点
    raw_nodes: list[dict] = []
    node_map: dict[str, dict] = {}
    for rec in all_records:
        node = rec["node"]
        raw_degree = rec.get("degree", 0) if isinstance(rec.get("degree"), int) else 0
        shaped = shape_node(node, degree=raw_degree)
        nid = shaped["id"]
        if nid not in node_map:
            node_map[nid] = shaped
            raw_nodes.append(shaped)

    # 获取这些节点之间的边
    nids = list(node_map.keys())
    edges: list[dict] = []
    edge_set: set = set()
    seen_nids_for_query: set = set()
    # 批量查询边（分段以避免过长参数）
    BATCH = 500
    all_edges_raw = []
    for i in range(0, len(nids), BATCH):
        batch = nids[i:i + BATCH]
        edge_query = """
        UNWIND $ids AS nid
        MATCH (a) WHERE a.event_id = nid OR a.entity_id = nid
        MATCH (a)-[r]-(b)
        WHERE b.event_id IN $ids OR b.entity_id IN $ids
        RETURN a, r, b
        """
        edge_records = execute_read(edge_query, {"ids": batch})
        all_edges_raw.extend(edge_records)

    for rec in all_edges_raw:
        shaped = shape_edge(rec["r"])
        eid = f"{shaped['source']}--{shaped['target']}"
        # 只保留两端都在所选集合内的边
        if shaped["source"] in node_map and shaped["target"] in node_map:
            if eid not in edge_set:
                edge_set.add(eid)
                shaped["id"] = eid
                edges.append(shaped)

    # 在子图内重算度数
    sub_degrees = compute_subgraph_degrees(raw_nodes, edges, degreeMode)
    sizes = compute_node_sizes(sub_degrees)

    # 注入度数 & 尺寸
    for node in raw_nodes:
        nid = node["id"]
        d = sub_degrees.get(nid, 0)
        s = sizes.get(nid, {"size": 24.0, "degree": d})
        node["degree"] = s["degree"]
        node["size"] = s["size"]

    # 按尺寸降序排序，取 Top-N
    raw_nodes.sort(key=lambda n: n["size"], reverse=True)
    total_candidates = len(raw_nodes)
    truncated = total_candidates > limit
    returned = raw_nodes[:limit]
    returned_ids = {n["id"] for n in returned}

    # 过滤边（仅保留返回节点间的边）
    filtered_edges = [e for e in edges if e["source"] in returned_ids and e["target"] in returned_ids]

    return GraphPayload(
        nodes=returned,
        edges=filtered_edges,
        meta={
            "returned": len(returned),
            "truncated": truncated,
            "totalCandidates": total_candidates,
        },
    )


# ─────────────────────────────── /api/dashboard ────────────────────────────
@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard():
    """返回右侧看板所需全部数据。"""
    # 节点数量
    node_counts = []
    for label, color in NODE_COLORS.items():
        result = execute_read(f"MATCH (n:{label}) RETURN count(n) AS cnt")
        cnt = result[0]["cnt"] if result else 0
        node_counts.append({"label": label, "cn": CLASS_CN.get(label, label), "count": cnt, "color": color})

    # 关系数量
    rel_query = """
    MATCH ()-[r]->() RETURN type(r) AS t, r.relation_cn AS cn, count(r) AS cnt ORDER BY cnt DESC
    """
    rel_records = execute_read(rel_query)
    relation_counts = [
        {"type": r["t"], "cn": r.get("cn", "") or r["t"], "count": r["cnt"]}
        for r in rel_records
    ]

    # 事件子类型分布
    subtype_query = """
    MATCH (e:Event) RETURN e.event_type_cn AS cn, count(e) AS cnt ORDER BY cnt DESC
    """
    subtype_records = execute_read(subtype_query)
    event_subtypes = [{"cn": r["cn"] or "未知", "count": r["cnt"]} for r in subtype_records]

    # 总量
    totals = {
        "nodes": sum(nc["count"] for nc in node_counts),
        "edges": sum(rc["count"] for rc in relation_counts),
    }

    # Top 10 重要节点
    top_nodes = get_global_top_nodes(10)

    return DashboardResponse(
        nodeCounts=node_counts,
        relationCounts=relation_counts,
        eventSubtypes=event_subtypes,
        totals=totals,
        topNodes=top_nodes,
        importanceMethod="度中心性",
    )
