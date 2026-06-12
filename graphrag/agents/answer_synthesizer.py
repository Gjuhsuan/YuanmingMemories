"""这个文件负责基于整理后的证据生成最终答案文本。"""

from __future__ import annotations

from .llm_client import call_text_agent


def synthesize_answer(question: str, context_text: str, api_key: str, run_id: str) -> str:
    prompt = f"""
You are a graph-grounded historical QA assistant.
Answer strictly based on the supplied graph evidence.

Requirements:
1. First paragraph: answer the question directly.
2. Second paragraph: explain the evidence chain, including events, entities, relations, and source documents.
3. Distinguish direct support, indirect support, and background relevance.
4. Do not turn background relevance into a definite conclusion.
5. If evidence is insufficient, say so clearly.
6. Obey explicit hard constraints in the question, especially time range, place, historical period, and main subject.
7. Do not merge evidence from different periods or places into one answer unless the question explicitly asks for comparison.
8. Prefer under-answering to over-generalizing. If only part of the constrained answer set is supported, say it is partial.
9. Do not promote background or weakly related evidence into “major events”, “main institutions”, or other high-confidence summaries.

Question: {question}
Graph-grounded evidence: {context_text[:9000]}
"""
    answer = call_text_agent(
        prompt,
        api_key,
        run_id,
        "answer",
        system_prompt="You are a faithful graph-grounded historical QA assistant.",
        max_tokens=1200,
    )
    return answer or "LLM answer generation failed. Please inspect the retrieved graph evidence."
