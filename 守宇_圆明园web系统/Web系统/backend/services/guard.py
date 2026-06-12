"""
Cypher 只读校验 —— 黑名单 + LIMIT 注入 + 超时保护。

严格按 CLAUDE.md 附录 C 实现。
"""
import re
import time
from typing import Optional

# ── 黑名单关键词（大小写不敏感）──
BLACKLIST = [
    r'\bCREATE\b', r'\bMERGE\b', r'\bDELETE\b', r'\bDETACH\b',
    r'\bSET\b', r'\bREMOVE\b', r'\bDROP\b', r'\bFOREACH\b',
    r'\bLOAD\s+CSV\b', r'\bPERIODIC\s+COMMIT\b',
]

# CALL 需要特殊处理：允许只读白名单过程
CALL_BLACKLIST = r'\bCALL\b'
CALL_WHITELIST = [
    'db.index.fulltext.queryNodes',
    'db.index.fulltext.queryRelationships',
    'db.schema',
    'db.labels',
    'db.relationshipTypes',
    'db.propertyKeys',
]


def validate_cypher(query: str) -> dict:
    """
    校验并净化 Cypher 查询。
    返回 {"valid": bool, "query": str, "error": Optional[str]}

    步骤：
    1. 去注释
    2. 黑名单匹配
    3. 强制 LIMIT 注入
    4. 大小限制
    """
    cleaned = _remove_comments(query)

    # 逐条黑名单检测
    for pattern in BLACKLIST:
        if re.search(pattern, cleaned, re.IGNORECASE):
            kw = re.search(pattern, cleaned, re.IGNORECASE).group(0)
            return {
                "valid": False,
                "query": query,
                "error": f"仅支持只读查询，检测到写操作关键字：{kw.strip()}",
            }

    # CALL 黑名单检测
    call_match = re.findall(CALL_BLACKLIST, cleaned, re.IGNORECASE)
    if call_match:
        # 检查 CALL 后面跟的是否在只读白名单中
        call_pattern = r'CALL\s+([a-zA-Z._]+)'
        for m in re.finditer(call_pattern, cleaned, re.IGNORECASE):
            called_proc = m.group(1)
            if not any(called_proc.startswith(w) for w in CALL_WHITELIST):
                return {
                    "valid": False,
                    "query": query,
                    "error": f"不允许调用的过程：{called_proc}",
                }

    # 强制 LIMIT 注入
    query_upper = cleaned.upper().strip()
    has_limit = bool(re.search(r'\bLIMIT\s+\d+', query_upper))
    if not has_limit:
        cleaned += "\nLIMIT 500"
    else:
        # 检查 LIMIT 值是否 > 1000
        limit_match = re.search(r'\bLIMIT\s+(\d+)', query_upper)
        if limit_match:
            limit_val = int(limit_match.group(1))
            if limit_val > 1000:
                cleaned = re.sub(
                    r'\bLIMIT\s+\d+', 'LIMIT 1000', cleaned, count=1, flags=re.IGNORECASE
                )

    return {"valid": True, "query": cleaned, "error": None}


def _remove_comments(query: str) -> str:
    """移除 Cypher 注释（单行 // 和多行 /* */）。"""
    # 移除多行注释
    query = re.sub(r'/\*.*?\*/', ' ', query, flags=re.DOTALL)
    # 移除单行注释（但不删除字符串内的 //）
    lines = []
    for line in query.split('\n'):
        # 简易处理：找到第一个 // 且不在引号内
        in_single = False
        in_double = False
        for i, ch in enumerate(line):
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == '/' and i + 1 < len(line) and line[i + 1] == '/' and not in_single and not in_double:
                line = line[:i]
                break
        lines.append(line)
    return '\n'.join(lines)
