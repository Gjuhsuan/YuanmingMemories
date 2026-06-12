"""
语义 Embedding 索引 —— 用 BGE 中文模型做 dense retrieval。
优先从 ModelScope 加载（国内网络友好），回退到 HuggingFace。
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# 国内网络优先用 ModelScope，回退 HF 镜像
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

_MODEL = None
_MODEL_ID = "BAAI/bge-small-zh-v1.5"


def _get_model():
    """懒加载 embedding 模型。优先 ModelScope → HF。"""
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"[embedding] 加载模型 {_MODEL_ID} ...")

        # 尝试从 ModelScope 加载（国内网络友好）
        try:
            from modelscope import snapshot_download
            local_dir = snapshot_download(
                f"BAAI/{_MODEL_ID.split('/')[-1]}",
                revision="master",
            )
            logger.info(f"[embedding] ModelScope 下载完成: {local_dir}")
            _MODEL = SentenceTransformer(local_dir)
        except Exception as e1:
            logger.warning(f"[embedding] ModelScope 加载失败 ({e1})，尝试 HF mirror...")
            try:
                _MODEL = SentenceTransformer(_MODEL_ID)
            except Exception as e2:
                logger.error(f"[embedding] HF 也失败 ({e2})，无法加载模型")
                raise

        logger.info(f"[embedding] 模型加载完成 dim={_MODEL.get_sentence_embedding_dimension()}")
    return _MODEL


class EmbeddingIndex:
    """
    Dense retrieval 索引。
    items: List[dict]   — 原始条目
    vectors: np.ndarray  — shape (N, dim)，L2 归一化
    """

    def __init__(self):
        self.items: List[dict] = []
        self.vectors: Optional[np.ndarray] = None
        self._id_to_idx: Dict[str, int] = {}

    def add(self, item_id: str, text: str, meta: dict = None):
        self.items.append({"id": item_id, "text": text, "meta": meta or {}})
        self._id_to_idx[item_id] = len(self.items) - 1

    def build(self, batch_size: int = 64):
        if not self.items:
            self.vectors = np.empty((0, 512), dtype=np.float32)
            return

        model = _get_model()
        texts = [item["text"] for item in self.items]
        logger.info(f"[embedding] 编码 {len(texts)} 条文本...")

        vectors = model.encode(
            texts, batch_size=batch_size, show_progress_bar=True,
            normalize_embeddings=True,
        )
        self.vectors = np.asarray(vectors, dtype=np.float32)
        logger.info(f"[embedding] 编码完成 shape={self.vectors.shape}")

    def search(self, query: str, top_k: int = 20) -> List[Tuple[str, float, dict]]:
        if self.vectors is None or len(self.vectors) == 0:
            return []

        model = _get_model()
        q_vec = model.encode([query], normalize_embeddings=True, show_progress_bar=False)
        q_vec = np.asarray(q_vec, dtype=np.float32)
        scores = np.dot(self.vectors, q_vec.T).flatten()

        if top_k >= len(scores):
            top_indices = np.argsort(-scores)
        else:
            top_indices = np.argpartition(-scores, top_k)[:top_k]
            top_indices = top_indices[np.argsort(-scores[top_indices])]

        results = []
        for idx in top_indices:
            item = self.items[idx]
            results.append((item["id"], float(scores[idx]), item["meta"]))
        return results

    def search_events(self, query: str, top_k: int = 20,
                      event_ids: Optional[set] = None,
                      min_score: float = 0.3) -> List[Tuple[str, float]]:
        results = self.search(query, top_k=max(top_k * 3, 60))
        out = []
        for item_id, score, meta in results:
            if score < min_score:
                continue
            if meta.get("type", "") != "event":
                continue
            if event_ids is not None and item_id not in event_ids:
                continue
            out.append((item_id, score))
            if len(out) >= top_k:
                break
        return out

    def search_entities(self, query: str, top_k: int = 20,
                        min_score: float = 0.3) -> List[Tuple[str, float]]:
        results = self.search(query, top_k=max(top_k * 3, 60))
        out = []
        for item_id, score, meta in results:
            if score < min_score:
                continue
            if meta.get("type", "") != "entity":
                continue
            out.append((item_id, score))
            if len(out) >= top_k:
                break
        return out

    def __len__(self):
        return len(self.items)

    def __bool__(self):
        return self.vectors is not None and len(self.vectors) > 0
