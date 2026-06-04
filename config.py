"""
Neo4j 连接配置 —— 从系统环境变量读取，fallback 到默认值。

环境变量：
  NEO4J_URI      - Neo4j 连接地址，默认 bolt://localhost:7687
  NEO4J_USER     - 用户名，默认 neo4j
  NEO4J_PASSWORD - 密码，默认 neo4j
  NEO4J_DATABASE - 数据库名，默认 my4j
"""

import os

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")
NEO4J_DATABASE = "neo4j"

# ═══════════════════════════════════════════════════════════════
# 本体术语中英文映射（提取自 ontology.ttl）
# ═══════════════════════════════════════════════════════════════

# ── 类名 → 中文标签 ──
CLASS_CN = {
    # 文献
    "Document": "文献",
    "HistoricalDocument": "史学文献",
    "ArchivalDocument": "档案文献",
    # 主体
    "Actor": "主体",
    "Person": "个人",
    "ImperialFamily": "皇室成员",
    "Emperor": "皇帝",
    "EmpressDowager": "太后",
    "Consort": "后妃",
    "ImperialKinsman": "皇室宗亲",
    "Official": "官员",
    "Eunuch": "太监",
    "Artisan": "工匠",
    "GardenKeeper": "园户",
    "OtherPerson": "其他人物",
    # 机构
    "Organization": "机构",
    "InnerCourtAgency": "内廷机构",
    "CentralGovernmentAgency": "中央机构",
    "LocalGovernmentAgency": "地方机构",
    "OtherOrganization": "其他机构",
    # 地点
    "Place": "地点",
    "GardenExteriorPlace": "园外地点",
    "AdministrativeRegion": "行政区域",
    "CapitalRegion": "京师行政区域",
    "ProvincialRegion": "地方行政区域",
    "ImperialGarden": "皇家园林",
    "FunctionalSite": "功能场所",
    "CustomsPort": "关税口岸",
    "MaterialOrigin": "物料产地",
    "OtherFunctionalSite": "其他功能场所",
    "GardenInteriorPlace": "园内地点",
    "ScenicArea": "景区景点",
    "BuildingComplex": "建筑组群",
    "IndividualBuilding": "单体建筑",
    "WaterFeature": "水体",
    "Mountain": "山体",
    # 事件
    "Event": "事件",
    "ConstructionEvent": "营造事件",
    "MaterialEvent": "物料事件",
    "FiscalEvent": "财政事件",
    "AdministrativeDocumentEvent": "行政文书事件",
    "CourtLifeAndCeremonyEvent": "园居与典礼事件",
    "SecurityAndDisorderEvent": "安防与失序事件",
    "PersonnelEvent": "人事事件",
    "GardenHistoryEvent": "园林兴废事件",
    "OtherEvent": "其他事件",
    # 客体
    "Object": "客体",
    "Artifact": "器物",
    "Material": "物料",
    "TransportEquipment": "运具",
    # 事件链
    "EventChain": "事件链",
    # 抽象规范
    "AbstractNorm": "抽象规范",
    "OfficialRank": "品级",
    "OfficialTitle": "职官",
    "Regulation": "规制",
    # 时间
    "TemporalInterval": "时间区间",
    "ChineseCalendarDate": "中历日期",
    "GregorianDate": "公历日期",
}

# ── 对象属性 → 中文标签 ──
OBJECT_PROPERTY_CN = {
    # 事件核心
    "hasAgent": "有施动者",
    "isAgentOf": "是施动者于",
    "hasParticipant": "有参与者",
    "isParticipantIn": "参与于",
    "involvesPlace": "涉及地点",
    "isInvolvedIn": "被涉及于",
    "involvesObject": "涉及客体",
    "isObjectInvolvedIn": "作为客体涉及于",
    # 时空
    "hasTimeSpan": "有时间跨度",
    "fallsWithin": "空间从属",
    "contains": "空间包含",
    # 主体与组织
    "holdsTitle": "担任职官",
    "belongsToOrganization": "隶属于",
    "hasMember": "有成员",
    # 事件间关系
    "consistsOf": "包含子事件",
    "isPartOf": "是子事件于",
    "causes": "导致",
    "isCausedBy": "因之而起",
    "belongsToChain": "属于事件链",
    "chainContains": "事件链包含",
    # 文献溯源
    "isDocumentedIn": "记载于",
    "documents": "记载了",
    "hasSource": "原始出处",
}

# ── 数据属性 → 中文标签 ──
DATA_PROPERTY_CN = {
    "hasName": "名称",
    "hasDescription": "描述",
    "hasDateText": "日期文本",
    "hasDate": "标准日期",
    "hasSourceText": "原始文本",
    "hasRankLevel": "品级数值",
}


def entity_type_cn(entity_type: str) -> str:
    """返回实体类型的中文标签，未知类型直接返回原文"""
    return CLASS_CN.get(entity_type, entity_type)


def event_type_cn(event_type: str) -> str:
    """返回事件类型的中文标签"""
    return CLASS_CN.get(event_type, event_type)


def property_cn(prop: str) -> str:
    """返回属性（对象属性 + 数据属性）的中文标签"""
    if prop in OBJECT_PROPERTY_CN:
        return OBJECT_PROPERTY_CN[prop]
    if prop in DATA_PROPERTY_CN:
        return DATA_PROPERTY_CN[prop]
    return prop