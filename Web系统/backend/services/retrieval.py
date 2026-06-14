"""
GraphRAG 检索管线：实体链接 → 子图扩展 → 排序裁剪 → 上下文序列化。

严格按照 CLAUDE.md 第 18.2 节设计。
"""
import time
import math
from typing import Optional

from ..db import execute_read
from .shaper import shape_node, shape_edge
from .palette import get_node_color
from ..settings import RAG_RETRIEVE_TOPK, RAG_HOPS, RAG_MAX_SOURCE_CHARS


def entity_linking(question: str) -> list[dict]:
    """
    ① 实体链接：对问题分词（简易）→ 全文索引 + CONTAINS 兜底 → 候选种子。
    返回 [{"id": ..., "label": ..., "name": ..., "score": ...}]
    """
    # 简易分词：按常见标点/空格拆词，每个词长度 >= 2
    import re
    words = re.split(r'[，。、；：？！\s,\.;:?!]+', question)
    candidates = []

    for w in words:
        w = w.strip()
        if len(w) < 2:
            continue
        # 先用全文索引
        try:
            idx_query = """
            CALL db.index.fulltext.queryNodes('entityName', $term)
            YIELD node, score
            RETURN node, score
            ORDER BY score DESC LIMIT 10
            """
            idx_results = execute_read(idx_query, {"term": w})
            for rec in idx_results:
                node = rec["node"]
                nid = node.get("event_id") or node.get("entity_id", "")
                if nid and not any(c["id"] == nid for c in candidates):
                    candidates.append({
                        "id": nid,
                        "label": _node_label(node),
                        "name": node.get("name", ""),
                        "score": rec.get("score", 0.0),
                        "matched_term": w,
                    })
        except Exception:
            pass

        # CONTAINS 兜底
        try:
            contains_query = """
            MATCH (n) WHERE n.name CONTAINS $term
            RETURN n LIMIT 5
            """
            contains_results = execute_read(contains_query, {"term": w})
            for rec in contains_results:
                node = rec["n"]
                nid = node.get("event_id") or node.get("entity_id", "")
                if nid and not any(c["id"] == nid for c in candidates):
                    candidates.append({
                        "id": nid,
                        "label": _node_label(node),
                        "name": node.get("name", ""),
                        "score": 0.5,
                        "matched_term": w,
                    })
        except Exception:
            pass

    # 按分数排序
    candidates.sort(key=lambda x: x["score"], reverse=True)

    # 兜底：如果候选太少，用汉字 bigram 模糊搜索
    if len(candidates) < 3:
        import re as _re
        chinese_chars = _re.findall(r'[一-鿿]', question)
        bigrams = set()
        for i in range(len(chinese_chars) - 1):
            bigrams.add(chinese_chars[i] + chinese_chars[i+1])
        for bg in list(bigrams)[:10]:
            if len(candidates) >= 15:
                break
            try:
                bg_results = execute_read(
                    "MATCH (n) WHERE n.name CONTAINS $term RETURN n LIMIT 5",
                    {"term": bg}
                )
                for rec in bg_results:
                    node = rec["n"]
                    nid = node.get("event_id") or node.get("entity_id", "")
                    if nid and not any(c["id"] == nid for c in candidates):
                        candidates.append({
                            "id": nid,
                            "label": _node_label(node),
                            "name": node.get("name", ""),
                            "score": 0.3,
                            "matched_term": bg,
                        })
            except Exception:
                pass
        candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:15]  # 最多 15 个种子


def subgraph_expand(seed_ids: list[str], hops: int = 1, topk: int = 40) -> dict:
    """
    ②③④ 合并种子 → 子图扩展（偏事件）→ 排序裁剪 → 返回 graph + 序列化上下文。
    """
    topk = topk or RAG_RETRIEVE_TOPK
    hops = hops or RAG_HOPS
    hops = min(max(hops, 1), 2)

    if not seed_ids:
        return {"graph": {"nodes": [], "edges": []}, "context": "", "seed_ids": []}

    # 先用 1 跳扩展（聚焦事件关联）
    all_nodes: dict[str, dict] = {}
    all_edges: dict[str, dict] = {}
    processed = set()

    # 分批查询种子邻居
    for seed_id in seed_ids:
        if seed_id in processed:
            continue
        processed.add(seed_id)

        # 查询种子节点本身
        seed_query = """
        MATCH (n) WHERE n.event_id = $sid OR n.entity_id = $sid
        RETURN n LIMIT 1
        """
        seed_recs = execute_read(seed_query, {"sid": seed_id})
        for rec in seed_recs:
            node = rec["n"]
            shaped = shape_node(node)
            all_nodes[shaped["id"]] = shaped

        # 1 跳邻居
        neighbor_query = """
        MATCH (n) WHERE n.event_id = $sid OR n.entity_id = $sid
        WITH n LIMIT 1
        OPTIONAL MATCH (n)-[r]-(m)
        RETURN n, r, m
        LIMIT 50
        """
        neighbor_recs = execute_read(neighbor_query, {"sid": seed_id})
        for rec in neighbor_recs:
            if rec.get("r") and rec.get("m"):
                m = rec["m"]
                m_shaped = shape_node(m)
                if m_shaped["id"] not in all_nodes:
                    all_nodes[m_shaped["id"]] = m_shaped

                edge = shape_edge(rec["r"])
                eid = edge["id"]
                if eid not in all_edges:
                    all_edges[eid] = edge

        # 2 跳（仅在 hops >= 2 时）
        if hops >= 2:
            hop2_query = """
            MATCH (n) WHERE n.event_id = $sid OR n.entity_id = $sid
            WITH n LIMIT 1
            MATCH (n)-[r1]-(m1)-[r2]-(m2)
            WHERE NOT (m2.event_id = $sid OR m2.entity_id = $sid)
            RETURN m2 AS node, r2 AS rel
            LIMIT 30
            """
            try:
                hop2_recs = execute_read(hop2_query, {"sid": seed_id})
                for rec in hop2_recs:
                    if rec.get("node"):
                        m2_shaped = shape_node(rec["node"])
                        if m2_shaped["id"] not in all_nodes:
                            all_nodes[m2_shaped["id"]] = m2_shaped
                    if rec.get("rel"):
                        edge = shape_edge(rec["rel"])
                        eid = edge["id"]
                        if eid not in all_edges:
                            all_edges[eid] = edge
            except Exception:
                pass

    # 排序：event 优先 + 度数加权
    node_list = list(all_nodes.values())
    for node in node_list:
        # 简单打分：Event 节点 +2，与种子直连 +3
        score = 0
        if node["label"] == "Event":
            score += 2
        if node["id"] in seed_ids:
            score += 3
        # 度数分的 log
        score += math.log(node.get("degree", 1) + 1)
        node["_score"] = score

    node_list.sort(key=lambda n: n.get("_score", 0), reverse=True)

    # 截断至 topk
    truncated = len(node_list) > topk
    kept_nodes = node_list[:topk]
    kept_ids = {n["id"] for n in kept_nodes}

    # 过滤边
    kept_edges = [
        e for e in all_edges.values()
        if e["source"] in kept_ids and e["target"] in kept_ids
    ]

    # 清理内部字段
    for n in kept_nodes:
        n.pop("_score", None)

    # 序列化上下文
    context_text = serialize_context(kept_nodes, kept_edges)

    return {
        "graph": {"nodes": kept_nodes, "edges": kept_edges},
        "context": context_text,
        "seed_ids": seed_ids,
        "truncated": truncated,
    }


def serialize_context(nodes: list[dict], edges: list[dict]) -> str:
    """
    ⑤ 序列化子图为紧凑中文上下文（喂给 LLM）。
    每条事件生成类似文档块的摘要格式。
    """
    # 按 Event / 实体分组
    events = [n for n in nodes if n["label"] == "Event"]
    entities = [n for n in nodes if n["label"] != "Event"]

    # 构建邻接关系
    adj: dict[str, list[tuple[str, str, str]]] = {}
    for e in edges:
        src, tgt = e["source"], e["target"]
        adj.setdefault(src, []).append((tgt, e["type_cn"], e["type"]))
        adj.setdefault(tgt, []).append((src, e["type_cn"], e["type"]))

    parts = []

    # 事件摘要
    for evt in events:
        neighbors = adj.get(evt["id"], [])
        agents = [n for n_id, cn, t in neighbors for n in nodes
                  if n["id"] == n_id and t == "HAS_AGENT"]
        participants = [n for n_id, cn, t in neighbors for n in nodes
                        if n["id"] == n_id and t == "HAS_PARTICIPANT"]
        places = [n for n_id, cn, t in neighbors for n in nodes
                  if n["id"] == n_id and t == "INVOLVES_PLACE"]
        objects = [n for n_id, cn, t in neighbors for n in nodes
                   if n["id"] == n_id and t == "INVOLVES_OBJECT"]
        documents = [n for n_id, cn, t in neighbors for n in nodes
                     if n["id"] == n_id and t == "IS_DOCUMENTED_IN"]

        source_text = ""
        # 从原始数据获取 source_text（节点详情中可能有）
        # 此处从简，用 name 替代

        evt_text = f"【{evt['id']}｜{evt.get('subtype_cn', '事件')}｜{evt.get('date_text', '日期不详')}】{evt['name']}。"
        if agents:
            evt_text += f"\n  施动者：{'、'.join(a['name'] for a in agents)}；"
        if participants:
            evt_text += f"\n  参与者：{'、'.join(p['name'] for p in participants)}；"
        if places:
            evt_text += f"\n  涉及地点：{'、'.join(p['name'] for p in places)}；"
        if objects:
            evt_text += f"\n  涉及客体：{'、'.join(o['name'] for o in objects)}；"
        if documents:
            evt_text += f"\n  记载于：{'、'.join(d['name'] for d in documents)}；"
        parts.append(evt_text)

    # 实体摘要
    for ent in entities[:10]:  # 最多 10 个实体摘要
        neighbors = adj.get(ent["id"], [])
        related_events = [n for n_id, cn, t in neighbors for n in nodes
                          if n["id"] == n_id and n["label"] == "Event"]
        if related_events:
            ent_text = f"【{ent['id']}｜{ent.get('type_cn', '')}】{ent['name']}。"
            ent_text += f" 关联事件：{'、'.join(e['name'] for e in related_events[:5])}。"
            parts.append(ent_text)

    context = "\n\n".join(parts)
    if not context:
        context = "（未找到相关图谱上下文）"

    return context


def _node_label(node) -> str:
    labels = list(node.labels)
    priority = [
        "Event", "Person", "Place", "Organization", "Object",
        "Document", "AbstractNorm", "TemporalInterval",
    ]
    for p in priority:
        if p in labels:
            return p
    return labels[0] if labels else "Unknown"
