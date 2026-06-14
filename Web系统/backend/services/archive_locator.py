"""
档案页面定位器：给定 sourceText，返回最佳匹配的 PDF 页码。
"""
import json
import re
import os
from pathlib import Path
from typing import Optional

# 数据文件路径
_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "archive_pages"
_ENTRY_MAP_FILE = _DATA_DIR / "entry_page_map.json"
_PAGES_FILE = _DATA_DIR / "pages_simplified.jsonl"

# 全局缓存
_entry_page_map: dict = {}
_pages: dict = {}
_loaded = False


def _load_data():
    """懒加载匹配数据。"""
    global _entry_page_map, _pages, _loaded
    if _loaded:
        return

    if _ENTRY_MAP_FILE.exists():
        with open(_ENTRY_MAP_FILE, 'r', encoding='utf-8') as f:
            _entry_page_map.update(json.load(f))

    if _PAGES_FILE.exists():
        with open(_PAGES_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                rec = json.loads(line)
                _pages[rec["page"]] = rec["text"]

    _loaded = True


def _clean_text(text: str) -> str:
    """与 step3 保持一致的文本清洗。"""
    text = re.sub(r'[（(][上下中]略[）)]', '', text)
    text = re.sub(r'\s+', '', text)
    # 只保留：CJK、字母、数字
    text = re.sub(r'[^一-鿿㐀-䶿a-zA-Z0-9]', '', text)
    return text


def _char_ngrams(text: str, n: int = 3) -> set:
    if len(text) < n:
        return {text}
    return {text[i:i+n] for i in range(len(text) - n + 1)}


def _match_score(query: str, target: str) -> float:
    q_grams = _char_ngrams(query, 3)
    t_grams = _char_ngrams(target, 3)
    if not q_grams or not t_grams:
        return 0.0
    overlap = q_grams & t_grams
    return len(overlap) / len(q_grams)


def locate_page(source_text: str) -> Optional[int]:
    """
    给定 sourceText，返回最佳匹配的页码。
    先查预计算映射（entry_page_map），再做实时匹配作为兜底。
    """
    _load_data()

    if not source_text or not source_text.strip():
        return None

    query_clean = _clean_text(source_text)
    if len(query_clean) < 10:
        return None

    # 1) 在预计算映射中查找（遍历所有 entry，找文本最接近的）
    best_page = None
    best_score = 0.0

    for entry_id_str, info in _entry_page_map.items():
        if info.get("page") is None:
            continue
        page_num = info["page"]
        page_text = _pages.get(page_num, "")
        page_clean = _clean_text(page_text)
        score = _match_score(query_clean, page_clean)
        if score > best_score:
            best_score = score
            best_page = page_num

    # 2) 如果映射找不到（score 太低），直接扫描所有页
    if best_score < 0.05 and _pages:
        for page_num, page_text in _pages.items():
            page_clean = _clean_text(page_text)
            score = _match_score(query_clean, page_clean)
            if score > best_score:
                best_score = score
                best_page = page_num

    if best_score >= 0.05:
        return best_page
    return None


def get_page_count() -> int:
    """返回总页数。"""
    _load_data()
    return len(_pages)


def get_page_url(page_num: int) -> str:
    """返回指定页的 PNG 访问 URL。"""
    return f"/static/archive/page-{page_num:03d}.png"
