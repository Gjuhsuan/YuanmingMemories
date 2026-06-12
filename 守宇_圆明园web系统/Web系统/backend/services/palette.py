"""
节点颜色常量 —— 前后端共用同一份真值。

摘自 CLAUDE.md 第 7.3 节。
"""

NODE_COLORS = {
    "Event": "#B5503C",
    "Person": "#5E7A99",
    "Place": "#6E8E6A",
    "Organization": "#8E7BA0",
    "Object": "#B08A4F",
    "Document": "#7C8691",
    "AbstractNorm": "#A8836E",
    "TemporalInterval": "#6FA0A0",
}

# 基础色（供前端 CSS 变量参考）
BASE_COLORS = {
    "bg_canvas": "#FAF8F3",
    "bg_panel": "#FFFFFF",
    "bg_subtle": "#F2EFE9",
    "border": "#E3DED4",
    "text_primary": "#2B2A28",
    "text_secondary": "#6B665E",
    "text_muted": "#9A938A",
    "accent": "#B5503C",
    "edge": "#CFC8BC",
}


def get_node_color(label: str) -> str:
    """返回给定 Label 的节点颜色。"""
    return NODE_COLORS.get(label, "#9A938A")
