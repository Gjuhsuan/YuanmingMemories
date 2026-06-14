"""
预加载缓存端点 —— 将 Top 300 Event 节点预计算并缓存为 JSON。

生成时机：后端启动时。存储在内存 + 可写入 JSON 文件。
"""
import json
import time
from pathlib import Path
from fastapi import APIRouter

from ..db import execute_read
from ..services.shaper import shape_node, shape_edge
from ..services.degree import compute_subgraph_degrees, compute_node_sizes
from ..services.palette import NODE_COLORS

router = APIRouter(prefix="/api")

# 预加载数据缓存
_preload_cache: dict | None = None
_preload_ts: float = 0.0
CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "preload_events.json"


def generate_preload() -> dict:
    """生成预加载数据：Top 300 Event + 关联节点 + 边。"""
    t0 = time.time()

    # 获取度数最高的 300 个 Event
    query = """
    MATCH (e:Event)
    WITH e, size([(e)-[r]-() WHERE r IS NOT NULL | 1]) AS deg
    ORDER BY deg DESC
    LIMIT 300
    RETURN e, deg
    """
    records = execute_read(query)

    node_map: dict[str, dict] = {}
    node_ids: set[str] = set()

    for rec in records:
        node = rec["e"]
        shaped = shape_node(node, degree=rec.get("deg", 0))
        node_map[shaped["id"]] = shaped
        node_ids.add(shaped["id"])

    # 获取这些节点之间的边 + 一跳邻居
    edge_set: set[str] = set()
    edges: list[dict] = []
    neighbor_ids: set[str] = set()

    nid_list = list(node_ids)
    BATCH = 100
    for i in range(0, len(nid_list), BATCH):
        batch = nid_list[i:i + BATCH]
        edge_query = """
        UNWIND $ids AS nid
        MATCH (a) WHERE a.event_id = nid OR a.entity_id = nid
        MATCH (a)-[r]-(b)
        WHERE b.event_id IN $ids OR b.entity_id IN $ids OR b:Event OR b:Person OR b:Place
        RETURN a, r, b
        LIMIT 2000
        """
        edge_records = execute_read(edge_query, {"ids": batch})
        for rec in edge_records:
            # 也加入邻居节点（限 200 个额外节点）
            b_node = rec["b"]
            b_shaped = shape_node(b_node)
            bid = b_shaped["id"]
            if bid not in node_map and len(neighbor_ids) < 200:
                node_map[bid] = b_shaped
                neighbor_ids.add(bid)

            edge = shape_edge(rec["r"])
            eid = f"{edge['source']}--{edge['target']}"
            if eid not in edge_set:
                edge_set.add(eid)
                edges.append(edge)

    all_nodes = list(node_map.values())
    all_node_ids = {n["id"] for n in all_nodes}

    # 过滤边
    filtered_edges = [
        e for e in edges
        if e["source"] in all_node_ids and e["target"] in all_node_ids
    ]

    # 计算子图度数 + 尺寸
    sub_degrees = compute_subgraph_degrees(all_nodes, filtered_edges, "total")
    sizes = compute_node_sizes(sub_degrees)
    for node in all_nodes:
        nid = node["id"]
        s = sizes.get(nid, {"size": 24.0, "degree": 0})
        node["degree"] = s["degree"]
        node["size"] = s["size"]

    elapsed = int((time.time() - t0) * 1000)

    result = {
        "nodes": all_nodes,
        "edges": filtered_edges,
        "generated_at": time.time(),
        "took_ms": elapsed,
    }
    print(f"[preload] 生成预加载数据: {len(all_nodes)} 节点 / {len(filtered_edges)} 边 ({elapsed}ms)")
    return result


def get_preload() -> dict:
    """获取预加载缓存（内存优先，其次 JSON 文件，最后实时生成）。"""
    global _preload_cache, _preload_ts

    # 内存缓存（5 分钟有效）
    now = time.time()
    if _preload_cache and (now - _preload_ts) < 300:
        return _preload_cache

    # JSON 文件缓存
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                _preload_cache = json.load(f)
            _preload_ts = now
            age = _preload_cache.get("generated_at", 0)
            print(f"[preload] 从 JSON 加载: {len(_preload_cache['nodes'])} 节点 (缓存于 {int(now - age)}s 前)")
            return _preload_cache
        except Exception:
            pass

    # 实时生成并缓存
    _preload_cache = generate_preload()
    _preload_ts = now

    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_preload_cache, f, ensure_ascii=False)
        print(f"[preload] 缓存已写入: {CACHE_FILE}")
    except Exception:
        pass

    return _preload_cache


@router.get("/preload")
async def preload():
    """返回预加载的事件图谱数据（快速首屏加载）。"""
    return get_preload()
