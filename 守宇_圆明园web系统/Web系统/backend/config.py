"""
复用根目录 config.py 的中英文映射。

由于根目录 config.py 与当前 backend/ 不在同一包路径下，
此处直接用 sys.path 方式导入，从而保持与 import_to_neo4j.py 逻辑一致。
"""
import sys
from pathlib import Path

# 把项目根目录加入 sys.path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 从根目录 config 导入全部符号
from config import *  # noqa: E402, F403
