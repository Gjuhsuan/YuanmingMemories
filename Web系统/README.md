# 圆明园事件知识图谱 · Web 系统

## 部署

### 前置条件

- Python 3.11+
- Node.js 22+
- Neo4j 已启动，数据已导入（`bolt://localhost:7687`，用户 `neo4j`，密码 `ymysj123`）

### 1. 安装后端依赖

```bash
cd Web系统
pip install -r backend/requirements.txt
```

### 2. 安装前端依赖并构建

```bash
cd frontend
npm install
npm run build
```

### 3. 配置 LLM API Key（可选）

不配置则 AI 问答返回检索结果预览。

```bash
# Linux / macOS
export LLM_API_KEY=sk-xxxxxxxx
export LLM_BASE_URL=https://api.deepseek.com/v1
export LLM_MODEL=deepseek-v4-flash

# Windows PowerShell
$env:LLM_API_KEY = "sk-xxxxxxxx"
$env:LLM_BASE_URL = "https://api.deepseek.com/v1"
$env:LLM_MODEL = "deepseek-v4-flash"
```

支持的所有环境变量见 `backend/settings.py`。

### 4. 启动

```bash
cd Web系统
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 **http://localhost:8000**。

### 开发模式

```bash
# 终端1
cd Web系统
uvicorn backend.main:app --reload --port 8000

# 终端2
cd Web系统/frontend
npm run dev
```

前端 **http://localhost:5173**，Vite 自动代理 `/api` 到后端。
