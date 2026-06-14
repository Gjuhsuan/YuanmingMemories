"""这个文件负责校验最终答案是否符合证据和约束。"""

from __future__ import annotations

from .llm_client import call_json_agent


def verify_answer(question: str, answer: str, context_text: str, api_key: str, run_id: str) -> str:
    if not api_key or not answer:
        return answer
    prompt = f"""
You are the final answer verifier.
Check whether the answer is supported by the graph evidence and revise it if necessary.

Question: {question}
Candidate answer: {answer}
Graph evidence: {context_text[:9000]}

Return JSON:
{{
  "unsupported_claims": ["claims not supported"],
  "revised_answer": "revised answer"
}}

Rules:
1. Check support against the original hard constraints, not just topical similarity.
2. Remove claims that mix different periods, places, or subjects unless the question explicitly asks for comparison.
3. If the answer is only partially supported under the stated constraints, revise it into a partial answer rather than a broad answer.
"""
    data = call_json_agent(
        prompt,
        api_key,
        run_id,
        "answer.verify",
        system_prompt="You are a strict answer verifier. Always return JSON.",
        max_tokens=1400,
    )
    revised = str(data.get("revised_answer", "")).strip()
    return revised or answer
