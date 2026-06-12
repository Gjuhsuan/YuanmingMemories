"""这个文件定义 GraphRAG 中标准化的子图检索单元。"""

from __future__ import annotations

from typing import List

from ..graph import format_path, node_name, relation_between
from ..model_defs import SubgraphUnit


def _edge_key(src: str, dst: str, label: str) -> str:
    return f"{src}|{label}|{dst}"


def make_event_star(store, event_id: str, max_edges: int = 12) -> SubgraphUnit:
    event = store.events.get(event_id, {})
    node_ids = [event_id]
    edge_keys: List[str] = []
    entity_ids: List[str] = []
    doc_ids: List[str] = []

    if event.get("doc_id"):
        doc_node_id = f"doc_{event['doc_id']}"
        node_ids.append(doc_node_id)
        doc_ids.append(event["doc_id"])
        edge_keys.append(_edge_key(event_id, doc_node_id, "IN_DOC"))

    for rel in store.event_relations.get(event_id, [])[:max_edges]:
        to_id = rel.get("to_id", "")
        if not to_id:
            continue
        node_ids.append(to_id)
        if to_id in store.entities:
            entity_ids.append(to_id)
        edge_keys.append(_edge_key(event_id, to_id, rel.get("relation_type", "RELATED_TO")))

    return SubgraphUnit(
        unit_id=f"event_star:{event_id}",
        unit_type="event_star",
        summary=event.get("name", event_id),
        seed_nodes=[event_id],
        node_ids=list(dict.fromkeys(node_ids)),
        edge_keys=edge_keys,
        event_ids=[event_id],
        entity_ids=list(dict.fromkeys(entity_ids)),
        doc_ids=list(dict.fromkeys(doc_ids)),
        metadata={"event_type": event.get("event_type", ""), "date_text": event.get("date_text", "")},
    )


def make_event_path(store, path: List[str]) -> SubgraphUnit:
    edge_keys: List[str] = []
    event_ids: List[str] = []
    entity_ids: List[str] = []
    doc_ids: List[str] = []
    community_ids: List[str] = []

    for idx, node_id in enumerate(path):
        if node_id in store.events:
            event_ids.append(node_id)
            doc_id = store.events[node_id].get("doc_id", "")
            if doc_id:
                doc_ids.append(doc_id)
        elif node_id in store.entities:
            entity_ids.append(node_id)
        elif node_id in store.communities:
            community_ids.append(node_id)
        if idx < len(path) - 1:
            label = relation_between(store, node_id, path[idx + 1])
            edge_keys.append(_edge_key(node_id, path[idx + 1], label))

    return SubgraphUnit(
        unit_id=f"path:{'->'.join(path)}",
        unit_type="event_path",
        summary=format_path(store, path),
        seed_nodes=path[:1],
        node_ids=list(dict.fromkeys(path)),
        edge_keys=edge_keys,
        event_ids=list(dict.fromkeys(event_ids)),
        entity_ids=list(dict.fromkeys(entity_ids)),
        doc_ids=list(dict.fromkeys(doc_ids)),
        community_ids=list(dict.fromkeys(community_ids)),
        path_lines=[format_path(store, path)],
    )


def make_entity_ego(store, entity_id: str, max_events: int = 8) -> SubgraphUnit:
    node_ids = [entity_id]
    edge_keys: List[str] = []
    event_ids: List[str] = []
    doc_ids: List[str] = []

    for event_id in list(store.entity_to_events.get(entity_id, set()))[:max_events]:
        node_ids.append(event_id)
        event_ids.append(event_id)
        label = relation_between(store, entity_id, event_id) or relation_between(store, event_id, entity_id)
        if label:
            edge_keys.append(_edge_key(entity_id, event_id, label))
        doc_id = store.events.get(event_id, {}).get("doc_id", "")
        if doc_id:
            doc_ids.append(doc_id)

    return SubgraphUnit(
        unit_id=f"entity_ego:{entity_id}",
        unit_type="entity_ego",
        summary=node_name(store, entity_id),
        seed_nodes=[entity_id],
        node_ids=list(dict.fromkeys(node_ids)),
        edge_keys=edge_keys,
        event_ids=list(dict.fromkeys(event_ids)),
        entity_ids=[entity_id],
        doc_ids=list(dict.fromkeys(doc_ids)),
        metadata={"entity_name": node_name(store, entity_id), "entity_type": store.entities.get(entity_id, {}).get("entity_type", "")},
    )


def make_community_slice(store, community_id: str, max_events: int = 10) -> SubgraphUnit:
    node_ids = [community_id]
    edge_keys: List[str] = []
    event_ids: List[str] = []
    doc_ids: List[str] = []

    for event_id in store.community_to_events.get(community_id, [])[:max_events]:
        node_ids.append(event_id)
        event_ids.append(event_id)
        edge_keys.append(_edge_key(event_id, community_id, "IN_COMMUNITY"))
        doc_id = store.events.get(event_id, {}).get("doc_id", "")
        if doc_id:
            doc_ids.append(doc_id)

    return SubgraphUnit(
        unit_id=f"community_slice:{community_id}",
        unit_type="community_slice",
        summary=store.communities.get(community_id, {}).get("name", community_id),
        seed_nodes=[community_id],
        node_ids=list(dict.fromkeys(node_ids)),
        edge_keys=edge_keys,
        event_ids=list(dict.fromkeys(event_ids)),
        doc_ids=list(dict.fromkeys(doc_ids)),
        community_ids=[community_id],
        metadata={"community_kind": store.communities.get(community_id, {}).get("kind", "community")},
    )
