# RAG + 知识图谱学习助手 MVP 使用说明

这份文档用于后续快速读取当前实现，不代替完整设计文档。完整设计见 `docs/RAG_KNOWLEDGE_GRAPH_ASSISTANT.md`。

## 1. 功能定位

当前 MVP 解决三个问题：

- 找资料：某个知识点出现在我的哪些笔记或课程资料里？
- 查解释：某个知识点是什么，原文依据在哪里？
- 看关系：它和哪些概念、tag、课程、章节有关？

它不是完整学习规划系统。暂时不做复杂 LLM 自动抽取、Web UI、多用户权限、PPT/OCR、自动复习计划。

## 2. 数据流

```text
Obsidian Markdown / Markdown / TXT / PDF
        |
        v
obsidian_sync
        |
        +--> rag_index.json      # 文本切块 + 本地轻量检索
        |
        +--> graph_store.json    # 双链/tag/frontmatter 关系图谱
        |
        +--> sync_state.json     # 文件 hash 和同步状态
```

运行数据保存在项目根目录 `.knowledge/` 中：

- `.knowledge/rag_index.json`
- `.knowledge/graph_store.json`
- `.knowledge/sync_state.json`

`.knowledge/` 是本地运行产物，已加入 `.gitignore`。需要重建索引时可以删除后重新同步。

## 3. 核心模块

| 路径 | 职责 |
|------|------|
| `obsidian/parser.py` | 解析 frontmatter、标题、`[[双链]]`、alias、tag |
| `obsidian/vault.py` | 扫描 Obsidian vault 并计算文件 hash |
| `obsidian/sync.py` | 编排同步流程，写入 RAG 索引和图谱 |
| `rag/ingest.py` | 导入 Markdown/TXT/PDF 课程资料 |
| `rag/chunker.py` | 文本切块 |
| `rag/embeddings.py` | 本地确定性 sparse vector |
| `rag/vector_store.py` | JSON 本地向量索引 |
| `graph/local_store.py` | 本地 JSON 图谱 |
| `graph/neo4j_store.py` | 可选 Neo4j adapter |
| `tools/obsidian_tool.py` | Agent 工具 `obsidian_sync` |
| `tools/rag_search.py` | Agent 工具 `rag_search` |
| `tools/graph_query.py` | Agent 工具 `graph_query` |
| `skills/course-learning/SKILL.md` | 课程学习助手 skill |

## 4. `/kb` 命令

`/kb` 是知识库的确定入口。它直接调用本地同步、检索和图谱查询逻辑，不消耗 LLM 调用，也不依赖模型猜工具。

REPL 安装 `prompt_toolkit` 后支持 slash-command 实时提示：输入 `/` 会出现命令候选。若终端不支持实时提示，输入 `/` 回车会显示同一组精简命令。

CLI 使用 Rich 渲染 Agent 回复里的常见 Markdown，标题、列表、代码块、简单表格、引用、粗体和行内代码会显示为终端友好格式。知识库状态和检索结果也会用 Rich 面板/表格展示；如果 Rich 不可用，会回退到内置轻量渲染。

| 命令 | 用途 |
|------|------|
| `/kb sync <vault> [course_dir] [--full]` | 同步 Obsidian vault 和可选课程资料目录 |
| `/kb status` | 查看 `.knowledge/` 状态 |
| `/kb search <query> [--course name] [--top-k n]` | 检索本地 RAG 索引 |
| `/kb graph <concept> [--intent related] [--limit n]` | 查询知识图谱关系 |
| `/kb reset --yes` | 删除生成的 `.knowledge/` 索引 |

推荐日常使用顺序：

```text
/kb sync demo_vault
/kb status
/kb search Dijkstra 算法
/kb graph Dijkstra 算法
```

`/kb reset` 需要显式加 `--yes`，因为它会删除 `.knowledge/`。这只是删除生成索引，不会删除原始笔记或课程资料。

## 5. Agent 工具

### obsidian_sync

用途：扫描 Obsidian vault，可选同步课程资料目录，生成 `.knowledge/` 本地数据。

参数：

```json
{
  "vault_path": "demo_vault",
  "course_dir": "course_materials",
  "mode": "incremental"
}
```

返回重点字段：

- `scanned_files`: 扫描文件数
- `updated_files`: 本次变更文件数
- `chunk_count`: 写入 RAG 的 chunk 数
- `relationship_count`: 写入图谱的关系数
- `graph_backend`: `local_json` 或 `neo4j`

### rag_search

用途：检索课程资料和 Obsidian 笔记，适合回答“是什么、在哪里出现过、原文怎么说”。

参数：

```json
{
  "query": "Dijkstra 算法是什么？",
  "course": "数据结构",
  "top_k": 5
}
```

返回：

```json
{
  "results": [
    {
      "text": "匹配文本片段",
      "source": "obsidian/Dijkstra.md",
      "score": 0.87,
      "metadata": {
        "title": "Dijkstra 算法",
        "course": "数据结构",
        "chapter": "图"
      }
    }
  ]
}
```

### graph_query

用途：查询知识点关系，适合回答“和谁有关、有哪些 tag、出现在哪些笔记、属于哪门课/章节”。

参数：

```json
{
  "concept": "Dijkstra 算法",
  "intent": "related",
  "limit": 20
}
```

常用 `intent`：

- `related`: 双链相关概念
- `tags`: 标签
- `mentions`: 出现在哪些笔记
- `course`: 课程和章节
- `prerequisites`: 前置知识，当前本地图谱只保留接口，MVP 不自动抽取复杂前置关系

## 6. 快速演示

创建 demo vault：

```powershell
mkdir demo_vault
notepad demo_vault\Dijkstra.md
```

写入：

```markdown
---
course: 数据结构
chapter: 图
aliases: [单源最短路]
tags: [algorithm]
---

# Dijkstra 算法

Dijkstra 用于求解非负权图中的单源最短路径。

相关知识：[[图]]、[[贪心算法]]、[[优先队列]]
```

启动 Agent：

```powershell
python agent.py
```

在 REPL 中输入：

```text
/kb sync demo_vault
/kb status
/kb search Dijkstra 算法
/kb graph Dijkstra 算法
```

也可以用自然语言让 Agent 选择工具：

```text
Dijkstra 算法是什么？
Dijkstra 算法和哪些知识点有关？
```

预期效果：

- 第一个问题会生成 `.knowledge/`。
- “是什么”类问题优先走 `rag_search`，返回来源片段。
- “和哪些知识点有关”优先走 `graph_query`，返回 `图`、`贪心算法`、`优先队列` 等双链关系。

## 7. Neo4j 配置

Neo4j 是可选能力。设置以下环境变量后会优先尝试 Neo4j：

```text
NEO4J_URI
NEO4J_USERNAME
NEO4J_PASSWORD
```

如果缺少配置、未安装 `neo4j` driver，或连接失败，系统会自动回退到本地 JSON 图谱，不影响 MVP 使用。

## 8. 当前边界

- PDF 只做文本抽取，不做 OCR、表格恢复、版式理解。
- 本地 RAG 使用轻量词袋/sparse vector，目标是稳定跑通闭环，不追求正式 embedding 效果。
- 图谱关系主要来自 Obsidian 双链、tag、frontmatter，不做复杂 LLM 自动关系抽取。
- 工具遵守 workspace 安全边界，默认只能扫描项目 workspace 内路径。

## 9. 验证

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```

当前验证结果：216 passed（含题库系统和知识库管理模块测试）。
