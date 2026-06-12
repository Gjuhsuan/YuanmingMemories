"""
FastAPI 入口 —— 注册路由、CORS、SSE、生命周期。

启动：uvicorn backend.main:app --reload --port 8000
"""
import sys
from pathlib import Path

# 确保 backend 包可导入
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .settings import CORS_ORIGINS
from .db import health_check, ensure_fulltext_index, close


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时健康检查 + 初始化索引，关闭时释放连接。"""
    # 启动
    print("[backend] 检查 Neo4j 连接...")
    if health_check():
        print("[backend] [OK] Neo4j 连接成功")
        print("[backend] 初始化全文索引...")
        if ensure_fulltext_index():
            print("[backend] [OK] 全文索引就绪")
        else:
            print("[backend] [WARN] 全文索引创建失败（可能已存在）")
    else:
        print("[backend] [FAIL] Neo4j 连接失败！请确认数据库已启动。")

    # 预热 GraphRAG 索引（在线程池中构建，避免阻塞启动）
    import asyncio
    try:
        print("[backend] 预热 GraphRAG 图底座索引...")
        loop = asyncio.get_event_loop()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as pool:
            await loop.run_in_executor(pool, _warm_graphrag_index)
        print("[backend] [OK] GraphRAG 索引预热完成")
    except Exception as e:
        print(f"[backend] [WARN] GraphRAG 索引预热失败（将在首次请求时懒加载）: {e}")

    yield

    # 关闭
    print("[backend] 释放 Neo4j 连接...")
    close()
    print("[backend] 已关闭")


def _warm_graphrag_index():
    """在后台线程中触发索引构建。"""
    from .services.graphrag_index import get_graphrag_index
    get_graphrag_index()


app = FastAPI(
    title="圆明园事件知识图谱 API",
    description="REST + SSE API for Yuanmingyuan Event KG",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS（开发期）
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局错误处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """兜底错误处理，避免整页崩溃。"""
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": str(exc) or "服务器内部错误",
            }
        },
    )


# ── 注册路由 ──
from .routers import graph, node, cypher, chat, preload, archive

app.include_router(graph.router)
app.include_router(node.router)
app.include_router(cypher.router)
app.include_router(chat.router)
app.include_router(preload.router)
app.include_router(archive.router)

# ── 挂载静态文件 ──
import os as _os
_ARCHIVE_PNG_DIR = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__)))),
    "archive_pages", "png"
)
if _os.path.isdir(_ARCHIVE_PNG_DIR):
    app.mount("/static/archive", StaticFiles(directory=_ARCHIVE_PNG_DIR), name="archive_static")

# 启动时预热预加载缓存
from .routers.preload import get_preload

@app.on_event("startup")
async def warm_preload():
    try:
        get_preload()
    except Exception:
        pass


@app.get("/api/health")
async def health():
    """健康检查端点。"""
    ok = health_check()
    return {
        "status": "ok" if ok else "error",
        "neo4j": "connected" if ok else "disconnected",
    }


# ── 生产静态文件挂载 ──
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists() and FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
