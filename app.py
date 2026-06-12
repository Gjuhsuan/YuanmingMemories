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

from config import NEO4J_DATABASE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from graphrag import (
    GraphRAGConfig,
    build_index as build_graphrag_index,
    run_pipeline as run_graphrag_pipeline,
)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
CACHE_FILE = "entry_summaries.json"


# ═══════════════════════════════════════════════════════════════
# 颜色方案
# ═══════════════════════════════════════════════════════════════

LABEL_COLORS = {
    "Event": "#E06C75",
    "Person": "#61AFEF",
    "Organization": "#528BFF",
    "Place": "#98C379",
    "Object": "#E5C07B",
    "Document": "#C678DD",
    "TemporalInterval": "#56B6C2",
    "AbstractNorm": "#D19A66",
    "EventChain": "#ABB2BF",
    "Entity": "#7F8C8D",
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
def load_graphrag_index():
    return build_graphrag_index()


@st.cache_resource
def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ═══════════════════════════════════════════════════════════════
# DeepSeek 总结与缓存
# ═══════════════════════════════════════════════════════════════


def _graph_fingerprint(nodes, edges):
    data = json.dumps(
        {
            "nodes": sorted((n["id"], n["group"]) for n in nodes),
            "edges": sorted((e["from"], e["to"], e.get("label", "")) for e in edges),
        },
        ensure_ascii=False,
    )
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
    """获取或生成档案 AI 总结，结果缓存到本地文件。"""
    if not DEEPSEEK_API_KEY:
        return None

    eid = str(entry["entry_id"])
    fp = _graph_fingerprint(nodes, edges)
    cache = _load_cache()

    if eid in cache and cache[eid].get("fingerprint") == fp:
        return cache[eid].get("summary", "")

    node_lines = []
    for n in nodes[:30]:
        node_lines.append(f"- [{n['group']}] {n.get('label', '')} ({n.get('type_cn', '')})")

    edge_lines = []
    for e in edges[:20]:
        edge_lines.append(f"- {e['from']} → {e['to']} ({e.get('label', '')})")

    prompt = f"""你是一位清代圆明园历史研究专家。请根据档案原文和知识图谱数据，撰写一段约300字的分析总结。

要求：
1. 用一段话概括档案记载的核心事件。
2. 点明涉及的关键人物、机构、地点及其在事件中的角色。
3. 若图谱中有事件间因果或时序关系，请简要说明。
4. 语言简洁、学术化，使用中文，不要编号或列表。

【档案信息】
标题：{entry.get('title', '')}
日期：{entry.get('date', '')}
原文：{entry.get('body', '')[:2500]}

【知识图谱节点摘要】
{chr(10).join(node_lines) if node_lines else '(无)'}

【知识图谱关系摘要】
{chr(10).join(edge_lines) if edge_lines else '(无)'}"""

    try:
        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=json.dumps(
                {
                    "model": "deepseek-v4-flash",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 800,
                    "thinking": {"type": "disabled"},
                }
            ).encode(),
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

    cache[eid] = {"summary": summary, "fingerprint": fp, "title": entry.get("title", "")}
    _save_cache(cache)
    return summary


# ═══════════════════════════════════════════════════════════════
# Neo4j 查询
# ═══════════════════════════════════════════════════════════════


def query_local_graph(driver, doc_id):
    """查与指定 doc_id 关联的 Event 及其一跳邻居。"""
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(
            """
            MATCH (e:Event {doc_id: $doc_id})
            OPTIONAL MATCH (e)-[r]-(n)
            RETURN e, r, n
            LIMIT 200
            """,
            doc_id=str(doc_id),
        )

        nodes = {}
        edges = []
        for record in result:
            _collect_node(nodes, record["e"])
            if record["r"] is not None and record["n"] is not None:
                _collect_node(nodes, record["n"])
                _collect_edge(edges, record["r"], record["e"], record["n"])
        return list(nodes.values()), edges


def query_important_entities(driver, top_n=25):
    """返回连接度最高的实体（非 Event）。"""
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(
            """
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
            """,
            top_n=top_n,
        )
        return [dict(r) for r in result]


def query_ego_network(driver, entity_id, max_nodes=200):
    """以指定实体为中心，取两跳 ego network。"""
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(
            """
            MATCH (center {entity_id: $eid})
            OPTIONAL MATCH (center)-[r]-(n1)
            RETURN center, r, n1
            """,
            eid=entity_id,
        )

        nodes = {}
        edges = []
        for record in result:
            _collect_node(nodes, record["center"])
            if record["r"] is not None and record["n1"] is not None:
                _collect_node(nodes, record["n1"])
                _collect_edge(edges, record["r"], record["center"], record["n1"])

        one_hop_ids = [nid for nid in nodes if nid != entity_id][:6]
        if one_hop_ids:
            result2 = session.run(
                """
                MATCH (n1)-[r2]-(n2)
                WHERE n1.entity_id IN $ids
                  AND NOT n2.entity_id IN $exclude
                RETURN n1, r2, n2
                LIMIT $lim
                """,
                ids=one_hop_ids,
                exclude=list(nodes.keys()),
                lim=max_nodes,
            )
            for record in result2:
                if record["r2"] is not None and record["n2"] is not None:
                    _collect_node(nodes, record["n2"])
                    _collect_edge(edges, record["r2"], record["n1"], record["n2"])

        return list(nodes.values()), edges


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
    edges_list.append({"from": from_id, "to": to_id, "label": rel_name})


# ═══════════════════════════════════════════════════════════════
# PyVis 网络图生成
# ═══════════════════════════════════════════════════════════════


def render_legend(nodes):
    """生成图例 HTML。"""
    groups = sorted({n["group"] for n in nodes})
    parts = []
    for g in groups:
        color = LABEL_COLORS.get(g, "#ABB2BF")
        parts.append(
            '<span style="display:inline-block;margin-right:14px">'
            f'<span style="background:{color};display:inline-block;'
            'width:12px;height:12px;border-radius:50%;margin-right:4px;vertical-align:middle"></span>'
            f"{g}</span>"
        )
    return "".join(parts)


def build_graph_html(nodes, edges, height=500):
    """用 PyVis 生成网络图 HTML 字符串。"""
    if not nodes:
        return "<p style='color:#999;text-align:center;margin-top:100px'>暂无图谱数据</p>"

    net = Network(height=f"{height}px", width="100%", directed=True, notebook=False)

    for n in nodes:
        color = LABEL_COLORS.get(n["group"], "#ABB2BF")
        label = n.get("label", n["id"])[:10]
        net.add_node(
            n["id"],
            label=label,
            title=f"{n.get('type_cn', '')}<br>{n['id']}",
            color=color,
            size=28,
            shape="dot",
            font={
                "size": 14,
                "color": "#333",
                "face": "Microsoft YaHei",
                "background": "rgba(255,255,255,0.85)",
                "strokeWidth": 0,
            },
        )

    for e in edges:
        net.add_edge(
            e["from"],
            e["to"],
            title=e.get("label", ""),
            label=e.get("label", "")[:10],
        )

    net.set_options(
        """
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
        """
    )

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        tmp_path = f.name
    try:
        net.save_graph(tmp_path)
        with open(tmp_path, encoding="utf-8") as f:
            html = f.read()
    finally:
        os.unlink(tmp_path)
    return html


TASK_TYPE_LABELS = {
    "event_overview": "事件综述",
    "timeline": "时间线问答",
    "entity_aggregation": "实体聚合",
    "attribute_lookup": "属性查找",
    "graph_qa": "图谱问答",
    "overview": "主题概览",
}


def _task_type_label(task_type):
    return TASK_TYPE_LABELS.get(task_type, task_type or "图谱问答")


def _support_level_priority(level):
    mapping = {"direct": 3, "indirect": 2, "background": 1}
    return mapping.get((level or "").strip().lower(), 0)


def _collect_support_rows(index, result, limit=6):
    best_by_event = {}
    events = index.get("events", {})
    entries = index.get("entries", {})

    for unit in result.retrieved_units:
        for assessment in unit.evidence_assessments:
            if not assessment.keep:
                continue
            priority = _support_level_priority(assessment.support_level)
            if priority <= 0:
                continue
            event_id = assessment.event_id
            score = (priority, float(assessment.relevance or 0.0), float(assessment.necessity or 0.0))
            prev = best_by_event.get(event_id)
            if prev and prev["score"] >= score:
                continue

            event = events.get(event_id, {})
            doc = entries.get(event.get("doc_id", ""), {})
            slot_texts = []
            for key, values in (assessment.slots or {}).items():
                if not values:
                    continue
                slot_texts.append(f"{key}: {'、'.join(values[:2])}")
                if len(slot_texts) >= 2:
                    break
            reason = (assessment.reason or "").strip()
            if not reason and assessment.claims:
                reason = "；".join(assessment.claims[:2])
            best_by_event[event_id] = {
                "score": score,
                "event_id": event_id,
                "event_name": event.get("name", event_id),
                "event_date": event.get("date_text", ""),
                "document_title": doc.get("title", ""),
                "support_level": assessment.support_level,
                "reason": reason or "该事件与问题约束匹配，并提供了直接图谱证据。",
                "slot_summary": "；".join(slot_texts),
            }

    rows = sorted(best_by_event.values(), key=lambda item: item["score"], reverse=True)
    return rows[:limit]


def _build_logic_lines(result, support_rows):
    constraints = []
    if result.plan.time_hints:
        constraints.append("时间：" + "、".join(result.plan.time_hints[:3]))
    if result.plan.place_hints:
        constraints.append("地点：" + "、".join(result.plan.place_hints[:3]))
    if result.plan.entity_hints:
        constraints.append("主体：" + "、".join(result.plan.entity_hints[:4]))
    if result.plan.relation_hints:
        constraints.append("关系：" + "、".join(result.plan.relation_hints[:4]))

    lines = []
    lines.append(
        f"1. 系统先把问题识别为“{_task_type_label(result.plan.task_type)}”，并在图谱中锁定相关约束。"
    )
    if constraints:
        lines.append("2. 本次优先使用的图谱约束是：" + "；".join(constraints) + "。")
    else:
        lines.append("2. 本次主要围绕问题中的核心人物、地点、时期和关系在线索图谱中检索。")

    if support_rows:
        event_names = "、".join(row["event_name"] for row in support_rows[:3])
        lines.append(f"3. 系统最终保留了 {len(support_rows)} 个核心支撑事件，答案主要依据这些事件生成，例如：{event_names}。")
    else:
        lines.append("3. 本次没有找到足够强的支撑事件，因此答案会更保守。")
    return lines


def _render_support_cards(support_rows):
    if not support_rows:
        st.warning("当前没有可展示的强支撑事件，答案可能依赖较弱证据。")
        return

    for idx, row in enumerate(support_rows, start=1):
        title = f"{idx}. {row['event_name']}"
        subtitle_parts = []
        if row["event_date"]:
            subtitle_parts.append(row["event_date"])
        if row["document_title"]:
            subtitle_parts.append(row["document_title"])
        subtitle = " | ".join(subtitle_parts)
        with st.expander(title, expanded=(idx == 1)):
            if subtitle:
                st.caption(subtitle)
            st.write(f"支撑强度：{row['support_level']}")
            st.write(f"证据说明：{row['reason']}")
            if row["slot_summary"]:
                st.write(f"补充信息：{row['slot_summary']}")


def _page_graphrag_user(driver):
    st.header("GraphRAG 问答")
    st.caption("当前版本采用以图谱为中心的问答流程：先定位相关事件与关系，再基于支撑证据生成答案。")

    index = load_graphrag_index()

    with st.sidebar:
        st.subheader("高级设置")
        with st.expander("检索与推理参数", expanded=False):
            subq_limit = st.slider("子问题上限", 1, 4, 3, key="graphrag_agent_subq_limit")
            graph_limit = st.slider("每个子问题主事件数", 2, 6, 4, key="graphrag_agent_event_limit")
            loop_limit = st.slider("反思轮数", 1, 3, 2, key="graphrag_agent_loop_limit")
            use_plan = st.checkbox(
                "启用大模型规划",
                value=bool(DEEPSEEK_API_KEY),
                disabled=not bool(DEEPSEEK_API_KEY),
                key="graphrag_agent_use_plan",
            )
            use_reflection = st.checkbox(
                "启用反思追问",
                value=bool(DEEPSEEK_API_KEY),
                disabled=not bool(DEEPSEEK_API_KEY),
                key="graphrag_agent_use_reflection",
            )
            use_answer = st.checkbox(
                "启用大模型归纳回答",
                value=bool(DEEPSEEK_API_KEY),
                disabled=not bool(DEEPSEEK_API_KEY),
                key="graphrag_agent_use_answer",
            )

    question = st.text_input(
        "输入你的问题",
        placeholder="例如：乾隆时期圆明园发生了哪些大事？",
        key="graphrag2_question",
    )

    if not question.strip():
        st.info("请输入一个与人物、地点、事件或时期相关的问题，系统会基于图谱证据给出回答。")
        return

    config = GraphRAGConfig(
        max_subquestions=subq_limit,
        event_limit_per_subquestion=graph_limit,
        max_iterations=loop_limit,
        use_llm_decomposition=use_plan,
        use_llm_reflection=use_reflection,
        use_llm_answer=use_answer,
    )
    result = run_graphrag_pipeline(index, driver, question, DEEPSEEK_API_KEY, config)

    support_rows = _collect_support_rows(index, result)
    logic_lines = _build_logic_lines(result, support_rows)
    support_docs = sorted({row["document_title"] for row in support_rows if row["document_title"]})
    support_events_count = len({row["event_id"] for row in support_rows})

    st.subheader("最终答案")
    st.info(result.answer)

    m1, m2, m3 = st.columns(3)
    m1.metric("问题类型", _task_type_label(result.plan.task_type))
    m2.metric("核心支撑事件", support_events_count)
    m3.metric("相关档案", len(support_docs))

    c1, c2 = st.columns([1.0, 1.15], gap="large")

    with c1:
        st.markdown("**答案是如何从图谱中得到的**")
        for line in logic_lines:
            st.write(line)

        st.markdown("**关键支撑证据**")
        _render_support_cards(support_rows)

        if support_docs:
            st.markdown("**相关档案来源**")
            for doc_title in support_docs[:6]:
                st.write("- " + doc_title)

    with c2:
        st.markdown("**答案支撑图谱子图**")
        if result.graph_nodes:
            st.markdown(render_legend(result.graph_nodes), unsafe_allow_html=True)
        graph_html = build_graph_html(result.graph_nodes, result.graph_edges, height=560)
        st.components.v1.html(graph_html, height=620, scrolling=False)
        st.caption(
            f"这张图只展示最终答案真正使用到的支撑事件与关联实体 | "
            f"节点 {len(result.graph_nodes)} | 关系 {len(result.graph_edges)}"
        )

    with st.expander("查看技术详情", expanded=False):
        st.caption(f"run_id: {result.run_id} | 日志文件: {result.log_path}")
        st.json(
            {
                "plan_source": result.plan.source,
                "task_type": result.plan.task_type,
                "time_hints": result.plan.time_hints,
                "place_hints": result.plan.place_hints,
                "entity_hints": result.plan.entity_hints,
                "target_slots": result.plan.target_slots,
                "subquestions": [subq.text for subq in result.plan.subquestions],
            }
        )


# ═══════════════════════════════════════════════════════════════
# 页面
# ═══════════════════════════════════════════════════════════════


def page_browse(entries, driver):
    st.header("档案浏览")

    st.sidebar.subheader("搜索档案")
    search = st.sidebar.text_input("输入标题关键词", key="search_entries")

    filtered = entries
    if search:
        filtered = [e for e in entries if search in e.get("title", "")]

    st.sidebar.caption(f"共 {len(filtered)} 条")

    selected_idx = st.sidebar.radio(
        "选择档案",
        options=range(len(filtered)),
        format_func=lambda i: f"[{filtered[i]['entry_id']}] {filtered[i].get('title', '')[:30]}",
        key="entry_radio",
    )

    entry = filtered[selected_idx]
    doc_id = str(entry["entry_id"])
    nodes, edges = query_local_graph(driver, doc_id)

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

    important = query_important_entities(driver, top_n=25)
    if not important:
        st.warning("未找到图谱数据，请先导入数据。")
        return

    options = [(r["eid"], f"{r['name']} ({r.get('type_cn', '')}) — 关联数 {r['degree']}") for r in important]
    selected_eid = st.selectbox(
        "选择一个中心节点（按连接度排序）",
        options=[o[0] for o in options],
        format_func=lambda eid: next((o[1] for o in options if o[0] == eid), eid),
    )

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


def page_graphrag(driver):
    return _page_graphrag_user(driver)

    st.header("GraphRAG 问答")
    st.caption("当前版本采用 agent-driven、graph-first 的问答链路：先做图谱规划，再做种子定位、子图检索、反思追问和证据归纳。")

    index = load_graphrag_index()

    with st.sidebar:
        st.subheader("Agent GraphRAG 设置")
        subq_limit = st.slider("子问题上限", 1, 4, 3, key="graphrag_agent_subq_limit")
        graph_limit = st.slider("每个子问题主事件数", 2, 6, 4, key="graphrag_agent_event_limit")
        loop_limit = st.slider("反思轮数", 1, 3, 2, key="graphrag_agent_loop_limit")
        use_plan = st.checkbox(
            "DeepSeek 图规划",
            value=bool(DEEPSEEK_API_KEY),
            disabled=not bool(DEEPSEEK_API_KEY),
            key="graphrag_agent_use_plan",
        )
        use_reflection = st.checkbox(
            "DeepSeek 反思追问",
            value=bool(DEEPSEEK_API_KEY),
            disabled=not bool(DEEPSEEK_API_KEY),
            key="graphrag_agent_use_reflection",
        )
        use_answer = st.checkbox(
            "DeepSeek 证据归纳回答",
            value=bool(DEEPSEEK_API_KEY),
            disabled=not bool(DEEPSEEK_API_KEY),
            key="graphrag_agent_use_answer",
        )

    question = st.text_input(
        "输入你的问题",
        placeholder="例如：雍正时期圆明园中与木植采办有关的机构和人物有哪些？",
        key="graphrag2_question",
    )

    if not question.strip():
        st.info("先输入一个与人物、地点、事件或时期相关的问题，我们就可以开始检索和扩图。")
        return

    config = GraphRAGConfig(
        max_subquestions=subq_limit,
        event_limit_per_subquestion=graph_limit,
        max_iterations=loop_limit,
        use_llm_decomposition=use_plan,
        use_llm_reflection=use_reflection,
        use_llm_answer=use_answer,
    )
    result = run_graphrag_pipeline(index, driver, question, DEEPSEEK_API_KEY, config)

    st.subheader("回答")
    st.write(result.answer)
    st.caption(f"run_id: {result.run_id} | 日志文件: {result.log_path}")

    with st.expander("图规划", expanded=False):
        st.json(
            {
                "source": result.plan.source,
                "task_type": result.plan.task_type,
                "reasoning_style": result.plan.reasoning_style,
                "target_slots": result.plan.target_slots,
                "entity_hints": result.plan.entity_hints,
                "relation_hints": result.plan.relation_hints,
                "time_hints": result.plan.time_hints,
                "place_hints": result.plan.place_hints,
                "schema_focus": result.plan.schema_focus,
                "subquestions": [
                    {
                        "text": subq.text,
                        "purpose": subq.purpose,
                        "target_types": subq.target_types,
                        "answer_slot": subq.answer_slot,
                    }
                    for subq in result.plan.subquestions
                ],
            }
        )

    st.subheader("检索与图谱过程")
    c1, c2 = st.columns([1.0, 1.15])

    with c1:
        st.markdown("**子问题与子图证据**")
        for idx, unit in enumerate(result.retrieved_units, start=1):
            meta = (
                f"score={round(unit.score, 2)} | "
                f"events={len(unit.event_ids)} | "
                f"entities={len(unit.entity_ids)} | "
                f"docs={len(unit.doc_ids)}"
            )
            with st.expander(f"{idx}. {unit.subquestion}", expanded=(idx == 1)):
                st.caption(meta)
                if unit.purpose:
                    st.write(f"目的：{unit.purpose}")
                if unit.seed_entities:
                    st.write("种子实体：" + "、".join(unit.seed_entities))
                if unit.seed_events:
                    st.write("种子事件：" + "、".join(unit.seed_events))
                if unit.community_hits:
                    st.write("命中社区：" + "、".join(unit.community_hits))
                if unit.path_lines:
                    st.write("路径线索：")
                    for path_line in unit.path_lines[:6]:
                        st.write("  - " + path_line)
                if unit.slot_fills:
                    st.write("已填槽位：")
                    st.json(unit.slot_fills)
                for line in unit.evidence_lines[:8]:
                    st.write("- " + line)

        if result.reflections:
            with st.expander("反思追问", expanded=False):
                st.json(
                    [
                        {
                            "step_index": step.step_index,
                            "enough": step.enough,
                            "missing_slots": step.missing_slots,
                            "missing_aspects": step.missing_aspects,
                            "follow_up_questions": step.follow_up_questions,
                            "note": step.note,
                        }
                        for step in result.reflections
                    ]
                )

        with st.expander("发送给回答模块的上下文", expanded=False):
            st.code(result.context_text, language="text")

    with c2:
        st.markdown("**答案支撑图谱子图**")
        if result.graph_nodes:
            st.markdown(render_legend(result.graph_nodes), unsafe_allow_html=True)
        graph_html = build_graph_html(result.graph_nodes, result.graph_edges, height=560)
        st.components.v1.html(graph_html, height=620, scrolling=False)
        st.caption(
            f"基于最终保留的答案支撑事件生成 | 子问题 {len(result.retrieved_units)} | "
            f"图节点 {len(result.graph_nodes)} | 图关系 {len(result.graph_edges)}"
        )


# ═══════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════


def main():
    st.set_page_config(page_title="圆明园知识图谱", page_icon="", layout="wide")
    st.title("圆明园知识图谱")

    entries = load_entries()
    driver = get_driver()

    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            session.run("RETURN 1").single()
    except Exception as e:
        st.error(f"Neo4j 连接失败: {e}")
        st.stop()

    page = st.sidebar.radio("导航", ["档案浏览", "全局图谱", "GraphRAG 问答"])

    if page == "档案浏览":
        page_browse(entries, driver)
    elif page == "全局图谱":
        page_global(driver)
    else:
        page_graphrag(driver)


if __name__ == "__main__":
    main()
