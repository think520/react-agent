# CLAUDE.md

Bobodan（波波蛋）是一个本地优先、Chat-first 的个人学习助手。开始产品、架构或界面工作前，先读 `docs/PROJECT_GUIDE.md`；界面工作还必须读 `docs/DESIGN.md`。

## 当前产品边界

- Chat 是主入口；Library 负责导入、阅读和触发概念提取；Practice / Review 负责练习闭环。
- 原始资料是知识型回答和练习的事实来源。Wiki、概念摘要和个人知识不能冒充原文证据。
- 知识地图只包含用户已审查的概念和关系。未审查候选只显示状态摘要，不参与回答。
- Wiki 已降级为高级维护和历史整理能力，不是一级导航，也不是默认 RAG 中间层。
- 个人知识使用结构化 SQLite 存储，按全局和资料库隔离；旧 Markdown memory / daily 只读保留用于迁移。
- `.knowledge/` 是可重建运行时索引，但旧 `rag_index*.json`、`graph_store.json` 和旧记忆文件可能是用户唯一历史数据，迁移完成前不得静默删除。

## 常用命令

```powershell
python agent.py
python agent.py --session-id <id>

.venv\Scripts\python.exe -m pytest -q

cd web/frontend
npm run lint
npm run build
npm test -- --run
```

主要 CLI 命令：

```text
/kb sync <vault> [course_dir] [--full]
/kb status
/kb search <query> [--course name] [--top-k n]
/kb graph <concept> [--limit n]
/kb reset --yes

/quiz generate <topic> [--count n] [--course name]
/quiz start [count] [--course name]
/quiz wrong | weak | stats

/learning plan <goal>
/learning progress [concept]
/learning review | today | plans
/learning mark <concept> mastered|learning|needs_review

/memory list | show | search | forget | stats | review
/memory legacy

/wiki init <vault>
/wiki lint [vault]
/wiki status [vault]
```

旧 `/wiki ingest`、旧 memory save/recall/daily 工具和旧 `graph_query` 已退役，不要重新接回。

## 架构真相

```text
core/
  agent_loop.py       ReAct 循环、工具执行、运行时证据门禁
  session.py          会话模型和 JSON 持久化
  db.py               SQLite 连接、WAL、busy_timeout 和迁移帮助函数
  llm_json.py         统一 LLM JSON 提取与修复

service/
  agent_service.py    Provider、会话和 Agent 运行入口
  kb_service.py       资料同步、查询、RAG 和高级 Wiki 维护
  concept_service.py  概念提取、候选审查和知识地图
  memory_service.py   个人知识、候选、事件和旧记忆迁移
  quiz_service.py     出题、练习、批改、错题变式
  learning_service.py 学习计划、SM-2 复习和掌握度

rag/
  sqlite_store.py     documents/chunks/FTS5 真相源；中文 CJK 2-gram
  qdrant_store.py     可降级的向量索引
  hybrid.py           vector + FTS5 → RRF
  directory.py        文档级路由
  grep_retriever.py   原文定位
  retriever.py        按资料库缓存的统一检索入口和能力状态

graph/
  concept_store.py    已审查概念、关系、证据、候选和布局位置

memory/
  personal_store.py   全局 / 资料库个人知识、学习事件和候选队列
  legacy.py           旧 Markdown 记忆只读解析

wiki/
  extractor.py        概念提取器：LLM 从资料提取概念候选与关系
  workflow.py         维护计划和用户确认工作流
  orchestration.py    大型任务、预算、恢复和检查点
  lint.py             只读健康检查
  utils.py            共享文件名和 LLM JSON 工具

web/backend/          FastAPI 路由、稳定 SSE 和错误信封
web/frontend/         React 桌面 UI；Zustand 管理跨页状态；路由按需加载
```

以下模块已经删除，禁止恢复为正常运行时依赖：

- `core/memory.py`、`memory/store.py`、`memory/search.py`、`memory/daily.py`
- `rag/chunker.py`、`rag/vector_store.py`、`rag/embeddings.py`
- `graph/local_store.py`、`graph/neo4j_store.py`、`graph/store.py`、`graph/schema.py`
- `wiki/compiler.py`

## 关键契约

### Agent 和证据

- 知识型问题默认以 `library_search` / `rag_search` 的原始 chunk 为证据骨架。
- `concept_map_query` 只读取已审查图谱，用来补充结构；候选不能绕过审查进入回答。
- `personal_knowledge_recall` 只调整讲解方式或补充明确标注的个人上下文。
- `service/evidence_policy.py` 和 AgentLoop 结束前验证共同构成运行时证据门禁。Prompt 只是指导，不是质量保证。
- stale 概念证据可以继续展示关系，但不能满足原文证据门禁；需要重新定位或重新检索。

### RAG

- SQLite `knowledge.db` 是唯一 RAG 真相源；不存在时返回 `retrieval_mode="unavailable"`，不回退旧 JSON。
- 无向量能力时返回 `fts_only`，前端必须让降级可见。
- FTS5 索引含 NFKC/casefold 和中文 2-gram 搜索文本；旧索引在打开时按需迁移重建。
- RetrievalOrchestrator 按 workspace + RAG 配置缓存；缓存连接跨线程使用时必须由管线锁保护，reset 前必须清缓存。
- `document_id` 是资料稳定 ID；新概念证据尽量带 `chunk_id`。旧证据可空，不强制模糊回填。

### 知识地图和迁移

- 资料同步不再写旧 JSON / Neo4j 图。概念必须经过“提取候选 → 用户审查 → 写入图谱”。
- `graph_store.json` 只在“设置 → 记忆与数据”惰性检测。
- Concept 和语义关系进入迁移候选；Memory 永远不进入概念图谱，只能进入个人知识候选。
- 薄 Memory、可能重复和被旧 Markdown 流程覆盖的项目必须在预览里说明；模糊重复只提示，不自动跳过。
- 迁移成功并校验后才归档旧 JSON，同时记录 SHA-256、迁移时间和数量。

### 个人知识

- `personal_knowledge` 是长期知识真相源；请求级 `personalization_context` 有长度上限。
- 旧 `.bobodan/memory/*.md` 和 `.bobodan/daily/*.md` 不再写入、不再注入 system prompt。
- 明确用户要求通过确认卡或管理页面写入；自动整理只能生成候选。
- 资料库请求必须带正确 library 上下文，不能跨库读取资料、错题或学习事件。

### 练习和复习

- Question 的来源由检索结果确定性保存，模型只能选择 `source_ids`，不能自行编造来源。
- 批改解析失败重试一次；仍失败返回 `grading_unavailable`，不能记为答错。
- 错题重练使用“原题 + 用户错误答案 + 原文证据”生成不同问法，不能只重放原题。
- 复习调度使用保守 SM-2：首次 1 天、第二次 6 天、之后按 ease factor 增长；答错重置为 1 天，ease 最低 1.3。

### Provider

- `LLMProvider` 必须提供 `name`、`model`、`complete()`、`complete_stream()` 和 `get_name()`。
- Provider 失败使用 `ProviderError`、`ProviderTimeout`、`ProviderConnectionError`、`ProviderConfigError`。
- 配置错误不可静默降级；流式输出一旦已经 yield 内容，中途失败不得从头重试，避免重复回答。
- MiniMax 流式工具调用在完整拒绝检测前缓存；拒绝回答不得执行缓冲工具调用。

### 服务和 Web

- 服务返回 `service/_result.py` 的 `{ok, ...}` 或 `{ok: false, code, error}`。
- FastAPI 使用 `unwrap_service_result`，按结构化 code 映射 HTTP，不用错误字符串猜状态。
- SSE 事件解析必须容忍坏帧；会话保存放在流生成器 `finally`，断线也保存已完成内容。
- 正文不展示模型原始思维链。过程只显示中文状态、工具摘要、引用和结构化 artifact。

## 编码纪律

- 修改前先定义可验证成功条件；优先写回归测试复现 bug。
- 只做与任务相关的最小改动，不顺手重构邻近代码。
- 文件搜索优先 `rg`；不可用时再用 PowerShell `Select-String`。
- 文件编辑使用 `apply_patch`，保留用户已有未提交改动。
- 删除或归档用户数据前先验证精确路径和迁移结果。
- 不把旧 JSON、旧 Markdown 记忆或 Wiki 整理页重新接成回答事实来源。
- 当前发布目标是 Windows 桌面端；除非用户重新要求，不执行移动端验收。

## Git

- Commit 使用简洁英文 conventional prefix。
- 不提交 API key、个人配置、`.knowledge/`、构建产物或临时文件。
- 只在用户明确要求时 push；本任务只提交，不推送。
