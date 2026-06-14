"""
Neo4j 记录 → 前端 graph payload 整形。

核心职责：
- 统一 id/idKind（event_id vs entity_id）
- 统一节点/边的 JSON 格式
- 不会丢失 Neo4j 原生属性
"""
from ..config import CLASS_CN
from .palette import get_node_color
from . import LABEL_CN


# Neo4j 实际属性名 → 中文显示名
NEO4J_PROPERTY_CN = {
    "date_text": "日期",
    "doc_id": "档案编号",
    "document_title": "来源档案",
    "source_text": "原始文本",
    "reasoning": "推理说明",
    "uncertainty_note": "不确定性说明",
    "event_id": "事件ID",
    "entity_id": "实体ID",
    "event_type": "事件类型(英)",
    "entity_type": "实体类型(英)",
    "event_type_cn": "事件子类型",
    "entity_type_cn": "实体子类型",
    "name": "名称",
    "hasName": "名称",
    "hasDescription": "描述",
    "hasDateText": "日期文本",
    "hasDate": "标准日期",
    "hasSourceText": "原始文本",
    "hasRankLevel": "品级数值",
    "relation_cn": "关系中文名",
    "comment": "备注",
    "alt_name": "别名",
    "short_name": "简称",
    "pinyin": "拼音",
    "latitude": "纬度",
    "longitude": "经度",
    "start_date": "开始日期",
    "end_date": "结束日期",
    "temporal_scope": "时间范围",
    "description": "描述",
    "edict_date": "上谕日期",
    "memorial_date": "奏折日期",
    "amount": "数额",
    "unit": "单位",
    "material_type": "物料类型",
    "rank": "品级",
    "title_cn": "职官",
    "jurisdiction": "管辖范围",
}


def _node_id(neo4j_node) -> tuple[str, str]:
    """
    返回 (id, idKind)。
    Event 用 event_id，其余实体用 entity_id。
    """
    labels = list(neo4j_node.labels)
    if "Event" in labels and neo4j_node.get("event_id"):
        return neo4j_node["event_id"], "event"
    eid = neo4j_node.get("entity_id", "")
    if eid:
        return eid, "entity"
    # fallback
    return str(neo4j_node.element_id), "entity"


def _node_label(neo4j_node) -> str:
    """取顶层 Label（Event > Person > Place > ...）"""
    labels = list(neo4j_node.labels)
    priority = [
        "Event", "Person", "Place", "Organization", "Object",
        "Document", "AbstractNorm", "TemporalInterval",
    ]
    for p in priority:
        if p in labels:
            return p
    return labels[0] if labels else "Unknown"


def shape_node(neo4j_node, degree: int = 0, size: float = 24.0) -> dict:
    """把单个 Neo4j Node 整形为前端 GraphNode dict。"""
    nid, id_kind = _node_id(neo4j_node)
    label = _node_label(neo4j_node)
    type_cn = LABEL_CN.get(label, label)
    subtype = neo4j_node.get("entity_type_cn") or neo4j_node.get("event_type_cn") or ""
    name = neo4j_node.get("name", "") or ""
    date_text = neo4j_node.get("date_text", "") or ""

    return {
        "id": nid,
        "idKind": id_kind,
        "label": label,
        "type_cn": type_cn,
        "name": name,
        "subtype_cn": subtype,
        "degree": degree,
        "size": size,
        "color": get_node_color(label),
        "date_text": date_text,
        "cited": False,
    }


def shape_edge(neo4j_rel) -> dict:
    """把单个 Neo4j Relationship 整形为前端 GraphEdge dict。"""
    rel_type = neo4j_rel.type
    relation_cn = neo4j_rel.get("relation_cn", "") or ""
    return {
        "id": f"{neo4j_rel.start_node.element_id}->{neo4j_rel.end_node.element_id}",
        "source": _node_id(neo4j_rel.start_node)[0],
        "target": _node_id(neo4j_rel.end_node)[0],
        "type": rel_type,
        "type_cn": relation_cn,
    }


def shape_node_detail(neo4j_node, degree: int = 0) -> dict:
    """
    把单个 Neo4j Node 整形为前端 NodeDetail dict（含全部属性 + sourceText）。
    """
    nid, id_kind = _node_id(neo4j_node)
    label = _node_label(neo4j_node)
    type_cn = LABEL_CN.get(label, label)
    subtype = neo4j_node.get("entity_type_cn") or neo4j_node.get("event_type_cn") or ""
    name = neo4j_node.get("name", "") or ""
    source_text = neo4j_node.get("source_text", "") or ""
    doc_title = neo4j_node.get("document_title", "") or ""

    # 仅过滤这些：已在其他地方显示的 + Neo4j 内部属性
    _skip_keys = {
        "name",   # 已在标题显示
        "event_id", "entity_id",  # 即 id 本身
        "event_type", "entity_type",  # 英文类型，中文已在标签显示
        "event_type_cn", "entity_type_cn",  # 已在副标题显示
        "source_text",  # 下方"原档案文本"专区已展示，不重复
        "element_id",  # Neo4j 内部
    }

    prop_keys = sorted(neo4j_node.keys())
    properties = []
    for k in prop_keys:
        if k in _skip_keys or k.startswith("_"):
            continue
        v = neo4j_node.get(k)
        if v is None or v == "":
            continue  # 空值不显示
        cn = NEO4J_PROPERTY_CN.get(k, k)
        properties.append({"key": k, "cn": cn, "value": str(v)})

    return {
        "id": nid,
        "idKind": id_kind,
        "label": label,
        "type_cn": type_cn,
        "subtype_cn": subtype,
        "name": name,
        "properties": properties,
        "sourceText": source_text,
        "degree": degree,
        "documentTitle": doc_title,
        "images": [],
    }
