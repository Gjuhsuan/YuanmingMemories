#!/bin/bash
# 圆明园事件知识图谱 Web 系统 — 一键启动
# 用法：bash start.sh <API_KEY>
# 示例：bash start.sh sk-xxxxxxxxxxxxxxxx

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "========================================"
echo "  圆明园事件知识图谱 Web 系统"
echo "========================================"

# 获取 API Key：优先命令行参数，否则交互输入
if [ -n "$1" ]; then
    export LLM_API_KEY="$1"
else
    echo -n "请输入 DeepSeek API Key: "
    read -r LLM_API_KEY
fi

if [ -z "$LLM_API_KEY" ]; then
    echo "[!] API Key 不能为空"
    exit 1
fi
export LLM_API_KEY
echo "[OK] API Key 已设置"

# 检查 Neo4j
if command -v neo4j &>/dev/null; then
    neo4j status &>/dev/null || {
        echo "[!] Neo4j 未运行，尝试启动..."
        neo4j start
        sleep 3
    }
    echo "[OK] Neo4j 运行中"
else
    echo "[!] 未检测到 neo4j，请确保 Neo4j 已启动"
fi

# 清理旧端口
echo "[..] 清理端口..."
lsof -ti:8000 2>/dev/null | xargs kill 2>/dev/null || true
sleep 1

# 检查前端依赖
if [ ! -d "frontend/node_modules" ]; then
    echo "[..] 安装前端依赖..."
    cd frontend && npm install --silent && cd ..
fi

# 启动后端（后台）
echo "[..] 启动后端..."
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 3

if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "[!] 后端启动失败"
    exit 1
fi
echo "[OK] 后端已启动"

# 启动前端（前台）
echo ""
echo "  >>> 打开 http://localhost:5173 <<<"
echo ""
cd frontend && npm run dev

# 前端退出后清理
kill $BACKEND_PID 2>/dev/null || true
