"""这个文件负责围绕子问题检索候选子图和相关事件。"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Set, Tuple

from ..agents import select_relations
from ..graph import find_paths, format_path, node_kind, node_name, normalize_text
from ..model_defs import GraphRAGConfig, QuestionPlan, RetrievalUnit, SubQuestion
from ..slot_filling import fill_slots, merge_slots
from .seed_locator import lexical_event_candidates, locate_seed_nodes
from .subgraph_ranker import rank_and_assess_events
from .subgraph_units import make_community_slice, make_entity_ego, make_event_path, make_event_star


GENERIC_RELATION_BLOCKLIST = {"IN_COMMUNITY", "HAS_EVENT"}


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


def node_summary(store, node_id: str) -> Dict[str, str]:
    return {"id": node_id, "name": node_name(store, node_id), "kind": node_kind(store, node_id)}


def candidate_relations(store, seed_nodes: List[str], plan: QuestionPlan, subq: SubQuestion, limit: int = 80) -> List[Dict[str, Any]]:
    counter: Counter[str] = Counter()
    examples: Dict[str, List[str]] = defaultdict(list)

    for relation_item in plan.relation_policy:
        rel = relation_item.get("relation")
        if rel:
            counter[rel] += float(relation_item.get("priority", 1) or 1) + 5
            examples[rel].append(str(relation_item.get("reason", "")))
    for rel in subq.preferred_relations:
        counter[rel] += 6
        examples[rel].append("preferred by subquestion")

    for node_id in seed_nodes:
        for edge in store.get("adjacency", {}).get(node_id, []):
            relation = edge.get("label", "")
            if not relation:
                continue
            counter[relation] += 2
            if len(examples[relation]) < 3:
                examples[relation].append(f"{node_name(store, node_id)} -> {relation} -> {node_name(store, edge.get('to', ''))}")

    if not counter:
        for relation in sorted(store.get("schema_relation_types", [])):
            counter[relation] += 1

    rows = []
    for relation, count in counter.most_common(limit):
        rows.append({"relation": relation, "count": count, "examples": examples.get(relation, [])[:3]})
    return rows


def allowed_relation_set(choices: List) -> Set[str]:
    return {choice.relation for choice in choices if getattr(choice, "relation", "")}


def expand_from_seed_nodes(store, seed_nodes: List[str], allowed_relations: Set[str], config: GraphRAGConfig) -> Tuple[Dict[str, float], List[List[str]]]:
    candidate_scores: Dict[str, float] = defaultdict(float)
    paths: List[List[str]] = []

    for node_id in seed_nodes:
        if node_id in store.get("events", {}):
            candidate_scores[node_id] += 8.0
        elif node_id in store.get("entities", {}):
            for event_id in store.get("entity_to_events", {}).get(node_id, set()):
                candidate_scores[event_id] += 5.0

    support_paths = find_paths(
        store,
        seed_nodes,
        goal_kinds={"Event", "Document"},
        allowed_relations=allowed_relations if allowed_relations else None,
        max_depth=config.max_depth,
        max_paths=max(20, config.candidate_event_limit * 2),
    )
    for path in support_paths:
        paths.append(path)
        path_bonus = max(0.5, 5.0 - (len(path) - 1))
        for node_id in path:
            if node_id in store.get("events", {}):
                candidate_scores[node_id] += path_bonus
            elif node_id in store.get("entities", {}):
                for event_id in store.get("entity_to_events", {}).get(node_id, set()):
                    candidate_scores[event_id] += path_bonus * 0.25
            elif node_id in store.get("communities", {}) and "HAS_EVENT" in allowed_relations:
                for event_id in store.get("community_to_events", {}).get(node_id, [])[: config.width]:
                    candidate_scores[event_id] += path_bonus * 0.15
    return dict(candidate_scores), paths


def build_subgraph_units(store, seed_events: List[str], seed_entities: List[str], seed_communities: List[str], paths: List[List[str]]):
    units = []
    for event_id in seed_events[:6]:
        units.append(make_event_star(store, event_id))
    for path in paths[:8]:
        if len(path) >= 2:
            units.append(make_event_path(store, path))
    for entity_id in seed_entities[:4]:
        units.append(make_entity_ego(store, entity_id))
    for community_id in seed_communities[:3]:
        units.append(make_community_slice(store, community_id))
    return units


def retrieve_for_subquestion(
    store,
    plan: QuestionPlan,
    subq: SubQuestion,
    config: GraphRAGConfig,
    api_key: str = "",
    run_id: str = "",
) -> RetrievalUnit:
    seed_queries = _unique(plan.seed_queries + plan.entity_hints + subq.seed_queries + [subq.text], limit=30)
    matched_entities, matched_events, matched_communities = locate_seed_nodes(store, seed_queries, subq.text, config.seed_limit)
    seed_nodes = list(matched_entities | matched_events | matched_communities)

    lexical_candidates: Dict[str, float] = {}
    if not seed_nodes:
        lexical_candidates = lexical_event_candidates(store, subq.text, limit=config.candidate_event_limit)
        seed_nodes = list(lexical_candidates.keys())[: config.seed_limit]

    relation_candidates = candidate_relations(store, seed_nodes, plan, subq)
    seed_summaries = [node_summary(store, node_id) for node_id in seed_nodes[:20]]
    if api_key and config.use_llm_relation_prune:
        original_question = getattr(plan, "original_question", "") or subq.text
        relation_choices = select_relations(
            question=original_question,
            subquestion=subq.text,
            store=store,
            seed_node_summaries=seed_summaries,
            candidate_relations=relation_candidates,
            api_key=api_key,
            run_id=run_id,
            stage=f"relation_prune.{normalize_text(subq.answer_slot or subq.text)[:20]}",
            relation_limit=config.relation_limit,
        )
    else:
        relation_choices = []
        for item in relation_candidates:
            relation = item.get("relation", "")
            if relation and relation not in GENERIC_RELATION_BLOCKLIST:
                relation_choices.append(type("Choice", (), {"relation": relation})())
            if len(relation_choices) >= config.relation_limit:
                break
    selected_relations = allowed_relation_set(relation_choices)

    candidate_scores, support_paths = expand_from_seed_nodes(store, seed_nodes, selected_relations, config)
    for event_id, score in lexical_candidates.items():
        candidate_scores[event_id] = max(candidate_scores.get(event_id, 0.0), score)
    if not candidate_scores and matched_events:
        for event_id in matched_events:
            candidate_scores[event_id] += 8.0

    event_ids, assessments, evidence_lines, slot_fills = rank_and_assess_events(
        store,
        plan,
        subq,
        config,
        api_key,
        run_id,
        candidate_scores,
        selected_relations,
    ) if candidate_scores else ([], [], [], {})

    entity_ids: Set[str] = set(matched_entities)
    doc_ids: Set[str] = set()
    community_names: List[str] = []
    community_ids: Set[str] = set(matched_communities)

    for event_id in event_ids:
        event = store.get("events", {}).get(event_id, {})
        if event.get("doc_id"):
            doc_ids.add(event["doc_id"])
        entity_ids.update(store.get("event_to_entities", {}).get(event_id, set()))
        for community_id in store.get("event_to_communities", {}).get(event_id, [])[:3]:
            community = store.get("communities", {}).get(community_id)
            if community:
                community_ids.add(community_id)
                community_names.append(community.get("name", community_id))

    for path in support_paths[:8]:
        for node_id in path:
            if node_id in store.get("entities", {}):
                entity_ids.add(node_id)
            elif node_id in store.get("events", {}):
                event = store.get("events", {}).get(node_id, {})
                if event.get("doc_id"):
                    doc_ids.add(event["doc_id"])

    path_lines = [format_path(store, path) for path in support_paths[:8]]
    seed_entity_names = [node_name(store, entity_id) for entity_id in list(matched_entities)[: config.seed_limit]]
    seed_event_names = [node_name(store, event_id) for event_id in list(matched_events)[: config.seed_limit]]
    if not seed_event_names:
        seed_event_names = [node_name(store, event_id) for event_id in event_ids[: config.seed_limit]]

    subgraph_units = build_subgraph_units(
        store,
        seed_events=event_ids or list(matched_events),
        seed_entities=list(matched_entities),
        seed_communities=list(community_ids),
        paths=support_paths,
    )
    for unit in subgraph_units:
        if unit.unit_type == "event_path":
            for line in unit.path_lines:
                if line not in path_lines:
                    path_lines.append(line)

    unit = RetrievalUnit(
        subquestion=subq.text,
        purpose=subq.purpose,
        seed_entities=seed_entity_names,
        seed_events=seed_event_names,
        community_hits=_unique(community_names, limit=8),
        selected_relations=sorted(selected_relations),
        path_lines=path_lines,
        event_ids=event_ids,
        entity_ids=list(entity_ids),
        doc_ids=list(doc_ids),
        evidence_lines=evidence_lines[: config.evidence_limit * 4],
        evidence_assessments=assessments,
        slot_fills=slot_fills,
        reflection_note="",
        score=sum(candidate_scores.get(event_id, 0.0) for event_id in event_ids),
    )
    fallback_slots = fill_slots(subq.text, store, [unit], plan.task_type, target_slots=plan.target_slots)
    unit.slot_fills = merge_slots([unit.slot_fills, fallback_slots])
    return unit
