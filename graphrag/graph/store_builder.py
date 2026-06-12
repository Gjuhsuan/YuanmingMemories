"""这个文件负责从项目数据构建 GraphRAG 使用的图底座。"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Set

from ..community_index import build_communities
from .graph_ops import normalize_text, token_set


@dataclass
class GraphSubstrate:
    entries: Dict[str, Dict] = field(default_factory=dict)
    events: Dict[str, Dict] = field(default_factory=dict)
    entities: Dict[str, Dict] = field(default_factory=dict)
    entity_surfaces: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    event_surfaces: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    name_index: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    doc_to_events: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    entity_to_events: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    event_to_entities: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    event_relations: Dict[str, List[Dict]] = field(default_factory=lambda: defaultdict(list))
    entity_relations: Dict[str, List[Dict]] = field(default_factory=lambda: defaultdict(list))
    relation_types: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    schema_types: Set[str] = field(default_factory=set)
    schema_relation_types: Set[str] = field(default_factory=set)
    schema_attribute_keys: Set[str] = field(default_factory=set)
    communities: Dict[str, Dict] = field(default_factory=dict)
    community_to_events: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    event_to_communities: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    adjacency: Dict[str, List[Dict]] = field(default_factory=lambda: defaultdict(list))
    node_meta: Dict[str, Dict] = field(default_factory=dict)

    def __getitem__(self, key: str):
        return getattr(self, key)

    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def as_dict(self) -> Dict[str, object]:
        return self.__dict__


def _read_jsonl(path: Path) -> Iterable[Dict]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _ensure_entity_bucket(store: GraphSubstrate, entity_id: str) -> Dict:
    return store.entities.setdefault(
        entity_id,
        {
            "entity_id": entity_id,
            "name": entity_id,
            "entity_type": "Unknown",
            "aliases": set(),
            "mention_texts": set(),
            "attributes": {},
            "event_ids": set(),
            "doc_ids": set(),
        },
    )


def _merge_entities_from_step1(store: GraphSubstrate, doc_id: str, entities: List[Dict]) -> None:
    for entity in entities or []:
        entity_id = entity.get("entity_id")
        if not entity_id:
            continue
        bucket = _ensure_entity_bucket(store, entity_id)
        bucket["name"] = entity.get("name") or bucket["name"]
        bucket["entity_type"] = entity.get("entity_type") or bucket["entity_type"]
        bucket["aliases"].update(alias for alias in entity.get("aliases", []) if alias)
        bucket["mention_texts"].update(text for text in entity.get("mention_texts", []) if text)
        bucket["event_ids"].update(entity.get("source_event_ids", []))
        bucket["doc_ids"].add(doc_id)


def _add_edge(store: GraphSubstrate, from_id: str, to_id: str, label: str, reverse_label: str | None = None) -> None:
    if not from_id or not to_id:
        return
    edge = {"to": to_id, "label": label or "RELATED_TO"}
    if edge not in store.adjacency[from_id]:
        store.adjacency[from_id].append(edge)
    reverse_edge = {"to": from_id, "label": reverse_label or f"REV_{label or 'RELATED_TO'}"}
    if reverse_edge not in store.adjacency[to_id]:
        store.adjacency[to_id].append(reverse_edge)


def _index_name(store: GraphSubstrate, raw: str, item_id: str) -> None:
    if not raw:
        return
    normalized = normalize_text(raw)
    if normalized:
        store.name_index[normalized].add(item_id)
    for token in token_set(raw, min_ngram=2, max_ngram=4):
        store.name_index[token].add(item_id)


def build_graph_substrate(
    entries_path: str = "entries_simplified.jsonl",
    stage1_path: str = "stage1_results.jsonl",
    stage2_path: str = "stage2_results.normalized.jsonl",
) -> GraphSubstrate:
    entries_path = Path(entries_path)
    stage1_path = Path(stage1_path)
    stage2_path = Path(stage2_path)

    store = GraphSubstrate()

    for entry in _read_jsonl(entries_path):
        doc_id = str(entry["entry_id"])
        store.entries[doc_id] = {
            "doc_id": doc_id,
            "title": entry.get("title", ""),
            "date": entry.get("date", ""),
            "body": entry.get("body", ""),
        }

    for batch in _read_jsonl(stage1_path):
        for result in batch.get("parsed", {}).get("results", []):
            doc_id = str(result.get("doc_id", ""))
            for event in result.get("step_4", {}).get("events_summary", []):
                event_id = event.get("event_id")
                if not event_id:
                    continue
                store.events[event_id] = {
                    "event_id": event_id,
                    "doc_id": doc_id,
                    "name": event.get("event_name", event_id),
                    "event_type": event.get("event_type", ""),
                    "source_text": event.get("source_text", ""),
                    "date_text": event.get("date_text", ""),
                }
                store.doc_to_events[doc_id].append(event_id)

    for bundle in _read_jsonl(stage2_path):
        for result in bundle.get("parsed", {}).get("results", []):
            doc_id = str(result.get("doc_id", ""))
            _merge_entities_from_step1(store, doc_id, result.get("step_1", {}).get("entities", []))
            final_step = result.get("step_5", {})

            for entity in final_step.get("final_entities", []):
                entity_id = entity.get("entity_id")
                if not entity_id:
                    continue
                bucket = _ensure_entity_bucket(store, entity_id)
                bucket["name"] = entity.get("name") or bucket["name"]
                bucket["entity_type"] = entity.get("entity_type") or bucket["entity_type"]
                bucket["doc_ids"].add(doc_id)
                if bucket.get("entity_type"):
                    store.schema_types.add(bucket["entity_type"])

            for rel in final_step.get("final_relations", []):
                from_id = rel.get("from_id", "")
                to_id = rel.get("to_id", "")
                relation_type = rel.get("relation_type", "") or "RELATED_TO"
                if from_id.startswith("evt_"):
                    store.event_relations[from_id].append(rel)
                    if to_id and not to_id.startswith("evt_"):
                        store.event_to_entities[from_id].add(to_id)
                        store.entity_to_events[to_id].add(from_id)
                else:
                    store.entity_relations[from_id].append(rel)
                store.relation_types[relation_type].add(relation_type)
                store.schema_relation_types.add(relation_type)

            for attr in final_step.get("final_entity_attributes", []):
                entity_id = attr.get("entity_id")
                if not entity_id:
                    continue
                bucket = _ensure_entity_bucket(store, entity_id)
                for key, value in attr.items():
                    if key == "entity_id":
                        continue
                    if value not in ("", None, []):
                        bucket["attributes"][key] = value
                        store.schema_attribute_keys.add(key)

    for entity_id, entity in store.entities.items():
        all_names = {entity.get("name", entity_id), *entity.get("aliases", set()), *entity.get("mention_texts", set())}
        for raw in all_names:
            if not raw:
                continue
            store.entity_surfaces[entity_id].add(raw)
            _index_name(store, raw, entity_id)

    for event_id, event in store.events.items():
        for raw in {event.get("name", ""), event.get("date_text", "")}:
            if raw:
                store.event_surfaces[event_id].add(raw)
                _index_name(store, raw, event_id)
        source_text = event.get("source_text", "")
        if source_text:
            for token in token_set(source_text, min_ngram=4, max_ngram=4):
                if len(token) >= 3:
                    store.name_index[token].add(event_id)

    for doc_id, entry in store.entries.items():
        for raw in {entry.get("title", ""), entry.get("date", "")}:
            _index_name(store, raw, doc_id)

    build_communities(store.__dict__)
    for community_id, community in store.communities.items():
        for raw in {community.get("name", ""), community_id}:
            _index_name(store, raw, community_id)

    for event_id, event in store.events.items():
        store.node_meta[event_id] = {"label": event.get("name", event_id), "kind": "Event"}
        doc_node_id = f"doc_{event.get('doc_id', '')}"
        store.node_meta[doc_node_id] = {
            "label": store.entries.get(event.get("doc_id", ""), {}).get("title", doc_node_id),
            "kind": "Document",
        }
        _add_edge(store, event_id, doc_node_id, "IN_DOC", "HAS_EVENT")

    for entity_id, entity in store.entities.items():
        store.node_meta[entity_id] = {
            "label": entity.get("name", entity_id),
            "kind": entity.get("entity_type", "Entity"),
        }

    for community_id, community in store.communities.items():
        store.node_meta[community_id] = {
            "label": community.get("name", community_id),
            "kind": f"Community:{community.get('kind', 'community')}",
        }
        for event_id in store.community_to_events.get(community_id, []):
            _add_edge(store, event_id, community_id, "IN_COMMUNITY", "HAS_EVENT")

    for event_id, rels in store.event_relations.items():
        for rel in rels:
            to_id = rel.get("to_id", "")
            if to_id in store.events or to_id in store.entities:
                _add_edge(store, event_id, to_id, rel.get("relation_type", "RELATED_TO"))

    for entity_id, rels in store.entity_relations.items():
        for rel in rels:
            to_id = rel.get("to_id", "")
            if to_id in store.events or to_id in store.entities:
                _add_edge(store, entity_id, to_id, rel.get("relation_type", "RELATED_TO"))

    return store
