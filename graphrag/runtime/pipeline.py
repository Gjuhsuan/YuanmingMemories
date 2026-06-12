"""这个文件负责串联完整的 GraphRAG 运行主流程。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

from ..agents import create_plan, reflect_on_evidence, synthesize_answer, verify_answer, verify_plan
from ..logging_utils import get_log_path, log_event, new_run_id
from ..model_defs import GraphRAGConfig, PipelineResult, RetrievalUnit, SubQuestion
from ..retrieval import retrieve_for_subquestion
from ..slot_filling import fill_slots_from_units
from .evidence_organizer import build_answer_support_graph_payload, build_context_text, build_grounded_answer


def _run_subquestions_parallel(index, plan, config: GraphRAGConfig, api_key: str, run_id: str) -> List[RetrievalUnit]:
    if len(plan.subquestions) <= 1:
        return [retrieve_for_subquestion(index, plan, plan.subquestions[0], config, api_key=api_key, run_id=run_id)]

    max_workers = min(max(1, config.parallel_workers), len(plan.subquestions))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(retrieve_for_subquestion, index, plan, subq, config, api_key, run_id)
            for subq in plan.subquestions
        ]
        return [future.result() for future in futures]


def _merge_slot_fills(units: List[RetrievalUnit]) -> Dict[str, List[str]]:
    return fill_slots_from_units(units)


def _subquestions_from_actions(actions, step_idx: int) -> List[SubQuestion]:
    subquestions: List[SubQuestion] = []
    for idx, action in enumerate(actions, start=1):
        subquestions.append(
            SubQuestion(
                text=action.query,
                purpose=action.purpose or "reflection search action",
                target_types=["Event", "Entity", "Document", "Relation", "Community"],
                answer_slot=f"reflection_{step_idx}_{idx}",
                seed_queries=action.seed_queries,
                preferred_relations=action.preferred_relations,
            )
        )
    return subquestions


def run_pipeline(index, driver, question: str, api_key: str, config: GraphRAGConfig) -> PipelineResult:
    del driver
    run_id = new_run_id()
    log_path = get_log_path()
    log_event(run_id, "pipeline.start", {"question": question})

    draft_plan = create_plan(question, index, api_key if config.use_llm_decomposition else "", run_id, max_subquestions=config.max_subquestions)
    plan = verify_plan(question, draft_plan, api_key if config.use_llm_decomposition else "", run_id, max_subquestions=config.max_subquestions)
    log_event(
        run_id,
        "plan.final",
        {
            "task_type": plan.task_type,
            "target_slots": plan.target_slots,
            "seed_queries": plan.seed_queries,
            "subquestions": [q.text for q in plan.subquestions],
        },
    )

    units = _run_subquestions_parallel(index, plan, config, api_key=api_key, run_id=run_id)
    reflections = []

    context_text = build_context_text(index, question, units, reflections)
    if api_key and config.use_llm_reflection:
        for step_idx in range(1, config.max_iterations + 1):
            slot_snapshot = _merge_slot_fills(units)
            reflection = reflect_on_evidence(
                question,
                context_text,
                slot_snapshot,
                plan.target_slots,
                api_key,
                run_id,
                step_idx,
            )
            reflections.append(reflection)
            if reflection.enough:
                break
            if reflection.need_user_clarification and not reflection.search_actions:
                break
            new_subquestions = _subquestions_from_actions(reflection.search_actions, step_idx)
            if not new_subquestions:
                break
            for subq in new_subquestions:
                units.append(retrieve_for_subquestion(index, plan, subq, config, api_key=api_key, run_id=run_id))
            context_text = build_context_text(index, question, units, reflections)

    graph_nodes, graph_edges = build_answer_support_graph_payload(index, units, max_events=config.related_event_limit)
    context_text = build_context_text(index, question, units, reflections)
    merged_slots = _merge_slot_fills(units)
    log_event(run_id, "slots.snapshot", {"slots": merged_slots})

    if api_key and config.use_llm_answer:
        answer = synthesize_answer(question, context_text, api_key, run_id)
        if config.use_llm_verification:
            answer = verify_answer(question, answer, context_text, api_key, run_id)
    else:
        answer = build_grounded_answer(question, index, units, plan.task_type)

    log_event(
        run_id,
        "pipeline.end",
        {
            "task_type": plan.task_type,
            "subquestion_count": len(plan.subquestions),
            "retrieval_units": len(units),
            "graph_nodes": len(graph_nodes),
            "graph_edges": len(graph_edges),
        },
    )
    return PipelineResult(
        plan=plan,
        retrieved_units=units,
        reflections=reflections,
        answer=answer,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        context_text=context_text,
        run_id=run_id,
        log_path=log_path,
    )
