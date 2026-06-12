#!/usr/bin/env python3
"""
将 stage1_results.jsonl 和 stage2_results.normalized.jsonl 导入 Neo4j 数据库。

系统环境变量：
  NEO4J_URI      - Neo4j 连接地址，默认 bolt://localhost:7687
  NEO4J_USER     - 用户名，默认 neo4j
  NEO4J_PASSWORD - 密码，默认 neo4j
  NEO4J_DATABASE - 数据库名，默认 neo4j

用法:
  python import_to_neo4j.py
  python import_to_neo4j.py --clear              # 导入前清空数据库
  python import_to_neo4j.py --skip-stage1         # 只导入阶段二
  python import_to_neo4j.py --skip-stage2         # 只导入阶段一
  python import_to_neo4j.py --stage1=xxx.jsonl --stage2=yyy.jsonl
"""

import json
import sys
from pathlib import Path

from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE
from config import entity_type_cn, event_type_cn, property_cn

# ── 实体类型 → Neo4j Label 映射 ────────────────────────────────
# 只映射到 ontology.ttl 中的顶层类作为 Neo4j Label，
# 细分子类（如 Emperor、ScenicArea 等）存储在节点的 entity_type 属性中。
ENTITY_TYPE_TO_LABEL = {
    # ── 人物 → Person ──
    "Emperor": "Person",
    "EmpressDowager": "Person",
    "Consort": "Person",
    "ImperialKinsman": "Person",
    "Official": "Person",
    "Eunuch": "Person",
    "Artisan": "Person",
    "GardenKeeper": "Person",
    "OtherPerson": "Person",
    # ── 机构 → Organization ──
    "InnerCourtAgency": "Organization",
    "CentralGovernmentAgency": "Organization",
    "LocalGovernmentAgency": "Organization",
    "OtherOrganization": "Organization",
    # ── 事件（Event 类型不由实体映射，由 stage1 事件单独处理）──
    # ── 事件链 → EventChain ──
    "EventChain": "EventChain",
    # ── 地点 → Place ──
    "GardenInteriorPlace": "Place",
    "ScenicArea": "Place",
    "BuildingComplex": "Place",
    "IndividualBuilding": "Place",
    "WaterFeature": "Place",
    "Mountain": "Place",
    "GardenExteriorPlace": "Place",
    "AdministrativeRegion": "Place",
    "CapitalRegion": "Place",
    "ProvincialRegion": "Place",
    "ImperialGarden": "Place",
    "FunctionalSite": "Place",
    "CustomsPort": "Place",
    "MaterialOrigin": "Place",
    "OtherFunctionalSite": "Place",
    # ── 客体 → Object ──
    "Material": "Object",
    "Artifact": "Object",
    "TransportEquipment": "Object",
    # ── 抽象规范 → AbstractNorm ──
    "OfficialTitle": "AbstractNorm",
    "OfficialRank": "AbstractNorm",
    "Regulation": "AbstractNorm",
    # ── 文献 → Document ──
    "ArchivalDocument": "Document",
    "HistoricalDocument": "Document",
    # ── 时间区间 → TemporalInterval ──
    "ChineseCalendarDate": "TemporalInterval",
    "GregorianDate": "TemporalInterval",
}

EVENT_LABEL = "Event"

# ── 阶段二的关系中，from_id 可能是 event_id（事件）或 entity_id（实体） ──
# Event 的 id 以 "evt_" 开头
def _is_event_id(id_str: str) -> bool:
    return id_str.startswith("evt_")

# 查找任意节点的 Cypher（利用索引）
MATCH_NODE_BY_ID = """
MATCH (n)
WHERE (n.event_id = $_id) OR (n.entity_id = $_id)
RETURN n
"""


def parse_args():
    args = {
        "clear": False,
        "skip_stage1": False,
        "skip_stage2": False,
        "stage1_file": "stage1_results.jsonl",
        "stage2_file": "stage2_results.normalized.jsonl",
    }
    for a in sys.argv[1:]:
        if a == "--clear":
            args["clear"] = True
        elif a == "--skip-stage1":
            args["skip_stage1"] = True
        elif a == "--skip-stage2":
            args["skip_stage2"] = True
        elif a.startswith("--stage1="):
            args["stage1_file"] = a.split("=", 1)[1]
        elif a.startswith("--stage2="):
            args["stage2_file"] = a.split("=", 1)[1]
        elif a in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
    return args


def create_indexes(driver):
    """在导入前创建索引以加速 MERGE 操作"""
    # 9 个顶层 Label（对应 ontology.ttl 顶层类）+ Event
    indexes = [
        ("Event", "event_id"),
        ("Person", "entity_id"),
        ("Organization", "entity_id"),
        ("EventChain", "entity_id"),
        ("Place", "entity_id"),
        ("Object", "entity_id"),
        ("AbstractNorm", "entity_id"),
        ("Document", "entity_id"),
        ("TemporalInterval", "entity_id"),
    ]
    with driver.session(database=NEO4J_DATABASE) as session:
        for label, prop in indexes:
            session.run(f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.{prop})")
    print(f"索引创建完毕 ({len(indexes)} 个)")


def clear_database(driver):
    """清空数据库所有数据（Community Edition 兼容方式）"""
    with driver.session(database=NEO4J_DATABASE) as session:
        # 1. 删除所有索引
        for idx in session.run("SHOW INDEXES").data():
            name = idx.get("name", "")
            if name:
                try:
                    session.run(f"DROP INDEX `{name}`")
                except Exception:
                    pass

        # 2. 删除所有约束
        for c in session.run("SHOW CONSTRAINTS").data():
            name = c.get("name", "")
            if name:
                try:
                    session.run(f"DROP CONSTRAINT `{name}`")
                except Exception:
                    pass

        # 3. 删除所有节点和关系（节点删除后其上 label 也一并清除）
        session.run("MATCH (n) DETACH DELETE n")

    print("数据库已清空 (节点/关系/索引/约束/labels 均已删除; "
          "property keys 在 Community Edition 中无法通过 Cypher 清除，但不影响使用)")


# ═══════════════════════════════════════════════════════════════
# 阶段一：导入事件 (Event)
# ═══════════════════════════════════════════════════════════════

def import_stage1(driver, filepath: str):
    """
    从 stage1 提取 step_4.events_summary，创建 Event 节点。
    """
    filepath = Path(filepath)
    if not filepath.exists():
        print(f"[Stage 1] 文件不存在: {filepath}")
        return

    event_count = 0

    with open(filepath, encoding="utf-8") as f:
        with driver.session(database=NEO4J_DATABASE) as session:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    batch = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"  [警告] 第 {line_no} 行 JSON 解析失败: {e}")
                    continue

                results = batch.get("parsed", {}).get("results", [])
                for doc in results:
                    doc_id = doc.get("doc_id", "")
                    doc_title = doc.get("document_title", "")

                    events = doc.get("step_4", {}).get("events_summary", [])
                    for evt in events:
                        evt_id = evt.get("event_id", "")
                        if not evt_id:
                            continue

                        evt_type = evt.get("event_type", "Event")
                        session.run(
                            f"""
                            MERGE (e:{EVENT_LABEL} {{event_id: $evt_id}})
                            SET e.name = $evt_name,
                                e.event_type = $evt_type,
                                e.event_type_cn = $evt_type_cn,
                                e.source_text = $source_text,
                                e.date_text = $date_text,
                                e.doc_id = $doc_id,
                                e.document_title = $doc_title,
                                e.reasoning = $reasoning,
                                e.uncertainty_note = $uncertainty
                            """,
                            evt_id=evt_id,
                            evt_name=evt.get("event_name", ""),
                            evt_type=evt_type,
                            evt_type_cn=event_type_cn(evt_type),
                            source_text=evt.get("source_text", ""),
                            date_text=evt.get("date_text", ""),
                            doc_id=doc_id,
                            doc_title=doc_title,
                            reasoning=evt.get("reasoning", ""),
                            uncertainty=evt.get("uncertainty_note", ""),
                        )
                        event_count += 1

                    # 同时把 step_1 的 event_name 和 event_type 记录下来
                    # step_1 事件就是 events_summary 中第一个以 doc_id 开头的事件
                    if (line_no % 500 == 0):  # 每 500 行打印一次进度
                        pass

            if event_count > 0:
                print(f"  已导入 {event_count} 个 Event ...")

    print(f"[Stage 1] 导入完成: {event_count} 个 Event 节点")


# ═══════════════════════════════════════════════════════════════
# 阶段二：导入实体与关系
# ═══════════════════════════════════════════════════════════════

def resolve_label(entity_type: str) -> str:
    return ENTITY_TYPE_TO_LABEL.get(entity_type, "Entity")


def import_stage2(driver, filepath: str):
    """
    从 stage2 提取 step_5 数据：
      - final_entities       → 创建实体节点
      - final_entity_attributes → 补充节点属性
      - final_relations      → 创建关系（事件-实体 / 实体-实体 / 事件-事件）
    """
    filepath = Path(filepath)
    if not filepath.exists():
        print(f"[Stage 2] 文件不存在: {filepath}")
        return

    entity_count = 0
    attr_count = 0
    rel_count = 0
    rel_skipped = 0

    with open(filepath, encoding="utf-8") as f:
        with driver.session(database=NEO4J_DATABASE) as session:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    batch = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"  [警告] 第 {line_no} 行 JSON 解析失败: {e}")
                    continue

                results = batch.get("parsed", {}).get("results", [])
                for doc in results:
                    step5 = doc.get("step_5", {})

                    # ── 1. 创建实体节点 ──
                    entities = step5.get("final_entities", [])
                    for ent in entities:
                        eid = ent.get("entity_id", "")
                        if not eid:
                            continue
                        etype = ent.get("entity_type", "")
                        label = resolve_label(etype)

                        session.run(
                            f"""
                            MERGE (n:{label} {{entity_id: $eid}})
                            SET n.name = $name,
                                n.entity_type = $etype,
                                n.entity_type_cn = $etype_cn
                            """,
                            eid=eid,
                            name=ent.get("name", ""),
                            etype=etype,
                            etype_cn=entity_type_cn(etype),
                        )
                        entity_count += 1

                    # ── 2. 补充实体属性 ──
                    attrs = step5.get("final_entity_attributes", [])
                    for attr in attrs:
                        eid = attr.get("entity_id", "")
                        if not eid:
                            continue

                        session.run(
                            """
                            MATCH (n) WHERE n.entity_id = $eid
                            SET n.description = $desc,
                                n.date_text =
                                    CASE WHEN $date_text <> ''
                                    THEN $date_text ELSE n.date_text END,
                                n.date =
                                    CASE WHEN $date <> ''
                                    THEN $date ELSE n.date END,
                                n.source_text =
                                    CASE WHEN $source_text <> ''
                                    THEN $source_text ELSE n.source_text END,
                                n.rank_level = $rank
                            """,
                            eid=eid,
                            desc=attr.get("hasDescription", ""),
                            date_text=attr.get("hasDateText", ""),
                            date=attr.get("hasDate", ""),
                            source_text=attr.get("hasSourceText", ""),
                            rank=attr.get("hasRankLevel"),
                        )
                        attr_count += 1

                    # ── 3. 创建关系 ──
                    # from_id / to_id 可能是 event_id (以 "evt_" 开头) 或 entity_id
                    relations = step5.get("final_relations", [])
                    for rel in relations:
                        from_id = rel.get("from_id", "")
                        to_id = rel.get("to_id", "")
                        rel_type = rel.get("relation_type", "")

                        if not from_id or not to_id or not rel_type:
                            rel_skipped += 1
                            continue

                        safe_rel = _safe_rel_type(rel_type)

                        # 根据 ID 前缀决定匹配属性
                        a_prop = "event_id" if _is_event_id(from_id) else "entity_id"
                        b_prop = "event_id" if _is_event_id(to_id) else "entity_id"

                        ontology_prop = rel.get("ontology_property", "")
                        session.run(
                            f"""
                            MATCH (a) WHERE a.{a_prop} = $from_id
                            MATCH (b) WHERE b.{b_prop} = $to_id
                            MERGE (a)-[r:{safe_rel}]->(b)
                            SET r.evidence = $evidence,
                                r.inference_level = $inference,
                                r.ontology_property = $ontology,
                                r.relation_cn = $relation_cn
                            """,
                            from_id=from_id,
                            to_id=to_id,
                            evidence=rel.get("evidence", ""),
                            inference=rel.get("inference_level", ""),
                            ontology=ontology_prop,
                            relation_cn=property_cn(ontology_prop),
                        )
                        rel_count += 1

            if entity_count > 0:
                print(f"  已导入 {entity_count} 个实体, "
                      f"{rel_count} 条关系 ...")

    print(f"[Stage 2] 导入完成: {entity_count} 个实体, "
          f"{attr_count} 条属性, {rel_count} 条关系")
    if rel_skipped > 0:
        print(f"  (跳过 {rel_skipped} 条缺少字段的关系)")


def _safe_rel_type(rel_type: str) -> str:
    """确保关系类型是合法的 Neo4j 标识符"""
    return rel_type.replace(" ", "_").replace("-", "_")


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def main():
    args = parse_args()

    print(f"连接 Neo4j: {NEO4J_URI}  数据库: {NEO4J_DATABASE}  用户: {NEO4J_USER}")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        # 验证连接
        with driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("RETURN 1 AS ok")
            result.single()
        print("连接成功！")

        clear_database(driver)

        create_indexes(driver)

        if not args["skip_stage1"]:
            print("\n── 阶段一：导入事件 ──")
            import_stage1(driver, args["stage1_file"])

        if not args["skip_stage2"]:
            print("\n── 阶段二：导入实体与关系 ──")
            import_stage2(driver, args["stage2_file"])

        print("\n全部导入完成！")

    except Exception as e:
        print(f"\n[错误] {e}")
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
