"""
GraphRAG 图底座索引缓存服务 —— 单例模式。

启动时构建一次，之后复用。
"""
import threading
from pathlib import Path
from ..settings import GRAPHRAG_ENTRIES_PATH, GRAPHRAG_STAGE1_PATH, GRAPHRAG_STAGE2_PATH

# 延迟导入，避免循环依赖
_graphrag_index = None
_index_lock = threading.Lock()


def get_graphrag_index():
    """
    获取 GraphRAG 图底座索引（单例）。
    首次调用时从 JSONL 文件构建索引，之后直接返回缓存。
    """
    global _graphrag_index
    if _graphrag_index is not None:
        return _graphrag_index

    with _index_lock:
        if _graphrag_index is not None:
            return _graphrag_index

        from ..graphrag import build_index

        entries_path = str(GRAPHRAG_ENTRIES_PATH)
        stage1_path = str(GRAPHRAG_STAGE1_PATH)
        stage2_path = str(GRAPHRAG_STAGE2_PATH)

        print(f"[graphrag_index] 开始构建图底座索引...")
        print(f"  entries: {entries_path}")
        print(f"  stage1:  {stage1_path}")
        print(f"  stage2:  {stage2_path}")

        _graphrag_index = build_index(
            entries_path=entries_path,
            stage1_path=stage1_path,
            stage2_path=stage2_path,
        )

        event_count = len(_graphrag_index.events)
        entity_count = len(_graphrag_index.entities)
        entry_count = len(_graphrag_index.entries)
        comm_count = len(_graphrag_index.communities)

        print(f"[graphrag_index] 索引构建完成: "
              f"{event_count} events, {entity_count} entities, "
              f"{entry_count} entries, {comm_count} communities")

        return _graphrag_index


def invalidate_index():
    """强制重建索引（数据更新后调用）。"""
    global _graphrag_index
    with _index_lock:
        _graphrag_index = None
        print("[graphrag_index] 索引已失效，下次访问将重建")
