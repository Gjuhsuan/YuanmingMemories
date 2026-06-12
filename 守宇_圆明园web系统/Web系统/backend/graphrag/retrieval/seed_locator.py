"""种子节点定位 —— 词法匹配 + 语义 Embedding 双路召回。"""

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


def _lexical_locate(store, queries: List[str], seed_limit: int) -> Tuple[Set[str], Set[str], Set[str], Dict[str, float]]:
    """词法匹配（保留原有逻辑），额外返回词法得分。"""
    entity_ids: Set[str] = set()
    event_ids: Set[str] = set()
    community_ids: Set[str] = set()
    lex_scores: Dict[str, float] = {}

    for query in queries:
        normalized = normalize_text(query)
        if not normalized:
            continue
        for item_id in store.get("name_index", {}).get(normalized, set()):
            if item_id in store.get("entities", {}):
                entity_ids.add(item_id)
                lex_scores[item_id] = max(lex_scores.get(item_id, 0), 1.0)
            elif item_id in store.get("events", {}):
                event_ids.add(item_id)
                lex_scores[item_id] = max(lex_scores.get(item_id, 0), 1.0)
            elif item_id in store.get("communities", {}):
                community_ids.add(item_id)

        for entity_id, surfaces in store.get("entity_surfaces", {}).items():
            if len(entity_ids) >= seed_limit * 3:
                break
            for surface in surfaces:
                norm_surface = normalize_text(surface)
                if len(norm_surface) >= 2 and (norm_surface in normalized or normalized in norm_surface):
                    entity_ids.add(entity_id)
                    lex_scores[entity_id] = max(lex_scores.get(entity_id, 0), 0.7)
                    break
        for event_id, surfaces in store.get("event_surfaces", {}).items():
            if len(event_ids) >= seed_limit * 3:
                break
            for surface in surfaces:
                norm_surface = normalize_text(surface)
                if len(norm_surface) >= 4 and (norm_surface in normalized or normalized in norm_surface):
                    event_ids.add(event_id)
                    lex_scores[event_id] = max(lex_scores.get(event_id, 0), 0.7)
                    break

    return entity_ids, event_ids, community_ids, lex_scores


def _semantic_locate(store, question_text: str, seed_limit: int) -> Tuple[Set[str], Set[str], Dict[str, float]]:
    """Embedding 语义检索种子节点。"""
    entity_ids: Set[str] = set()
    event_ids: Set[str] = set()
    sem_scores: Dict[str, float] = {}

    emb = getattr(store, "emb_index", None)
    if emb is None or not emb:
        return entity_ids, event_ids, sem_scores

    # 实体语义检索
    for entity_id, score in emb.search_entities(question_text, top_k=seed_limit * 2, min_score=0.35):
        entity_ids.add(entity_id)
        sem_scores[entity_id] = max(sem_scores.get(entity_id, 0), score)

    # 事件语义检索
    for event_id, score in emb.search_events(question_text, top_k=seed_limit * 2, min_score=0.35):
        event_ids.add(event_id)
        sem_scores[event_id] = max(sem_scores.get(event_id, 0), score)

    return entity_ids, event_ids, sem_scores


def _merge_and_rank(
    store,
    lex_entities: Set[str], lex_events: Set[str], lex_communities: Set[str],
    sem_entities: Set[str], sem_events: Set[str],
    lex_scores: Dict[str, float], sem_scores: Dict[str, float],
    seed_limit: int,
) -> Tuple[Set[str], Set[str], Set[str]]:
    """融合词法+语义种子，综合排序。"""

    # 融合实体：词法命中 + 语义命中
    all_entities = lex_entities | sem_entities
    # 融合事件
    all_events = lex_events | sem_events

    # 综合得分：词法 0.6 + 语义 0.4（语义权重更高因为精度更好）
    def entity_score(eid: str) -> float:
        lex = lex_scores.get(eid, 0)
        sem = sem_scores.get(eid, 0)
        # 语义主导（×0.9），词法仅作微弱信号（×0.1）
        # 热门实体惩罚：连接事件越多，得分略微降低（避免 hub 霸占）
        hub_penalty = 1.0 / (1.0 + len(store.get("entity_to_events", {}).get(eid, set())) * 0.02)
        return lex * 0.1 + sem * 0.9 * hub_penalty

    def event_score(eid: str) -> float:
        lex = lex_scores.get(eid, 0)
        sem = sem_scores.get(eid, 0)
        # 语义权重 0.9，词法仅 0.1
        return lex * 0.1 + sem * 0.9

    ranked_entities = sorted(all_entities, key=entity_score, reverse=True)[:seed_limit]
    ranked_events = sorted(all_events, key=event_score, reverse=True)[:seed_limit]
    communities = set(list(lex_communities)[:seed_limit])

    return set(ranked_entities), set(ranked_events), communities


def locate_seed_nodes(store, seed_queries: List[str], question_text: str, seed_limit: int) -> Tuple[Set[str], Set[str], Set[str]]:
    """双路召回种子节点：词法 + Embedding 语义。"""

    queries = _unique(seed_queries + [question_text], limit=30)

    # 路 1: 词法匹配
    lex_entities, lex_events, lex_communities, lex_scores = _lexical_locate(store, queries, seed_limit)

    # 路 2: Embedding 语义检索
    sem_entities, sem_events, sem_scores = _semantic_locate(store, question_text, seed_limit)

    # 融合
    return _merge_and_rank(
        store,
        lex_entities, lex_events, lex_communities,
        sem_entities, sem_events,
        lex_scores, sem_scores,
        seed_limit,
    )


def lexical_event_candidates(store, text: str, limit: int) -> Dict[str, float]:
    """词法兜底 + 语义增强的事件候选。"""
    # 词法 n-gram 得分
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

    # 语义增强
    emb = getattr(store, "emb_index", None)
    if emb is not None and emb:
        for event_id, sem_score in emb.search_events(text, top_k=limit, min_score=0.3):
            scores[event_id] = max(scores.get(event_id, 0), sem_score * 3.0)

    return dict(sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit])
