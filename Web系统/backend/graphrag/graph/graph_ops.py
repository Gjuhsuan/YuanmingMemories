"""这个文件提供图谱节点、关系、路径检索等基础图操作。"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set


PUNCT_RE = re.compile(r"[\s,，。；：、！!？?（）()\[\]【】“”\"'·\-]+")


def normalize_text(text: str) -> str:
    return PUNCT_RE.sub("", (text or "").strip().lower())


def token_set(text: str, min_ngram: int = 3, max_ngram: int = 4) -> Set[str]:
    text = (text or "").strip()
    tokens = {seg for seg in re.split(PUNCT_RE, text) if len(seg) >= 2}
    compact = normalize_text(text)
    if compact:
        tokens.add(compact)
        start = max(2, int(min_ngram or 2))
        end = max(start, int(max_ngram or start))
        for size in range(start, end + 1):
            for idx in range(0, max(0, len(compact) - size + 1)):
                tokens.add(compact[idx : idx + size])
    return tokens


def node_name(store, node_id: str) -> str:
    if node_id in store.events:
        return store.events[node_id].get("name", node_id)
    if node_id in store.entities:
        return store.entities[node_id].get("name", node_id)
    if node_id in store.communities:
        return store.communities[node_id].get("name", node_id)
    if node_id.startswith("doc_"):
        doc_id = node_id[4:]
        return store.entries.get(doc_id, {}).get("title", node_id)
    return node_id


def node_kind(store, node_id: str) -> str:
    if node_id in store.events:
        return "Event"
    if node_id in store.entities:
        return store.entities[node_id].get("entity_type", "Entity")
    if node_id in store.communities:
        return f"Community:{store.communities[node_id].get('kind', 'community')}"
    if node_id.startswith("doc_"):
        return "Document"
    return "Unknown"


def relation_between(store, from_id: str, to_id: str) -> str:
    for edge in store.adjacency.get(from_id, []):
        if edge.get("to") == to_id:
            return edge.get("label", "")
    return ""


def format_path(store, path: List[str]) -> str:
    if not path:
        return ""
    parts: List[str] = []
    for idx, node_id in enumerate(path):
        parts.append(node_name(store, node_id))
        if idx < len(path) - 1:
            label = relation_between(store, node_id, path[idx + 1])
            parts.append(f"-[{label}]-")
    return " ".join(parts)


def find_paths(
    store,
    start_ids: Iterable[str],
    goal_ids: Optional[Set[str]] = None,
    goal_kinds: Optional[Set[str]] = None,
    required_terms: Optional[Iterable[str]] = None,
    allowed_relations: Optional[Set[str]] = None,
    max_depth: int = 3,
    max_paths: int = 20,
) -> List[List[str]]:
    start_ids = [node_id for node_id in start_ids if node_id]
    goal_ids = goal_ids or set()
    goal_kinds = goal_kinds or set()
    required_terms = [normalize_text(term) for term in (required_terms or []) if normalize_text(term)]
    allowed_relations = set(allowed_relations or [])
    if not start_ids:
        return []

    paths: List[List[str]] = []
    queue: List[List[str]] = [[node_id] for node_id in start_ids]
    seen_prefixes = set()
    while queue and len(paths) < max_paths:
        path = queue.pop(0)
        current = path[-1]
        prefix_key = tuple(path)
        if prefix_key in seen_prefixes:
            continue
        seen_prefixes.add(prefix_key)

        current_name = normalize_text(node_name(store, current))
        current_kind = node_kind(store, current)
        matched_goal = False
        if current in goal_ids and len(path) > 1:
            matched_goal = True
        elif goal_kinds and current_kind in goal_kinds and len(path) > 1:
            matched_goal = True
        elif required_terms and any(term and term in current_name for term in required_terms) and len(path) > 1:
            matched_goal = True
        if matched_goal:
            paths.append(path)
            continue

        if len(path) - 1 >= max_depth:
            continue
        for edge in store.adjacency.get(current, []):
            label = edge.get("label", "")
            if allowed_relations and label not in allowed_relations:
                continue
            nxt = edge.get("to")
            if not nxt or nxt in path:
                continue
            queue.append(path + [nxt])

    return paths
