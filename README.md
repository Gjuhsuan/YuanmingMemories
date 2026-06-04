# YuanmingMemories

## 数据导入 Neo4j

### 1. 配置系统变量

将 Neo4j 密码配置为名为 NEO4J_PASSWORD 的系统变量（用户名和数据库名默认为 `neo4j`，无需额外配置）：

### 2. 运行导入数据的代码

确保 Neo4j 已启动，且用户名和数据库名均为 `neo4j`（默认值），用户密码也已配置为系统变量，会自动清空现有数据库并重新导入数据。

```bash
python import_to_neo4j.py
```

## 网站浏览

启动 Streamlit 可视化网站：

```bash
streamlit run app.py
```

网站包含两个页面：
- **档案浏览** — 左侧列表浏览全部档案，点击后左侧展示原文和 AI 分析总结、右侧展示该档案关联的局部知识图谱
- **全局图谱** — 选择一个重要节点（按连接度排序），展示以其为中心的两跳网络

### AI 总结（可选）

如需使用 AI 分析总结功能，配置 DeepSeek API Key：

**Windows (PowerShell):**
```powershell
$env:DEEPSEEK_API_KEY = "sk-xxx"
```

**Windows (CMD):**
```cmd
set DEEPSEEK_API_KEY=sk-xxx
```

**Linux / macOS:**
```bash
export DEEPSEEK_API_KEY=sk-xxx
```

> 不配置也不影响其他功能，页面不会显示 AI 总结按钮。总结结果自动缓存到 `entry_summaries.json`，相同图谱结构不会重复调用 API。
