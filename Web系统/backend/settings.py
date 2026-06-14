"""
环境变量集中读取。
所有敏感配置从环境变量注入，绝不硬编码。
"""
import os
from pathlib import Path

# ── Neo4j ──
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "ymysj123")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

# ── LLM Provider ──
# 支持 openai 兼容协议（DeepSeek / OpenAI / 国产模型等）和 anthropic 原生协议
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")  # "openai" | "anthropic"
# API Key：优先 LLM_API_KEY，其次 DEEPSEEK_API_KEY，都没有则为空
LLM_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-flash")
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "2048"))

# ── RAG ──
RAG_RETRIEVE_TOPK = int(os.environ.get("RAG_RETRIEVE_TOPK", "40"))
RAG_HOPS = int(os.environ.get("RAG_HOPS", "2"))
RAG_MAX_CONTEXT_TOKENS = int(os.environ.get("RAG_MAX_CONTEXT_TOKENS", "8000"))
RAG_MAX_SOURCE_CHARS = int(os.environ.get("RAG_MAX_SOURCE_CHARS", "300"))

# ── Rate Limiting ──
CHAT_RATE_LIMIT_PER_MINUTE = int(os.environ.get("CHAT_RATE_LIMIT_PER_MINUTE", "20"))

# ── CORS ──
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

# ── GraphRAG 数据文件路径 ──
# 数据文件位于项目根目录 (YuanmingMemories/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
GRAPHRAG_ENTRIES_PATH = Path(os.environ.get(
    "GRAPHRAG_ENTRIES_PATH",
    str(_PROJECT_ROOT / "entries_simplified.jsonl")
))
GRAPHRAG_STAGE1_PATH = Path(os.environ.get(
    "GRAPHRAG_STAGE1_PATH",
    str(_PROJECT_ROOT / "stage1_results.jsonl")
))
GRAPHRAG_STAGE2_PATH = Path(os.environ.get(
    "GRAPHRAG_STAGE2_PATH",
    str(_PROJECT_ROOT / "stage2_results.normalized.jsonl")
))

# ── GraphRAG Pipeline 配置 ──
GRAPHRAG_MAX_SUBQUESTIONS = int(os.environ.get("GRAPHRAG_MAX_SUBQUESTIONS", "3"))
GRAPHRAG_EVENT_LIMIT_PER_SUB = int(os.environ.get("GRAPHRAG_EVENT_LIMIT_PER_SUB", "4"))
GRAPHRAG_MAX_ITERATIONS = int(os.environ.get("GRAPHRAG_MAX_ITERATIONS", "2"))
GRAPHRAG_RELATED_EVENT_LIMIT = int(os.environ.get("GRAPHRAG_RELATED_EVENT_LIMIT", "12"))
GRAPHRAG_PARALLEL_WORKERS = int(os.environ.get("GRAPHRAG_PARALLEL_WORKERS", "3"))
