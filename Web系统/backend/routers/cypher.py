"""
Cypher 只读检索代理路由。
"""
import time
from fastapi import APIRouter, HTTPException
from ..db import execute_read_tx
from ..services.guard import validate_cypher
from ..services.shaper import shape_node, shape_edge
from ..schemas import CypherRequest, CypherResponse, GraphPayload

router = APIRouter(prefix="/api")

MAX_RESULT_SIZE = 2000  # 节点+边总数上限


@router.post("/cypher", response_model=CypherResponse)
async def execute_cypher(body: CypherRequest):
    """
    执行只读 Cypher 查询。返回 graph（抽取节点/边渲染）和/或 table（标量列）。
    """
    # 1. 安全校验
    validation = validate_cypher(body.query)
    if not validation["valid"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "BAD_CYPHER",
                    "message": validation["error"],
                }
            },
        )

    safe_query = validation["query"]
    t0 = time.time()

    try:
        records = execute_read_tx(safe_query)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "BAD_CYPHER",
                    "message": f"查询执行错误：{str(e)}",
                }
            },
        )

    took_ms = int((time.time() - t0) * 1000)

    # 2. 解析结果：抽取 Node / Relationship → graph；标量 → table
    nodes_map: dict[str, dict] = {}
    edges_map: dict[str, dict] = {}
    table_rows: list[list] = []
    table_columns: list[str] | None = None

    if records:
        # 构建列名
        if hasattr(records[0], 'keys'):
            table_columns = list(records[0].keys())

        for rec in records:
            row_values = []
            for k in table_columns or []:
                val = rec.get(k)
                if hasattr(val, 'labels'):  # Neo4j Node
                    shaped = shape_node(val)
                    nid = shaped["id"]
                    if nid not in nodes_map:
                        nodes_map[nid] = shaped
                    row_values.append(shaped["name"])
                elif hasattr(val, 'type'):  # Neo4j Relationship
                    shaped = shape_edge(val)
                    eid = shaped["id"]
                    if eid not in edges_map:
                        edges_map[eid] = shaped
                    row_values.append(shaped["type_cn"])
                elif isinstance(val, list):
                    # 解析列表中的 Node/Rel
                    sub_vals = []
                    for item in val:
                        if hasattr(item, 'labels'):
                            shaped = shape_node(item)
                            nid = shaped["id"]
                            if nid not in nodes_map:
                                nodes_map[nid] = shaped
                            sub_vals.append(shaped["name"])
                        elif hasattr(item, 'type'):
                            shaped = shape_edge(item)
                            eid = shaped["id"]
                            if eid not in edges_map:
                                edges_map[eid] = shaped
                            sub_vals.append(shaped["type_cn"])
                        else:
                            sub_vals.append(str(item))
                    row_values.append(", ".join(sub_vals))
                else:
                    row_values.append(str(val) if val is not None else "")
            table_rows.append(row_values)

    # 截断
    total_graph = len(nodes_map) + len(edges_map)
    truncated = total_graph > MAX_RESULT_SIZE
    if truncated:
        # 简单截断：保留前 MAX_RESULT_SIZE 个
        node_list = list(nodes_map.values())[:MAX_RESULT_SIZE]
        nodes_map = {n["id"]: n for n in node_list}

    graph = None
    if nodes_map:
        graph = GraphPayload(
            nodes=list(nodes_map.values()),
            edges=list(edges_map.values()),
            meta={},
        )

    table = None
    if table_columns and table_rows:
        table = {"columns": table_columns, "rows": table_rows}

    return CypherResponse(
        graph=graph,
        table=table,
        meta={
            "rowCount": len(table_rows),
            "tookMs": took_ms,
            "truncated": truncated,
        },
    )
