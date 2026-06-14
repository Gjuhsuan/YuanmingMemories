"""
Neo4j driver 单例、读事务封装、健康检查、全文索引初始化。
"""
from neo4j import GraphDatabase, Driver

from .settings import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE

_driver: Driver | None = None


def get_driver() -> Driver:
    """获取全局单例 Neo4j driver。"""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
            max_connection_lifetime=3600,
            max_connection_pool_size=20,
        )
    return _driver


def execute_read(query: str, params: dict | None = None, timeout: int = 5):
    """
    执行只读查询，返回 records 列表。
    超时参数通过驱动事务配置控制。
    """
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run(query, parameters=params or {}, timeout=timeout)
        return list(result)


def execute_read_tx(query: str, params: dict | None = None, timeout: int = 5):
    """在 read_transaction 中执行查询（更安全的只读包装）。"""
    driver = get_driver()

    def _tx(tx):
        return list(tx.run(query, parameters=params or {}, timeout=timeout))

    with driver.session(database=NEO4J_DATABASE) as session:
        return session.execute_read(_tx)


def health_check() -> bool:
    """验证 Neo4j 连通性。"""
    try:
        execute_read("RETURN 1 AS ok")
        return True
    except Exception:
        return False


def ensure_fulltext_index():
    """
    确保全文索引存在（用于 RAG 实体链接）。
    索引名: entityName
    覆盖: 所有主 Label 的 name 属性。
    """
    query = """
    CREATE FULLTEXT INDEX entityName IF NOT EXISTS
    FOR (n:Event|Person|Place|Object|Organization|Document|AbstractNorm|TemporalInterval)
    ON EACH [n.name]
    """
    try:
        execute_read(query)
        return True
    except Exception:
        return False


def close():
    """关闭 driver 连接池。"""
    global _driver
    if _driver:
        _driver.close()
        _driver = None
