"""
系统提示词、上下文模板、引用解析。

严格按 CLAUDE.md 附录 D 设计。
"""
import re

SYSTEM_PROMPT = """你是「圆明园历史档案研究助理」，服务于研究圆明园相关史事的专业历史学者。
你的全部回答都必须严格依据下方【图谱上下文】，这些内容来自圆明园事件知识图谱
（清代内务府档案抽取而成）。请遵守：

1. 只用【图谱上下文】中的信息作答。上下文没有的，明确说"现有图谱资料中未见相关记载"，
   不得臆造人名、官职、日期、数字或因果。
2. 凡引用某条资料，在相关句子末尾以【id】标注其编号（id 必须来自【可引用清单】），
   例如：……由都虞司委员办理【evt_1_1】。可一句多引。
3. 日期保留档案原文表述（如"雍正二年正月十八日"），必要时再附公历。
4. 区分"档案明载"与"据关系推断"；若资料含不确定性说明，请向学者提示。
5. 用规范、克制、严谨的学术中文；先给结论，再列依据；不输出与问题无关的内容。"""


def build_context_block(
    serialized_subgraph: str,
    allowed_ids: list[str],
    pinned_summaries: str = "",
) -> str:
    """
    组装"图谱上下文"块（插入 user 消息）。
    """
    parts = [
        "【图谱上下文】",
        serialized_subgraph or "（未检索到相关资料）",
        "",
        "【可引用清单】",
        ", ".join(allowed_ids) if allowed_ids else "（无）",
    ]
    if pinned_summaries:
        parts.extend([
            "",
            "【用户已重点引入的节点】",
            pinned_summaries,
        ])
    return "\n".join(parts)


def build_user_message(
    question: str,
    serialized_subgraph: str,
    allowed_ids: list[str],
    pinned_summaries: str = "",
) -> str:
    """组装发给 LLM 的 user 消息。"""
    context = build_context_block(serialized_subgraph, allowed_ids, pinned_summaries)
    return f"{context}\n\n问题：{question}"


def parse_citations(text: str, allowed_ids: list[str]) -> list[dict]:
    """
    从模型输出中解析引用标记【id】。
    只返回在 allowed_ids 中存在的 id。
    返回 [{"id": "...", "marker": "①"}]
    """
    pattern = r'【([^】]+)】'
    matches = re.findall(pattern, text)

    seen = set()
    citations = []
    marker_idx = 0
    markers = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

    for m in matches:
        # 检查是否在 allowed_ids 中
        if m in allowed_ids and m not in seen:
            seen.add(m)
            marker = markers[marker_idx] if marker_idx < len(markers) else f"[{marker_idx + 1}]"
            citations.append({"id": m, "marker": marker})
            marker_idx += 1

    return citations


def build_pinned_summaries(pinned_items: list[dict]) -> str:
    """
    根据上下文篮中的节点生成摘要文本。
    """
    if not pinned_items:
        return ""

    lines = []
    for item in pinned_items:
        lines.append(
            f"  - [{item.get('id', '')}] {item.get('name', '')}"
            f"（{item.get('type_cn', '')}）"
        )
    return "\n".join(lines)
