"""
度数/重要度计算与节点尺寸映射。

算法严格按 CLAUDE.md 附录 B 实现：
  平方根压缩 + 95百分位截顶 + 线性映射到 18-46px 直径。
"""
import math
import time
from typing import Optional

from ..db import execute_read, execute_read_tx

# ── 缓存 ──
_global_degree_cache: Optional[dict[str, int]] = None
_global_degree_ts: float = 0.0
_CACHE_TTL = 300  # 5 分钟


def compute_subgraph_degrees(
    nodes: list[dict],
    edges: list[dict],
    degree_mode: str = "total"
) -> dict[str, int]:
    """
    在内存中计算子图各节点的度数。
    degree_mode: total / in / out
    """
    degrees: dict[str, int] = {n["id"]: 0 for n in nodes}

    for edge in edges:
        src = edge["source"]
        tgt = edge["target"]
        if degree_mode in ("total", "out") and src in degrees:
            degrees[src] += 1
        if degree_mode in ("total", "in") and tgt in degrees:
            degrees[tgt] += 1

    return degrees


def compute_node_sizes(degrees: dict[str, int]) -> dict[str, dict]:
    """
    根据度数计算节点尺寸与标签字号。

    返回 { node_id: {"size": float, "degree": int} }

    算法：95百分位截顶 → sqrt → 线性映射 [18, 46]
    """
    if not degrees:
        return {}

    vals = list(degrees.values())
    n = len(vals)
    sorted_vals = sorted(vals)
    idx_95 = min(int(n * 0.95), n - 1)
    d_cap = sorted_vals[idx_95]

    # sqrt 压缩
    s_vals = {}
    for nid, d in degrees.items():
        d_capped = min(d, d_cap)
        s_vals[nid] = math.sqrt(max(d_capped, 0))

    s_list = list(s_vals.values())
    s_min, s_max = min(s_list), max(s_list)

    S_MIN, S_MAX = 26.0, 58.0

    results = {}
    for nid, s in s_vals.items():
        if s_max == s_min:
            size = (S_MIN + S_MAX) / 2.0
        else:
            size = S_MIN + (S_MAX - S_MIN) * (s - s_min) / (s_max - s_min)
        results[nid] = {
            "size": round(size, 1),
            "degree": degrees[nid],
        }
    return results


def compute_font_size(node_size: float) -> int:
    """fontSize = clamp(round(size * 0.28), 10, 14)"""
    return max(10, min(14, round(node_size * 0.28)))


def get_global_degrees() -> dict[str, int]:
    """
    获取全局节点度数（度中心性）。
    带 5 分钟进程内缓存。
    返回 { node_id: degree }
    """
    global _global_degree_cache, _global_degree_ts

    now = time.time()
    if _global_degree_cache is not None and (now - _global_degree_ts) < _CACHE_TTL:
        return _global_degree_cache

    query = "MATCH (n)-[r]-() RETURN n.event_id AS nid, n.entity_id AS eid, count(r) AS deg"
    records = execute_read(query)

    degrees = {}
    for rec in records:
        nid = rec.get("nid") or rec.get("eid") or ""
        if nid:
            degrees[nid] = rec.get("deg", 0)

    _global_degree_cache = degrees
    _global_degree_ts = now
    return degrees


def get_global_top_nodes(limit: int = 10) -> list[dict]:
    """
    返回全局 Top-N 重要节点（按度中心性排序）。
    """
    degrees = get_global_degrees()
    sorted_items = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:limit]

    # 批量查询节点基本信息
    top = []
    for nid, deg in sorted_items:
        query = """
        MATCH (n)
        WHERE n.event_id = $nid OR n.entity_id = $nid
        RETURN n, labels(n) AS labels, n.name AS name,
               COALESCE(n.entity_type_cn, n.event_type_cn, '') AS subtype_cn
        LIMIT 1
        """
        recs = execute_read(query, {"nid": nid})
        if recs:
            rec = recs[0]
            labels = rec.get("labels", [])
            label = _top_label(labels)
            from .palette import get_node_color
            top.append({
                "id": nid,
                "name": rec.get("name", ""),
                "label": label,
                "type_cn": _label_cn(label),
                "subtype_cn": rec.get("subtype_cn", ""),
                "degree": deg,
                "color": get_node_color(label),
            })

    return top


def _top_label(labels: list[str]) -> str:
    priority = [
        "Event", "Person", "Place", "Organization", "Object",
        "Document", "AbstractNorm", "TemporalInterval",
    ]
    for p in priority:
        if p in labels:
            return p
    return labels[0] if labels else "Unknown"


def _label_cn(label: str) -> str:
    from ..config import CLASS_CN
    return CLASS_CN.get(label, label)
