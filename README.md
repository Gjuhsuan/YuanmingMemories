# 圆明园事件知识图谱 · Web 系统

基于 FastAPI + Vue 3 的圆明园历史事件知识图谱浏览与智能问答系统。数据存储在 Neo4j 图数据库中，集成了 GraphRAG 深度检索与 LLM 问答能力。

## 前置条件

| 依赖    | 版本要求                         |
| ------- | -------------------------------- |
| Python  | 3.11+                            |
| Node.js | 18+                              |
| Neo4j   | 已启动（Community Edition 即可） |

## 第一步：数据导入 Neo4j

### 1. 启动 Neo4j

确保 Neo4j 数据库已启动，默认连接参数：

- URI: `bolt://localhost:7687`
- 用户名: `neo4j`
- 数据库名: `neo4j`

### 2. 配置密码（可选）

脚本默认从环境变量 `NEO4J_PASSWORD` 读取密码。如果你的 Neo4j 密码不是默认值，请先设置：

**Windows PowerShell:**

```powershell
$env:NEO4J_PASSWORD = "你的密码"
```

**Windows CMD:**

```cmd
set NEO4J_PASSWORD=你的密码
```

**Linux / macOS:**

```bash
export NEO4J_PASSWORD=你的密码
```

### 3. 运行导入

```bash
cd YuanmingMemories
pip install neo4j
python import_to_neo4j.py
```

脚本会自动清空现有数据库并重新导入。导入的数据包括：

- **阶段一**（`stage1_results.jsonl`）：事件（Event）节点
- **阶段二**（`stage2_results.normalized.jsonl`）：实体节点、属性、关系

可选参数：

```bash
python import_to_neo4j.py --skip-stage1    # 只导入阶段二
python import_to_neo4j.py --skip-stage2    # 只导入阶段一
python import_to_neo4j.py --clear          # 导入前清空数据库（默认行为）
```

---

## 第二步：安装依赖

### 后端（Python）

```bash
conda env create -f environment.yml
```

主要依赖：`fastapi`、`uvicorn`、`neo4j`、`pydantic`、`anthropic`、`httpx`、`sse-starlette`

### 前端（Node.js）

```bash
cd Web系统/frontend
npm install
```

主要依赖：`vue 3`、`@antv/g6`（图可视化）、`pinia`（状态管理）、`axios`

---

## 第三步：启动系统

### ① 启动后端

```bash
uvicorn Web系统.backend.main:app --reload --port 9090 --host 127.0.0.1
```

后端运行在 **http://127.0.0.1:9090**，启动时会自动：

- 检查 Neo4j 连接
- 初始化全文索引
- 预热 GraphRAG 图底座索引

### ② 启动前端（开发模式）

另开一个终端：

```bash
cd Web系统/frontend
npm run dev
```

前端运行在 **http://localhost:5173**，Vite 自动将 `/api` 请求代理到后端 `127.0.0.1:9090`。

> 浏览器访问 **http://localhost:5173** 即可使用。

---

## 配置 LLM 问答（可选）

不配置也不影响图谱浏览功能，但 AI 问答将只返回检索结果预览，不会生成自然语言回答。

### 方式一：使用 DeepSeek（默认）

**Windows PowerShell:**

```powershell
$env:LLM_API_KEY = "sk-xxxxxxxx"
$env:LLM_BASE_URL = "https://api.deepseek.com/v1"
$env:LLM_MODEL = "deepseek-v4-flash"
```

### 方式二：使用 Anthropic Claude

```powershell
$env:LLM_PROVIDER = "anthropic"
$env:LLM_API_KEY = "sk-ant-xxxxxxxx"
$env:LLM_MODEL = "claude-sonnet-4-6"
```

### 全部环境变量

| 变量                           | 默认值                          | 说明                                         |
| ------------------------------ | ------------------------------- | -------------------------------------------- |
| `NEO4J_URI`                  | `bolt://localhost:7687`       | Neo4j 连接地址                               |
| `NEO4J_USER`                 | `neo4j`                       | Neo4j 用户名                                 |
| `NEO4J_PASSWORD`             | `ymysj123`                    | Neo4j 密码                                   |
| `NEO4J_DATABASE`             | `neo4j`                       | Neo4j 数据库名                               |
| `LLM_PROVIDER`               | `openai`                      | LLM 协议：`openai`（兼容）或 `anthropic` |
| `LLM_API_KEY`                | —                              | API Key                                      |
| `LLM_BASE_URL`               | `https://api.deepseek.com/v1` | API 地址                                     |
| `LLM_MODEL`                  | `deepseek-v4-flash`           | 模型名称                                     |
| `RAG_RETRIEVE_TOPK`          | `40`                          | GraphRAG 检索 Top-K                          |
| `RAG_HOPS`                   | `2`                           | 子图扩展跳数                                 |
| `CHAT_RATE_LIMIT_PER_MINUTE` | `20`                          | 问答速率限制                                 |

---

## 功能概览

- **本体结构** — 浏览知识图谱的本体类层次，点击查看类定义与关联属性
- **图谱探索** — 以力导向图浏览事件与实体，支持按类型筛选，点击节点查看档案影像与详情
- **智能问答** — 基于 GraphRAG 的深度检索问答，支持多轮对话、引用溯源、思考过程可视化

---

## 项目结构

```
YuanmingMemories/
├── config.py                      # Neo4j 连接配置 + 本体术语中英文映射
├── import_to_neo4j.py             # 数据导入 Neo4j 脚本
├── ontology.ttl                   # 领域本体定义（OWL/TTL）
├── entries_simplified.jsonl       # 实体条目数据
├── stage1_results.jsonl           # 阶段一：事件抽取结果
├── stage2_results.normalized.jsonl# 阶段二：实体与关系归一化结果
├── archive_pages/                 # 档案页面数据
│
└── Web系统/
    ├── backend/
    │   ├── main.py                # FastAPI 应用入口
    │   ├── settings.py            # 环境变量集中管理
    │   ├── routers/               # API 路由（ontology, archive, chat, graph, node, cypher）
    │   ├── services/              # 业务逻辑（检索、LLM、GraphRAG 索引等）
    │   ├── graphrag/              # GraphRAG 模块（规划→检索→证据评估→答案合成）
    │   └── requirements.txt
    │
    └── frontend/
        ├── src/
        │   ├── pages/             # 页面组件（本体结构、图谱探索、智能问答）
        │   ├── components/        # UI 组件（图谱画布、档案面板、聊天面板等）
        │   ├── stores/            # Pinia 状态管理
        │   └── api/               # 后端 API 调用层
        ├── vite.config.ts         # Vite 配置（含 /api、/static 代理）
        └── package.json
```
