# 文化遗产图谱问答系统：Schema-Constrained Agentic Historical GraphRAG

本项目实现了一个面向文化遗产档案的 **Schema-Constrained Agentic GraphRAG** 系统。系统以结构化历史知识图谱为底座，通过大语言模型代理完成问题规划、关系选择、证据评估、反思补检、答案生成与事实校验，目标是在历史档案场景中实现**可解释、可追溯、证据约束的问答**。

与普通 RAG 不同，本系统不是简单地检索若干文本片段后生成答案，而是围绕图谱中的 **事件、实体、关系、文档来源、社区结构** 组织证据链；与传统规则式图谱问答不同，本系统尽量避免写死领域关键词规则，而是让 LLM 在图谱 schema 和候选集合约束下进行动态决策。

---

## 1. 核心设计思想

本系统借鉴了 ToG-2 和 Youtu-GraphRAG 的思路，但针对文化遗产档案问答进行了应用化改造。

### 1.1 Schema-constrained，而不是关键词规则驱动

系统不再依赖诸如“石材、太湖石、赏赐、筵宴、张进朝”等人工关键词规则，而是将图谱中的 schema 提供给 LLM，包括：

- Entity Type
- Event Type
- Relation Type
- Attribute Type
- Documents
- Communities

LLM 根据问题和 schema 决定：

- 问题属于什么任务类型；
- 需要填充哪些答案槽位；
- 应该定位哪些种子实体或事件；
- 应该优先探索哪些关系；
- 当前证据是否足够；
- 哪些事实可以进入最终答案。

### 1.2 Agentic Graph Retrieval

在线问答阶段不是一次性检索，而是由多个 LLM agent 组成闭环：

```text
User Question
→ Planner Agent
→ Plan Verifier
→ Seed Locator
→ Relation Selector
→ Controlled Graph Expansion
→ Evidence Assessor
→ Reflection Agent
→ Evidence Organizer
→ Answer Synthesizer
→ Answer Verifier
→ Final Answer + Evidence
```

其中 Reflection Agent 会判断证据是否足够。如果不足，它不会直接把自然语言追问丢回检索器，而是生成机器可执行的 `SearchAction`，用于补充检索。

### 1.3 Evidence-grounded Answering

最终答案必须基于检索到的图谱证据。系统会尽量区分：

- direct support：直接支持；
- indirect support：间接支持；
- background：背景相关；
- weak：弱相关；
- irrelevant：无关。

Answer Verifier 会在最终输出前检查答案中是否存在不被证据支持的断言，并对答案进行修正。

---

## 2. 项目目录结构

```text
graphrag/
├── __init__.py
├── answer_slots.py
├── community_index.py
├── logging_utils.py
├── slot_filling.py
│
├── agents/
│   ├── __init__.py
│   ├── llm_client.py
│   ├── planner.py
│   ├── plan_verifier.py
│   ├── relation_selector.py
│   ├── evidence_assessor.py
│   ├── reflector.py
│   ├── answer_synthesizer.py
│   └── answer_verifier.py
│
├── graph/
│   ├── __init__.py
│   ├── graph_ops.py
│   └── store_builder.py
│
├── model_defs/
│   ├── __init__.py
│   ├── planning.py
│   ├── retrieval.py
│   ├── evidence.py
│   ├── answer.py
│   └── runtime.py
│
├── retrieval/
│   ├── __init__.py
│   ├── seed_locator.py
│   ├── subgraph_retriever.py
│   ├── subgraph_ranker.py
│   └── subgraph_units.py
│
└── runtime/
    ├── __init__.py
    ├── pipeline.py
    └── evidence_organizer.py
```

---

## 3. 模块说明

### 3.1 `graph/`

负责构建和操作图谱底座。

#### `store_builder.py`

从预处理后的 JSONL 文件中构建统一图谱底座 `GraphSubstrate`，包含：

- `entries`：档案条目；
- `events`：事件节点；
- `entities`：实体节点；
- `event_relations`：事件到实体或事件的关系；
- `entity_relations`：实体间关系；
- `name_index`：名称索引；
- `adjacency`：图邻接表；
- `communities`：社区索引；
- `schema_types`：实体类型集合；
- `schema_relation_types`：关系类型集合；
- `schema_attribute_keys`：属性字段集合。

主要入口：

```python
from graphrag import build_graph_substrate

index = build_graph_substrate(
    entries_path="entries_simplified.jsonl",
    stage1_path="stage1_results.jsonl",
    stage2_path="stage2_results.normalized.jsonl",
)
```

#### `graph_ops.py`

提供底层图操作能力，包括：

- 文本归一化；
- 节点名称查询；
- 节点类型判断；
- 邻居查询；
- 路径搜索；
- 路径格式化。

这些函数供检索模块和证据组织模块调用。

---

### 3.2 `agents/`

负责各类 LLM agent 的调用和逻辑封装。

#### `llm_client.py`

封装底层 LLM API 调用。默认使用 DeepSeek 接口，支持通过环境变量配置：

```bash
export DEEPSEEK_API_KEY="你的 API Key"
export DEEPSEEK_MODEL="deepseek-v4-pro"
export DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"
```

可选参数：

```bash
export DEEPSEEK_THINKING="disabled"
export DEEPSEEK_REASONING_EFFORT=""
```

该模块还包含 JSON 解析与修复逻辑，用于处理 LLM 返回的非严格 JSON。

#### `planner.py`

Planner Agent 负责根据原始问题和图谱 schema 生成初始查询计划，包括：

- `task_type`
- `target_slots`
- `seed_queries`
- `preferred_entity_types`
- `preferred_event_types`
- `relation_policy`
- `subquestions`

该模块强调 schema-aware planning，而不是关键词映射。

#### `plan_verifier.py`

Plan Verifier 负责检查和修正 Planner 的输出，确保：

- 任务类型合理；
- 子问题数量不超过上限；
- target slots 不为空；
- subquestions 可执行；
- plan 中包含必要的 seed queries 和 relation policy。

#### `relation_selector.py`

Relation Selector Agent 负责在给定种子节点和候选关系的条件下，选择最适合当前问题的关系类型。

它对应 ToG-2 中的 relation prune 思想：

```text
seed nodes
→ candidate relations
→ LLM relation selection
→ selected relations
```

注意：LLM 只能从候选关系中选择，不应自由编造不存在的关系。

#### `evidence_assessor.py`

Evidence Assessor 负责对候选事件和证据进行评分，判断其是否应该保留。

输出字段包括：

- `relevance`
- `necessity`
- `support_level`
- `keep`
- `reason`
- `slots`
- `claims`

系统会优先保留 direct / indirect 且 relevance 较高的证据。

#### `reflector.py`

Reflection Agent 负责判断当前证据是否足以回答问题。如果证据不足，它会输出 `SearchAction`，用于下一轮补充检索。

与旧版设计不同，reflection 不再返回泛泛的自然语言追问，而是返回结构化检索动作：

```json
{
  "query": "需要补充检索的问题",
  "purpose": "为什么需要补充检索",
  "seed_queries": ["候选实体或事件"],
  "preferred_relations": ["建议探索的关系"],
  "target_slots": ["需要补齐的槽位"]
}
```

#### `answer_synthesizer.py`

根据整理后的图谱证据生成最终答案。生成时要求：

- 直接回答问题；
- 说明证据链；
- 区分直接证据、间接证据和背景信息；
- 不得把背景相关性提升为确定结论；
- 证据不足时必须明确说明。

#### `answer_verifier.py`

对最终答案进行 claim-level verification。它会检查：

- 答案是否违反原问题的时间、地点、主体等约束；
- 是否混合了不同时期、地点或对象的证据；
- 是否存在未被证据支持的结论；
- 是否需要改写为更保守的答案。

---

### 3.3 `retrieval/`

负责种子定位、关系约束扩展、子图构造和证据排序。

#### `seed_locator.py`

根据 plan 中的 `seed_queries` 和子问题文本，在图谱中定位：

- seed entities
- seed events
- seed communities

如果找不到明确种子，会退回到 lexical event candidates。

#### `subgraph_retriever.py`

核心检索逻辑，负责：

1. 根据 plan 和 subquestion 获取 seed nodes；
2. 汇总候选关系；
3. 调用 Relation Selector 选择关系；
4. 按 selected relations 执行受控图扩展；
5. 构造候选事件集合；
6. 调用 ranker 和 evidence assessor；
7. 返回 `RetrievalUnit`。

这是系统最接近 ToG-style graph exploration 的模块。

#### `subgraph_ranker.py`

负责对候选事件进行排序，并组织为可供 LLM 评估的 evidence items。

排序时会综合考虑：

- candidate score；
- 事件名称；
- 事件类型；
- 日期；
- 原文；
- 文档来源；
- 相关实体；
- 选定关系。

#### `subgraph_units.py`

负责构造不同类型的子图单元，例如：

- event star；
- event path；
- entity ego graph；
- community slice。

这些子图单元可以用于后续证据组织和可视化。

---

### 3.4 `runtime/`

负责完整运行流程。

#### `pipeline.py`

主入口，执行完整 GraphRAG pipeline：

```text
create_plan
→ verify_plan
→ retrieve_for_subquestion
→ reflect_on_evidence
→ supplementary retrieval
→ build_context_text
→ synthesize_answer
→ verify_answer
→ return PipelineResult
```

#### `evidence_organizer.py`

负责将检索结果组织为 LLM 可读的层级化证据上下文，并构建前端可视化所需的图节点和边。

---

### 3.5 `model_defs/`

定义系统中使用的核心数据结构，包括：

- `QuestionPlan`
- `SubQuestion`
- `RelationPolicyItem`
- `RelationChoice`
- `SearchAction`
- `EvidenceAssessment`
- `SubgraphUnit`
- `RetrievalUnit`
- `ReflectionStep`
- `GraphRAGConfig`
- `PipelineResult`

---

## 4. 数据输入格式

系统默认需要三个 JSONL 文件：

```text
entries_simplified.jsonl
stage1_results.jsonl
stage2_results.normalized.jsonl
```

### 4.1 `entries_simplified.jsonl`

每行一个档案条目，至少包含：

```json
{
  "entry_id": "文档 ID",
  "title": "档案标题",
  "date": "日期",
  "body": "正文"
}
```

### 4.2 `stage1_results.jsonl`

用于提供事件抽取结果。系统会读取：

```text
parsed.results[].doc_id
parsed.results[].step_4.events_summary[]
```

事件字段示例：

```json
{
  "event_id": "evt_xxx",
  "event_name": "事件名称",
  "event_type": "事件类型",
  "source_text": "原文依据",
  "date_text": "时间表达"
}
```

### 4.3 `stage2_results.normalized.jsonl`

用于提供实体、关系和属性归一化结果。系统会读取：

```text
parsed.results[].step_1.entities[]
parsed.results[].step_5.final_entities[]
parsed.results[].step_5.final_relations[]
parsed.results[].step_5.final_entity_attributes[]
```

实体字段示例：

```json
{
  "entity_id": "ent_xxx",
  "name": "实体名称",
  "entity_type": "实体类型",
  "aliases": ["别名"],
  "mention_texts": ["原文提及"]
}
```

关系字段示例：

```json
{
  "from_id": "evt_xxx",
  "to_id": "ent_xxx",
  "relation_type": "INVOLVES_OBJECT",
  "evidence": "关系证据"
}
```

属性字段示例：

```json
{
  "entity_id": "ent_xxx",
  "attribute_key": "属性名",
  "attribute_value": "属性值"
}
```

---

## 5. 快速开始

### 5.1 安装依赖

本项目主要依赖 Python 标准库。若需要增强 JSON 修复能力，可安装：

```bash
pip install json-repair
```

如果项目未来接入向量检索、Neo4j 或前端可视化，可根据实际需要安装额外依赖。

### 5.2 设置环境变量

```bash
export DEEPSEEK_API_KEY="你的 API Key"
export DEEPSEEK_MODEL="deepseek-v4-pro"
export DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"
```

Windows PowerShell 示例：

```powershell
$env:DEEPSEEK_API_KEY="你的 API Key"
$env:DEEPSEEK_MODEL="deepseek-v4-pro"
$env:DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"
```

### 5.3 构建图谱底座

```python
from graphrag import build_graph_substrate

index = build_graph_substrate(
    entries_path="entries_simplified.jsonl",
    stage1_path="stage1_results.jsonl",
    stage2_path="stage2_results.normalized.jsonl",
)
```

### 5.4 运行问答

```python
import os
from graphrag import GraphRAGConfig, build_graph_substrate, run_pipeline

index = build_graph_substrate(
    entries_path="entries_simplified.jsonl",
    stage1_path="stage1_results.jsonl",
    stage2_path="stage2_results.normalized.jsonl",
)

config = GraphRAGConfig(
    max_subquestions=3,
    max_iterations=2,
    seed_limit=8,
    relation_limit=5,
    max_depth=3,
    width=3,
    candidate_event_limit=24,
    event_limit_per_subquestion=6,
    evidence_limit=8,
    use_llm_decomposition=True,
    use_llm_relation_prune=True,
    use_llm_evidence_scoring=True,
    use_llm_reflection=True,
    use_llm_answer=True,
    use_llm_verification=True,
)

result = run_pipeline(
    index=index,
    driver=None,
    question="近代圆明园石材被运出的事件主要涉及哪些机构？",
    api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
    config=config,
)

print(result.answer)
print(result.context_text)
print(result.log_path)
```

---

## 6. 配置参数说明

`GraphRAGConfig` 是系统主要配置类。

| 参数                            | 默认值 | 说明                                 |
| ------------------------------- | -----: | ------------------------------------ |
| `max_subquestions`            |      3 | Planner 最多生成多少个子问题         |
| `parallel_workers`            |      3 | 子问题并行检索线程数                 |
| `max_iterations`              |      2 | Reflection 最多补检轮数              |
| `seed_limit`                  |      8 | 最多保留多少个 seed nodes            |
| `relation_limit`              |      5 | Relation Selector 最多选择多少种关系 |
| `max_depth`                   |      3 | 图路径搜索最大深度                   |
| `width`                       |      3 | 每轮扩展宽度                         |
| `candidate_event_limit`       |     24 | 候选事件上限                         |
| `event_limit_per_subquestion` |      6 | 每个子问题最终保留事件数             |
| `related_event_limit`         |     12 | 最终证据图最多保留事件数             |
| `evidence_limit`              |      8 | 每个检索单元证据文本数量             |
| `min_llm_relevance`           |    5.0 | LLM 证据评分保留阈值                 |
| `use_llm_decomposition`       |   True | 是否启用 LLM 规划                    |
| `use_llm_relation_prune`      |   True | 是否启用 LLM 关系选择                |
| `use_llm_evidence_scoring`    |   True | 是否启用 LLM 证据评分                |
| `use_llm_reflection`          |   True | 是否启用 LLM 反思补检                |
| `use_llm_answer`              |   True | 是否启用 LLM 生成答案                |
| `use_llm_verification`        |   True | 是否启用 LLM 答案校验                |

---

## 7. 返回结果说明

`run_pipeline()` 返回 `PipelineResult`：

```python
result.answer          # 最终答案
result.context_text    # 组织后的证据上下文
result.graph_nodes     # 可视化图节点
result.graph_edges     # 可视化图边
result.plan            # 最终查询计划
result.retrieved_units # 每个子问题的检索结果
result.reflections     # 反思与补检记录
result.run_id          # 本次运行 ID
result.log_path        # 日志文件路径
```

可用于调试的内容：

```python
print(result.plan)
print(result.retrieved_units)
print(result.reflections)
print(result.context_text)
```

---

## 8. 日志

系统会通过 `logging_utils.py` 记录运行日志。日志内容包括：

- pipeline start/end；
- planner request/response；
- plan verification；
- relation prune；
- evidence assessment；
- reflection；
- answer synthesis；
- answer verification；
- slot snapshot。

日志通常位于包目录下的：

```text
graphrag_runtime.log
```

可通过：

```python
print(result.log_path)
```

查看实际路径。

---

## 9. 典型问答类型

系统适合处理以下文化遗产档案问题：

### 9.1 事实查询

```text
某个机构在圆明园相关档案中出现于哪些事件？
```

### 9.2 聚合统计

```text
近代圆明园石材被运出的事件主要涉及哪些机构？
```

### 9.3 时间线追踪

```text
皇子等什么时候从海子出发前往圆明园，之后又去了哪里？
```

### 9.4 跨事件推理

```text
某一建筑的修缮活动与财政支出之间有什么关系？
```

### 9.5 证据核查

```text
某个说法是否能被现有圆明园档案图谱支持？
```

---

## 10. 系统运行逻辑示例

以问题：

```text
近代圆明园石材被运出的事件主要涉及哪些机构？
```

为例，系统大致执行：

```text
1. Planner Agent 判断这是聚合型问题，需要 organizations、target_events、documents 等槽位。
2. Seed Locator 定位“圆明园”“石材”等相关 seed nodes。
3. Relation Selector 从候选关系中选择与物项、机构、事件、文档相关的关系。
4. Controlled Graph Expansion 基于 selected relations 搜索候选子图。
5. Evidence Assessor 判断哪些事件直接支持“石材被运出”和“涉及机构”。
6. Reflection Agent 检查是否缺少机构、事件或文档来源。
7. Evidence Organizer 将事件、实体、路径和文档组织成层级化上下文。
8. Answer Synthesizer 生成答案。
9. Answer Verifier 检查答案是否过度概括或包含无证据断言。
10. 输出最终答案和证据链。
```

---

## 11. 设计原则

本项目遵循以下原则：

1. **不写死领域关键词规则**不使用固定关键词决定检索路径，而是通过 schema 和候选集合约束 LLM 决策。
2. **LLM 负责判断，程序负责执行**LLM 不直接访问数据库，也不自由编造关系；程序提供候选实体、候选关系和候选证据，LLM 在候选集合内选择。
3. **先检索证据，再生成答案**答案必须来自 evidence graph，不能依赖模型常识自由发挥。
4. **区分相关性和支持性**同主题不等于支持答案。背景相关事件不能被写成核心证据。
5. **保守回答优先**如果证据不足，系统应明确说明不确定，而不是强行回答。
6. **保留可追溯证据**
   输出结果应尽量包含事件、实体、路径、文档来源等 provenance 信息。

---
