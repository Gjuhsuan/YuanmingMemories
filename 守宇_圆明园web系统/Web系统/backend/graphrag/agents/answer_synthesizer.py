"""答案合成 —— 基于证据生成专业、丰富、有引用标注的历史学回答。"""

from __future__ import annotations

from .llm_client import call_text_agent


def synthesize_answer(question: str, context_text: str, api_key: str, run_id: str) -> str:
    prompt = f"""
你是一位研究圆明园历史的资深学者，面向专业读者撰写基于史料的严谨回答。

写作规范：
1. 直接回答问题，深入分析每个涉及机构/人物的具体角色、职能和互动关系，不要只列名词。
2. 每个关键事实陈述后，必须紧跟引用标记【event_id】（如【evt_1_1】）。引用标记直接跟在相关句子的句号后。
3. 按时间顺序或逻辑链条组织叙述，展现事件之间的因果关系。
4. 区分"直接记载"(support=direct)和"间接提及"(support=indirect)。直接证据优先详述，间接证据作为补充。
5. 即使证据标记为unverified或weak，只要出现在证据列表中，就是系统已知的事实，应当引用和分析。
6. 严守问题中的时间、地点约束。具体给出机构全称、人物官职、准确日期。
7. 如果证据不充分，在分析现有证据后明确指出缺失部分，但不影响已确认内容的详细呈现。
8. 每个机构/人物必须说明其"做了什么"，而非仅仅出现名字。

引用格式示例：
"雍正帝降旨同意砍伐围场大树并运送进京【evt_1_1】。随后，允禄以总管内务府事务和硕庄亲王身份传谕都虞司委员办理【evt_1_1】。"

问题：{question}
图谱证据：{context_text[:10000]}
"""
    answer = call_text_agent(
        prompt,
        api_key,
        run_id,
        "answer",
        system_prompt="你是研究圆明园历史的资深学者。每个事实陈述后必须紧跟【event_id】引用标记。深入分析角色和关系，不只是罗列名称。",
        max_tokens=8192,
    )
    return answer or "LLM answer generation failed. Please inspect the retrieved graph evidence."
