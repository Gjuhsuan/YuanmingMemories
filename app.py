"""
圆明园知识图谱 — Streamlit 可视化网站
用法: streamlit run app.py
"""

import hashlib
import json
import os
import tempfile
import urllib.request

import streamlit as st
from neo4j import GraphDatabase
from pyvis.network import Network

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
CACHE_FILE = "entry_summaries.json"

# ═══════════════════════════════════════════════════════════════
# 颜色方案
# ═══════════════════════════════════════════════════════════════

LABEL_COLORS = {
    "Event":              "#E06C75",  # 玫红 — 事件
    "Person":             "#61AFEF",  # 蓝 — 人物
    "Organization":       "#528BFF",  # 深蓝 — 机构
    "Place":              "#98C379",  # 绿 — 地点
    "Object":             "#E5C07B",  # 金 — 客体
    "Document":           "#C678DD",  # 紫 — 文献
    "TemporalInterval":   "#56B6C2",  # 青 — 时间
    "AbstractNorm":       "#D19A66",  # 橙 — 抽象规范
    "EventChain":         "#ABB2BF",  # 灰 — 事件链
}


# ═══════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════

@st.cache_data
def load_entries():
    entries = []
    with open("entries_simplified.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


@st.cache_resource
def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ═══════════════════════════════════════════════════════════════
# DeepSeek 总结 与 缓存
# ═══════════════════════════════════════════════════════════════

def _graph_fingerprint(nodes, edges):
    data = json.dumps({
        "nodes": sorted((n["id"], n["group"]) for n in nodes),
        "edges": sorted((e["from"], e["to"], e.get("label", "")) for e in edges),
    }, ensure_ascii=False)
    return hashlib.md5(data.encode()).hexdigest()[:8]


def _load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_or_create_summary(entry, nodes, edges):
    """获取或生成档案 AI 总结（含图谱感知），结果缓存到本地文件"""
    if not DEEPSEEK_API_KEY:
        return None

    eid = str(entry["entry_id"])
    fp = _graph_fingerprint(nodes, edges)
    cache = _load_cache()

    if eid in cache and cache[eid].get("fingerprint") == fp:
        return cache[eid].get("summary", "")

    # 构造提示词
    node_lines = []
    for n in nodes[:30]:
        node_lines.append(
            f"- [{n['group']}] {n.get('label','')} ({n.get('type_cn','')})")
    edge_lines = []
    for e in edges[:20]:
        edge_lines.append(f"- {e['from']} → {e['to']} ({e.get('label','')})")

    prompt = f"""你是一位清代圆明园历史研究专家。请根据档案原文和知识图谱数据，撰写一段约300字的分析总结。

要求：
1. 用一段话概括档案记载的核心事件
2. 点明涉及的关键人物、机构、地点及其在事件中的角色
3. 若图谱中有事件间因果或时序关系，请简要说明
4. 语言简洁、学术化，使用中文；不要编号或列表

【档案信息】
标题：{entry.get('title','')}
日期：{entry.get('date','')}
原文：{entry.get('body','')[:2500]}

【知识图谱节点摘要】
{chr(10).join(node_lines) if node_lines else '(无)'}

【知识图谱关系摘要】
{chr(10).join(edge_lines) if edge_lines else '(无)'}"""

    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=json.dumps({
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 800,
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
        summary = body["choices"][0]["message"]["content"]
    except Exception as e:
        summary = f"(DeepSeek API 调用失败: {e})"

    cache[eid] = {"summary": summary, "fingerprint": fp,
                  "title": entry.get("title", "")}
    _save_cache(cache)
    return summary


# ═══════════════════════════════════════════════════════════════
# Neo4j 查询
# ═══════════════════════════════════════════════════════════════

def query_local_graph(driver, doc_id):
    """查与指定 doc_id 关联的 Event 及其一跳邻居"""
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("""
            MATCH (e:Event {doc_id: $doc_id})
            OPTIONAL MATCH (e)-[r]-(n)
            RETURN e, r, n
            LIMIT 200
        """, doc_id=str(doc_id))

        nodes = {}
        edges = []
        for record in result:
            _collect_node(nodes, record["e"])
            if record["r"] is not None and record["n"] is not None:
                _collect_node(nodes, record["n"])
                _collect_edge(edges, record["r"], record["e"], record["n"])
        return list(nodes.values()), edges


def query_important_entities(driver, top_n=25):
    """返回连接度最高的实体（非 Event）"""
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("""
            MATCH (n)
            WHERE NOT n:Event
            OPTIONAL MATCH (n)--(m)
            WITH n, count(DISTINCT m) AS degree
            ORDER BY degree DESC
            LIMIT $top_n
            RETURN n.entity_id AS eid,
                   n.name AS name,
                   n.entity_type_cn AS type_cn,
                   labels(n) AS lbls,
                   degree
        """, top_n=top_n)
        return [dict(r) for r in result]


def query_ego_network(driver, entity_id, max_nodes=200):
    """以指定实体为中心，取两跳 ego network"""
    with driver.session(database=NEO4J_DATABASE) as session:
        # 一跳
        result = session.run("""
            MATCH (center {entity_id: $eid})
            OPTIONAL MATCH (center)-[r]-(n1)
            RETURN center, r, n1
        """, eid=entity_id)

        nodes = {}
        edges = []
        for record in result:
            _collect_node(nodes, record["center"])
            if record["r"] is not None and record["n1"] is not None:
                _collect_node(nodes, record["n1"])
                _collect_edge(edges, record["r"], record["center"], record["n1"])

        # 二跳（只从连接最多的几个一跳节点扩展）
        one_hop_ids = [nid for nid in nodes if nid != entity_id][:6]
        if one_hop_ids:
            result2 = session.run("""
                MATCH (n1)-[r2]-(n2)
                WHERE n1.entity_id IN $ids
                  AND NOT n2.entity_id IN $exclude
                RETURN n1, r2, n2
                LIMIT $lim
            """, ids=one_hop_ids, exclude=list(nodes.keys()), lim=max_nodes)
            for record in result2:
                if record["r2"] is not None and record["n2"] is not None:
                    _collect_node(nodes, record["n2"])
                    _collect_edge(edges, record["r2"], record["n1"], record["n2"])

        return list(nodes.values()), edges


# ── 辅助 ──

def _id_of(node):
    return node.get("event_id") or node.get("entity_id")


def _label_of(node):
    if node.labels:
        return list(node.labels)[0]
    return "Unknown"


def _name_of(node):
    name = node.get("name") or node.get("event_type_cn") or ""
    return name.strip()


def _collect_node(nodes_dict, node):
    if node is None:
        return
    nid = _id_of(node)
    if not nid or nid in nodes_dict:
        return
    nodes_dict[nid] = {
        "id": nid,
        "label": _name_of(node)[:22] or nid[:22],
        "group": _label_of(node),
        "type_cn": node.get("entity_type_cn") or node.get("event_type_cn") or "",
    }


def _collect_edge(edges_list, rel, from_node, to_node):
    from_id = _id_of(from_node)
    to_id = _id_of(to_node)
    rel_name = rel.get("relation_cn") or rel.type or ""
    edges_list.append({
        "from": from_id,
        "to": to_id,
        "label": rel_name,
    })


# ═══════════════════════════════════════════════════════════════
# PyVis 网络图生成
# ═══════════════════════════════════════════════════════════════

def render_legend(nodes):
    """生成图例 HTML"""
    groups = sorted({n["group"] for n in nodes})
    c = LABEL_COLORS
    parts = []
    for g in groups:
        color = c.get(g, "#ABB2BF")
        parts.append(
            '<span style="display:inline-block;margin-right:14px">'
            f'<span style="background:{color};display:inline-block;'
            'width:12px;height:12px;border-radius:50%;margin-right:4px;vertical-align:middle"></span>'
            f'{g}</span>'
        )
    return "".join(parts)


def build_graph_html(nodes, edges, height=500):
    """用 PyVis 生成网络图 HTML 字符串"""
    if not nodes:
        return "<p style='color:#999;text-align:center;margin-top:100px'>暂无图谱数据</p>"

    net = Network(height=f"{height}px", width="100%",
                  directed=True, notebook=False)
    c = LABEL_COLORS

    for n in nodes:
        color = c.get(n["group"], "#ABB2BF")
        label = n.get("label", n["id"])[:10]
        net.add_node(
            n["id"],
            label=label,
            title=f"{n.get('type_cn','')}<br>{n['id']}",
            color=color,
            size=28,
            shape="dot",
            font={"size": 14, "color": "#333", "face": "Microsoft YaHei",
                  "background": "rgba(255,255,255,0.85)", "strokeWidth": 0},
        )

    for e in edges:
        net.add_edge(
            e["from"], e["to"],
            title=e.get("label", ""),
            label=e.get("label", "")[:10],
        )

    net.set_options("""
    {
      "nodes": {
        "borderWidth": 2,
        "borderWidthSelected": 3,
        "color": { "highlight": { "border": "#333" } }
      },
      "edges": {
        "width": 1.5,
        "color": { "color": "#999", "highlight": "#333", "hover": "#666" },
        "font": { "size": 10, "align": "middle", "color": "#666", "background": "#fff" },
        "smooth": { "type": "continuous" },
        "arrows": { "to": { "enabled": true, "scaleFactor": 0.6 } }
      },
      "physics": {
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
          "gravitationalConstant": -40,
          "centralGravity": 0.005,
          "springLength": 180,
          "springConstant": 0.06,
          "avoidOverlap": 0.3
        },
        "stabilization": { "iterations": 200 }
      },
      "interaction": { "hover": true, "tooltipDelay": 80, "zoomView": true, "dragView": true }
    }
    """)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False,
                                     mode="w", encoding="utf-8") as f:
        tmp_path = f.name
    try:
        net.save_graph(tmp_path)
        with open(tmp_path, encoding="utf-8") as f:
            html = f.read()
    finally:
        os.unlink(tmp_path)
    return html


# ═══════════════════════════════════════════════════════════════
# 页面
# ═══════════════════════════════════════════════════════════════

def page_browse(entries, driver):
    st.header("档案浏览")

    # ── 侧边栏：搜索 + 列表 ──
    st.sidebar.subheader("搜索档案")
    search = st.sidebar.text_input("输入标题关键词", key="search_entries")

    filtered = entries
    if search:
        filtered = [e for e in entries if search in e.get("title", "")]

    st.sidebar.caption(f"共 {len(filtered)} 条")

    # 选择一条
    selected_idx = st.sidebar.radio(
        "选择档案",
        options=range(len(filtered)),
        format_func=lambda i: f"[{filtered[i]['entry_id']}] {filtered[i].get('title','')[:30]}",
        key="entry_radio",
    )

    entry = filtered[selected_idx]
    doc_id = str(entry["entry_id"])
    nodes, edges = query_local_graph(driver, doc_id)

    # ── 主区域：左右分栏 ──
    left, right = st.columns([1, 1.2])

    with left:
        st.subheader(entry.get("title", ""))
        st.caption(f"日期: {entry.get('date', '')}  |  档案 ID: {entry['entry_id']}")
        st.markdown("**原文**")
        st.markdown(
            f"<div style='max-height:350px;overflow-y:auto;padding:12px;"
            f"background:#fafafa;border:1px solid #ddd;border-radius:6px;"
            f"line-height:1.8;white-space:pre-wrap;font-size:14px'>"
            f"{entry.get('body', '')}</div>",
            unsafe_allow_html=True,
        )

        # ── AI 总结 ──
        if DEEPSEEK_API_KEY:
            if st.button("AI 分析总结", key=f"sum_{entry['entry_id']}"):
                with st.spinner("正在调用 DeepSeek 分析图谱与原文 ..."):
                    summary = get_or_create_summary(entry, nodes, edges)
                if summary:
                    st.markdown("**AI 分析总结**")
                    st.info(summary)
            else:
                cache = _load_cache()
                eid = str(entry["entry_id"])
                fp = _graph_fingerprint(nodes, edges)
                if eid in cache and cache[eid].get("fingerprint") == fp:
                    st.markdown("**AI 分析总结**")
                    st.info(cache[eid]["summary"])
        else:
            st.caption("设置 DEEPSEEK_API_KEY 环境变量以启用 AI 总结")

    with right:
        st.markdown("**关联知识图谱**")
        if nodes:
            st.markdown(render_legend(nodes), unsafe_allow_html=True)
        html = build_graph_html(nodes, edges, height=520)
        st.components.v1.html(html, height=580, scrolling=False)

        label_counts = {}
        for n in nodes:
            g = n["group"]
            label_counts[g] = label_counts.get(g, 0) + 1
        stats = "  |  ".join(f"{k}: {v}" for k, v in sorted(label_counts.items()))
        st.caption(f"节点: {len(nodes)}  |  关系: {len(edges)}  |  {stats}")


def page_global(driver):
    st.header("全局图谱")

    # ── 获取重要节点列表 ──
    important = query_important_entities(driver, top_n=25)
    if not important:
        st.warning("未找到图谱数据，请先导入数据。")
        return

    # 下拉选择中心节点
    options = [(r["eid"], f"{r['name']} ({r.get('type_cn','')}) — 关联数 {r['degree']}") for r in important]
    selected_eid = st.selectbox(
        "选择一个中心节点（按连接度排序）",
        options=[o[0] for o in options],
        format_func=lambda eid: next((o[1] for o in options if o[0] == eid), eid),
    )

    # 默认选中 雍正帝 或 圆明园
    if "selected_center" not in st.session_state:
        for r in important:
            if "雍正" in (r.get("name") or ""):
                selected_eid = r["eid"]
                st.session_state["selected_center"] = True
                st.rerun()
            if "圆明园" in (r.get("name") or ""):
                selected_eid = r["eid"]
                st.session_state["selected_center"] = True
                st.rerun()

    if not selected_eid:
        st.stop()

    nodes, edges = query_ego_network(driver, selected_eid)
    st.caption(f"中心节点: {selected_eid}  |  节点: {len(nodes)}  |  关系: {len(edges)}")
    if nodes:
        st.markdown(render_legend(nodes), unsafe_allow_html=True)
    html = build_graph_html(nodes, edges, height=620)
    st.components.v1.html(html, height=680, scrolling=False)


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════

def main():
    st.set_page_config(page_title="圆明园知识图谱", page_icon="", layout="wide")
    st.title("圆明园知识图谱")

    entries = load_entries()
    driver = get_driver()

    # 验证 Neo4j 连接
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            session.run("RETURN 1").single()
    except Exception as e:
        st.error(f"Neo4j 连接失败: {e}")
        st.stop()

    page = st.sidebar.radio("导航", ["档案浏览", "全局图谱"])

    if page == "档案浏览":
        page_browse(entries, driver)
    else:
        page_global(driver)


if __name__ == "__main__":
    main()
