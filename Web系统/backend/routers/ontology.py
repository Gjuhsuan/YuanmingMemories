"""
本体结构 API —— 解析 ontology.ttl 返回类层次、属性等结构化 JSON。
"""
import re
from pathlib import Path
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["ontology"])

# ontology.ttl 位于项目根目录 (YuanmingMemories/)
_ONTOLOGY_PATH = Path(__file__).resolve().parent.parent.parent.parent / "ontology.ttl"
_cache: dict | None = None


def _parse_ttl(text: str) -> dict:
    """简易 Turtle 解析器，提取类层次、标签、注释和属性。"""
    classes: dict[str, dict] = {}
    object_props: list[dict] = []
    data_props: list[dict] = []

    lines = text.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("#") or line.startswith("@"):
            i += 1
            continue

        # ── 类声明 ──
        cls_match = re.match(r"^:(\w+)\s+rdf:type\s+owl:Class", line)
        if cls_match:
            uri = cls_match.group(1)
            entry = {
                "uri": uri,
                "label_zh": uri,
                "label_en": uri,
                "comment_zh": "",
                "comment_en": "",
                "parent": None,
            }
            classes[uri] = entry

            # 收集后续连续属性行，直到行尾为 .
            buffer = [line]
            i += 1
            while i < len(lines):
                pl = lines[i].strip()
                if not pl:
                    i += 1
                    continue
                buffer.append(pl)
                if pl.rstrip().endswith("."):
                    break
                i += 1

            # 合并 buffer 为一段文本，方便跨行匹配
            block = " ".join(buffer)

            # 父类
            sub_match = re.search(r"rdfs:subClassOf\s+:(\w+)", block)
            if sub_match:
                entry["parent"] = sub_match.group(1)

            # 中文 label
            zh_label = re.search(r'rdfs:label\s+"([^"]*)"@zh', block)
            if zh_label:
                entry["label_zh"] = zh_label.group(1)
            en_label = re.search(r'rdfs:label\s+[^;]*"([^"]*)"@en', block)
            if en_label:
                entry["label_en"] = en_label.group(1)

            # 中文 comment
            zh_comment = re.search(r'rdfs:comment\s+"([^"]*)"@zh', block)
            if zh_comment:
                entry["comment_zh"] = zh_comment.group(1)
            en_comment = re.search(r'rdfs:comment\s+[^;]*"([^"]*)"@en', block)
            if en_comment:
                entry["comment_en"] = en_comment.group(1)

            i += 1
            continue

        # ── 对象属性 ──
        obj_match = re.match(r"^:(\w+)\s+rdf:type\s+owl:ObjectProperty", line)
        if obj_match:
            uri = obj_match.group(1)
            entry = {
                "uri": uri,
                "label_zh": uri,
                "label_en": uri,
                "comment_zh": "",
                "domain": None,
                "range": None,
                "inverseOf": None,
            }

            buffer = [line]
            i += 1
            while i < len(lines):
                pl = lines[i].strip()
                if not pl:
                    i += 1
                    continue
                buffer.append(pl)
                if pl.rstrip().endswith("."):
                    break
                i += 1

            block = " ".join(buffer)

            zh_label = re.search(r'rdfs:label\s+"([^"]*)"@zh', block)
            if zh_label:
                entry["label_zh"] = zh_label.group(1)
            en_label = re.search(r'rdfs:label\s+[^;]*"([^"]*)"@en', block)
            if en_label:
                entry["label_en"] = en_label.group(1)
            zh_comment = re.search(r'rdfs:comment\s+"([^"]*)"@zh', block)
            if zh_comment:
                entry["comment_zh"] = zh_comment.group(1)
            dm = re.search(r"rdfs:domain\s+:(\w+)", block)
            if dm:
                entry["domain"] = dm.group(1)
            rm = re.search(r"rdfs:range\s+:(\w+)", block)
            if rm:
                entry["range"] = rm.group(1)
            inv = re.search(r"owl:inverseOf\s+:(\w+)", block)
            if inv:
                entry["inverseOf"] = inv.group(1)

            object_props.append(entry)
            i += 1
            continue

        # ── 数据属性 ──
        data_match = re.match(r"^:(\w+)\s+rdf:type\s+owl:DatatypeProperty", line)
        if data_match:
            uri = data_match.group(1)
            entry = {
                "uri": uri,
                "label_zh": uri,
                "label_en": uri,
                "comment_zh": "",
                "domain": None,
                "range": None,
            }

            buffer = [line]
            i += 1
            while i < len(lines):
                pl = lines[i].strip()
                if not pl:
                    i += 1
                    continue
                buffer.append(pl)
                if pl.rstrip().endswith("."):
                    break
                i += 1

            block = " ".join(buffer)

            zh_label = re.search(r'rdfs:label\s+"([^"]*)"@zh', block)
            if zh_label:
                entry["label_zh"] = zh_label.group(1)
            zh_comment = re.search(r'rdfs:comment\s+"([^"]*)"@zh', block)
            if zh_comment:
                entry["comment_zh"] = zh_comment.group(1)
            dm = re.search(r"rdfs:domain\s+:(\w+)", block)
            if dm:
                entry["domain"] = dm.group(1)
            rm = re.search(r'rdfs:range\s+xsd:(\w+)', block)
            if rm:
                entry["range"] = rm.group(1)

            data_props.append(entry)
            i += 1
            continue

        i += 1

    # 构建树：找出根节点（无 parent 或 parent 不在 classes 中）
    roots = []
    for uri, cls in classes.items():
        p = cls.get("parent")
        if not p or p not in classes:
            roots.append(uri)

    def build_tree(uris: list[str]) -> list[dict]:
        result = []
        for u in sorted(uris, key=lambda x: classes[x]["label_zh"]):
            c = classes[u]
            children = [ch for ch in classes if classes[ch].get("parent") == u]
            node = {
                "uri": c["uri"],
                "label_zh": c["label_zh"],
                "label_en": c["label_en"],
                "comment_zh": c["comment_zh"],
                "comment_en": c["comment_en"],
                "parent": c.get("parent"),
                "children": build_tree(children),
            }
            result.append(node)
        return result

    return {
        "tree": build_tree(roots),
        "objectProperties": object_props,
        "dataProperties": data_props,
    }


def get_ontology_cached() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    if _ONTOLOGY_PATH.exists():
        text = _ONTOLOGY_PATH.read_text(encoding="utf-8")
        _cache = _parse_ttl(text)
    else:
        _cache = {"tree": [], "objectProperties": [], "dataProperties": []}
    return _cache


@router.get("/ontology")
async def ontology():
    """返回解析后的本体结构：类层次树 + 对象属性 + 数据属性。"""
    return get_ontology_cached()
