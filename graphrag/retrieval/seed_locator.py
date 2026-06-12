"""这个文件负责在图底座中定位问题对应的种子节点。"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Set, Tuple

from ..graph import normalize_text, token_set


def _unique(items: Iterable[str], limit: int | None = None) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if limit and len(out) >= limit:
            break
    return out


def locate_seed_nodes(store, seed_queries: List[str], question_text: str, seed_limit: int) -> Tuple[Set[str], Set[str], Set[str]]:
    entity_ids: Set[str] = set()
    event_ids: Set[str] = set()
    community_ids: Set[str] = set()

    queries = _unique(seed_queries + [question_text], limit=30)
    for query in queries:
        normalized = normalize_text(query)
        if not normalized:
            continue
        for item_id in store.get("name_index", {}).get(normalized, set()):
            if item_id in store.get("entities", {}):
                entity_ids.add(item_id)
            elif item_id in store.get("events", {}):
                event_ids.add(item_id)
            elif item_id in store.get("communities", {}):
                community_ids.add(item_id)

        for entity_id, surfaces in store.get("entity_surfaces", {}).items():
            if len(entity_ids) >= seed_limit * 3:
                break
            for surface in surfaces:
                norm_surface = normalize_text(surface)
                if len(norm_surface) >= 2 and (norm_surface in normalized or normalized in norm_surface):
                    entity_ids.add(entity_id)
                    break
        for event_id, surfaces in store.get("event_surfaces", {}).items():
            if len(event_ids) >= seed_limit * 3:
                break
            for surface in surfaces:
                norm_surface = normalize_text(surface)
                if len(norm_surface) >= 4 and (norm_surface in normalized or normalized in norm_surface):
                    event_ids.add(event_id)
                    break

    entity_ids = set(
        sorted(
            entity_ids,
            key=lambda eid: (
                len(store.get("entity_to_events", {}).get(eid, set())),
                -len(store.get("entities", {}).get(eid, {}).get("name", "")),
            ),
        )[:seed_limit]
    )
    event_ids = set(list(event_ids)[:seed_limit])
    community_ids = set(list(community_ids)[:seed_limit])
    return entity_ids, event_ids, community_ids


def lexical_event_candidates(store, text: str, limit: int) -> Dict[str, float]:
    terms = [term for term in token_set(text, min_ngram=2, max_ngram=4) if len(term) >= 2]
    scores: Dict[str, float] = defaultdict(float)
    for term in terms:
        for item_id in store.get("name_index", {}).get(normalize_text(term), set()):
            if item_id in store.get("events", {}):
                scores[item_id] += 1.0
            elif item_id in store.get("entities", {}):
                for event_id in store.get("entity_to_events", {}).get(item_id, set()):
                    scores[event_id] += 0.8
            elif item_id in store.get("communities", {}):
                for event_id in store.get("community_to_events", {}).get(item_id, [])[:limit]:
                    scores[event_id] += 0.3
    return dict(sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit])
