# YuanmingMemories

## 数据导入 Neo4j

### 1. 配置系统变量

将 Neo4j 密码配置为名为 NEO4J_PASSWORD 的系统变量（用户名和数据库名默认为 `neo4j`，无需额外配置）：

### 2. 运行导入数据的代码

确保 Neo4j 已启动，且用户名和数据库名均为 `neo4j`（默认值），用户密码也已配置为系统变量，会自动清空现有数据库并重新导入数据。

```bash
python import_to_neo4j.py
```
