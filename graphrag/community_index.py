"""这个文件负责构建图谱中的主题社区索引。"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple


PLACE_TYPE_TOKENS = ("place", "building", "site", "region", "location")


def _safe_name(value: str, fallback: str) -> str:
    value = (value or "").strip()
    return value if value else fallback


def _add_membership(
    communities: Dict[str, Dict],
    community_to_events: Dict[str, List[str]],
    event_to_communities: Dict[str, List[str]],
    event_id: str,
    community_id: str,
    name: str,
    kind: str,
) -> None:
    if not event_id or not community_id:
        return
    communities.setdefault(
        community_id,
        {
            "community_id": community_id,
            "name": name,
            "kind": kind,
            "summary": "",
        },
    )
    if event_id not in community_to_events[community_id]:
        community_to_events[community_id].append(event_id)
    if community_id not in event_to_communities[event_id]:
        event_to_communities[event_id].append(community_id)


def _event_place_entities(store: Dict, event_id: str) -> Iterable[Tuple[str, str]]:
    for entity_id in store.get("event_to_entities", {}).get(event_id, set()):
        entity = store.get("entities", {}).get(entity_id, {})
        entity_type = entity.get("entity_type", "").lower()
        if any(token in entity_type for token in PLACE_TYPE_TOKENS):
            yield entity_id, entity.get("name", entity_id)


def build_communities(store: Dict) -> None:
    """Build schema-derived communities only.

    This intentionally avoids domain-keyword communities such as manually defined
    topic tags. The communities here are structural/schema abstractions that can
    be safely used as retrieval candidates, while query-specific pruning is left
    to the LLM agent.
    """

    communities: Dict[str, Dict] = {}
    community_to_events = defaultdict(list)
    event_to_communities = defaultdict(list)

    for event_id, event in store.get("events", {}).items():
        event_type = _safe_name(event.get("event_type", ""), "UnknownEvent")
        _add_membership(
            communities,
            community_to_events,
            event_to_communities,
            event_id,
            f"type::{event_type}",
            event_type,
            "event_type",
        )

        doc_id = event.get("doc_id", "")
        if doc_id:
            title = store.get("entries", {}).get(doc_id, {}).get("title", doc_id)
            _add_membership(
                communities,
                community_to_events,
                event_to_communities,
                event_id,
                f"doc::{doc_id}",
                title,
                "document",
            )

        date_text = (event.get("date_text", "") or "").strip()
        if date_text:
            _add_membership(
                communities,
                community_to_events,
                event_to_communities,
                event_id,
                f"time_text::{date_text}",
                date_text,
                "time_text",
            )

        for entity_id, place_name in list(_event_place_entities(store, event_id))[:3]:
            _add_membership(
                communities,
                community_to_events,
                event_to_communities,
                event_id,
                f"place::{entity_id}",
                place_name,
                "place_entity",
            )

        relation_types = {
            rel.get("relation_type", "")
            for rel in store.get("event_relations", {}).get(event_id, [])
            if rel.get("relation_type")
        }
        for relation_type in sorted(relation_types):
            _add_membership(
                communities,
                community_to_events,
                event_to_communities,
                event_id,
                f"relation::{relation_type}",
                relation_type,
                "relation_type",
            )

    store["communities"] = communities
    store["community_to_events"] = community_to_events
    store["event_to_communities"] = event_to_communities
