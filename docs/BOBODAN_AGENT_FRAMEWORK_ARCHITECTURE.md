# Bobodan Agent Framework Architecture

## 1. 结论

Bobodan 不应该继续按“功能不断堆进 CLI/工具文件”的方式扩展。后续应把它框成一个本地优先的个人学习 Agent 框架：

> Bobodan 是一个 local-first 的个人学习 Agent runtime。它通过工具、知识库、记忆、题库、学习路径和 Obsidian/wiki 编译层，把用户的本地资料变成可检索、可复习、可出题、可规划的个人知识系统。

这份文档的目标是定边界：什么模块负责什么，谁可以调用谁，新增功能应该放在哪里。

## 2. 核心原则

- Core 只管 Agent 运行，不管具体业务。
- Provider 只管模型调用，不管工具和学习逻辑。
- Tool 是 Agent 和外部能力之间的接口，不承载复杂业务状态。
- Knowledge 是知识库运行时，不属于 CLI。
- Learning 是学习业务层，不直接处理文件解析。
- Memory 是用户长期上下文，不替代知识库。
- UI 只展示和收集输入，不写核心逻辑。
- 后续扩展必须优先走 plugin / tool / workflow 边界，不直接改核心。

## 3. 顶层分层

```text
UI Layer
  CLI / future Web UI

Service Layer
  service/learning_service  service/quiz_service  service/memory_service
  service/kb_service        service/agent_service
  ↓ CLI and tools both delegate here; returns {"ok": bool, ...} dicts

Agent Runtime Layer
  core / providers / session / event stream

Tool & Extension Layer
  tools / skills / future plugins

Workflow Layer
  wiki ingest / kb sync / quiz generation / learning plan

Knowledge Layer
  rag / graph / wiki / knowledge

Learning Layer
  quiz / learning / review / mastery

Memory Layer
  memory / daily memory / permanent memory / FTS5

Storage Layer
  .knowledge / .bobodan / .session / Obsidian vault
```

## 4. 模块边界

### 4.1 `core/`

职责：

- Agent 主循环
- session 消息管理
- tool call 编排
- event stream 输出
- skills prompt 注入
- memory prompt 注入

不应该做：

- 不解析 PDF/Markdown
- 不直接操作知识库索引
- 不写 UI 渲染
- 不写具体学习业务

允许依赖：

- `providers/`
- `tools/`
- `core/session.py`
- `core/skills.py`
- `core/memory.py`

### 4.2 `providers/`

职责：

- 统一 LLM Provider 接口
- 消息格式转换
- tool call 解析
- stream / non-stream 结果解析
- provider 重试和错误包装

不应该做：

- 不执行工具
- 不保存 session
- 不处理 RAG
- 不处理学习业务

### 4.3 `tools/`

职责：

- 向 Agent 暴露可调用能力
- 参数校验
- 返回 `ToolResult`
- 做轻量编排

不应该做：

- 不承载复杂业务状态
- 不直接写大量核心算法
- 不把 CLI 展示逻辑放进工具

规则：

- 复杂逻辑应放到对应业务模块。
- tool 只做参数适配和结果封装。

示例：

```text
tools/rag_search.py -> 调用 rag/ 或 knowledge/
tools/quiz_tools.py -> 调用 quiz/
tools/wiki_tools.py -> 调用 wiki/
```

### 4.4 `rag/`

职责：

- 文档切块
- embedding provider
- sparse / dense vector store
- vector store router
- RAG 检索

不应该做：

- 不解析 Obsidian 双链业务
- 不生成题目
- 不生成学习路径
- 不直接写 CLI 输出

后续边界：

```text
rag/embeddings.py       # 本地稀疏 embedding
rag/ollama.py           # Ollama embedding client
rag/vector_store.py     # sparse store
rag/dense_store.py      # dense store
rag/router.py           # VectorStoreRouter
```

### 4.5 `knowledge/`

职责：

- 知识库状态管理
- 文档 manifest
- import report
- 知识库统计
- 课程、来源、chunk、图谱的聚合视图

不应该做：

- 不直接做 embedding
- 不直接调用 LLM
- 不直接生成题目

定位：

> `knowledge/` 是 `.knowledge/` 的管理层，不是 RAG 算法层。

### 4.6 `wiki/`

职责：

- LLM wiki 编译
- entity / concept 页面生成
- source registry 管理
- wiki index / log
- wiki lint

不应该做：

- 不复制原始资料全文
- 不替代 `.knowledge/`
- 不把生成内容当 truth source

数据关系：

```text
原始资料 = truth source
wiki 页面 = 编译层
.knowledge = 运行时索引层
```

### 4.7 `graph/`

职责：

- 知识图谱 schema
- 本地图谱 store
- 可选 Neo4j adapter
- 概念关系查询

不应该做：

- 不解析原始文件
- 不生成学习计划
- 不负责向量检索

### 4.8 `quiz/`

职责：

- 题目 schema
- 题库 store
- 题目生成
- 答案批改
- 错题分析

允许依赖：

- `rag/`
- `knowledge/`
- `learning/` 的掌握度数据可以读取，但不要形成循环依赖

不应该做：

- 不直接扫描文件
- 不直接写 Obsidian

### 4.9 `learning/`

职责：

- 学习路径生成
- 掌握度追踪
- 复习计划
- 弱点分析

允许依赖：

- `quiz/`
- `knowledge/`
- `graph/`
- `memory/`

不应该做：

- 不生成底层 RAG 索引
- 不直接操作 vector store

### 4.10 `memory/` 与 `core/memory.py`

职责：

- 用户偏好
- 项目上下文
- 学习状态
- daily memory
- permanent memory
- FTS5 检索

不应该做：

- 不存课程全文
- 不替代 RAG
- 不作为知识库主索引

边界：

```text
memory = 用户和长期上下文
knowledge = 学习资料和知识库
```

### 4.11 `cli/`

职责：

- 用户输入
- 命令解析
- 输出渲染
- 状态展示

不应该做：

- 不写业务核心逻辑
- 不直接处理 RAG 算法
- 不直接操作底层数据库

规则：

- CLI 调 service / tool / router。
- CLI 不应该成为业务中心。

## 5. 依赖规则

允许的方向：

```text
cli -> core/tools/domain modules
tools -> domain modules
core -> providers/tools/session/memory prompt
learning -> quiz/knowledge/graph/memory
quiz -> rag/knowledge
wiki -> rag/knowledge/obsidian/providers
knowledge -> rag/graph/manifest/store
rag -> embeddings/vector stores
```

禁止的方向：

```text
domain modules -> cli
providers -> tools
rag -> quiz
rag -> learning
knowledge -> cli
memory -> cli
```

任何新增模块如果需要跨层调用，先写文档说明依赖方向。

## 6. 扩展点

Bobodan 后续应逐步支持这些扩展点：

### 6.1 Provider

用于新增 LLM：

- MiniMax
- DeepSeek
- OpenAI-compatible
- Ollama chat 后续可选

### 6.2 Embedding Backend

用于新增 embedding：

- local sparse
- Ollama dense
- future OpenAI embedding
- future local sentence-transformer

### 6.3 Vector Store

用于新增索引后端：

- JSON sparse store
- JSON dense store
- FAISS
- Chroma
- LanceDB

### 6.4 Tool

用于暴露 Agent 可调用能力：

- file tools
- RAG tools
- graph tools
- quiz tools
- learning tools
- wiki tools

### 6.5 Skill

用于注入任务说明和领域策略：

- course-learning
- research
- coding
- exam-review

### 6.6 Importer

用于新增资料类型：

- Markdown
- TXT
- PDF
- PPT/PPTX
- DOCX
- web page
- image OCR

### 6.7 Workflow

用于多步骤任务：

- `/kb sync`
- `/wiki ingest`
- `/quiz generate`
- `/learning plan`
- future exam review workflow

## 7. Workflow 边界

复杂任务不要写成一个巨大的 tool。应放到 workflow 层。

推荐结构：

```text
workflow/
  kb_sync.py
  wiki_ingest.py
  quiz_generate.py
  learning_plan.py
```

每个 workflow 应该包含：

- 输入 schema
- 状态对象
- step 列表
- 可恢复状态
- 错误报告
- 最终结果

## 8. 事件与状态

Bobodan 应把运行过程抽象成事件：

```text
assistant_delta
thinking_start
thinking_stop
tool_start
tool_end
workflow_start
workflow_step
workflow_end
error
```

CLI 和未来 Web UI 都只消费事件，不直接深入核心逻辑。

## 9. 数据边界

### `.knowledge/`

存放知识库运行时数据：

- RAG index
- graph store
- manifest
- import report
- quiz database
- learning database

可删除、可重建。

### `.bobodan/`

存放 Agent 个性化数据：

- permanent memory
- daily memory
- memory index
- FTS5 memory db

不应随便删除。

### `.session/`

存放会话历史。

### Obsidian vault

用户的原始资料和可读输出目标。

规则：

- 原始资料是 truth source。
- wiki 页面是编译层。
- `.knowledge/` 是运行时索引。

## 10. 新功能放置规则

新增功能前先判断它属于哪一类：

| 问题 | 放置位置 |
|---|---|
| 新模型供应商 | `providers/` |
| 新 embedding 模型 | `rag/` |
| 新向量库 | `rag/` |
| 新 Agent 工具 | `tools/` + 对应业务模块 |
| 新资料解析 | `ingestion/` 或 `rag/ingest.py` |
| 新知识库状态 | `knowledge/` |
| 新学习功能 | `learning/` |
| 新题库功能 | `quiz/` |
| 新记忆机制 | `memory/` |
| 新 CLI 命令 | `cli/`，但逻辑放业务模块 |
| 新长期流程 | `workflow/` |

## 11. 不要做的事

- 不要把所有能力都塞进 `cli/repl.py`
- 不要让 tool 文件承载业务核心
- 不要让 RAG 层知道 quiz/learning 的细节
- 不要让 memory 存课程原文
- 不要让 wiki 复制源文件全文
- 不要把生成内容当作唯一事实来源
- 不要为了接新模型破坏现有 provider
- 不要为了接 Ollama 替换现有本地检索

## 12. 阶段路线

### P0：边界文档

- 完成本文件
- 后续改动以本文件为准

### P1：RAG 后端抽象

- `OllamaEmbeddingClient`
- `DenseVectorStore`
- `VectorStoreRouter`
- `config.rag`
- `/kb status` 显示 embedding 后端

### P2：Workflow 抽象

- 把 `/kb sync`
- `/wiki ingest`
- `/quiz generate`
- `/learning plan`

逐步变成 workflow。

### P3：Plugin 协议

定义插件可以贡献：

- tools
- skills
- slash commands
- importers
- embedding backends
- vector stores
- workflows

### P4：UI 解耦

CLI 只作为一个客户端。后续 Web UI 通过同一套 runtime/event stream 接入。

## 13. 一句话架构定位

Bobodan 后续不是简单的 CLI Agent，也不是 Pi/OpenClaw 的复制品。

它应该是：

> 一个 local-first learning agent framework：以本地知识库为核心，以 Agent runtime 为调度层，以工具、workflow、memory、quiz、learning、wiki 为扩展能力。

