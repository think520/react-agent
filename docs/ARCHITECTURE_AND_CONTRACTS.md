# Bobodan 架构、命令与关键契约

> 本页是从 `PROJECT_GUIDE.md` 抽出的轻量工程速查（2026-11-20），供人与各类 Agent 快速查架构目录、常用命令、依赖边界与运行时契约；产品定位与发布门槛见 [`PROJECT_GUIDE.md`](PROJECT_GUIDE.md)，排期与门禁见 [`ROADMAP.md`](ROADMAP.md)。

---

## 1. 常用命令与运行

```powershell
# CLI / 单进程 Web
python agent.py
python agent.py --session-id <id>
python agent.py web

# 全量本地质量门禁（Ruff + 架构/替身门禁 + pytest + 前端 lint/tsc/vitest/build）
.\scripts\quality.ps1

# 单独跑后端 / 前端
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

聊天侧命令另有 `/wiki plan`、`/wiki update`（Web 对话内发起 Wiki 计划与增量更新，不是 CLI 命令；见 `web/frontend/src/lib/commandRouter.ts`）。

---

## 2. 架构目录树

```text
core/
  agent_loop.py           ReAct 循环、工具执行、运行时证据门禁
  session.py              会话模型和 JSON 持久化
  db.py                   SQLite 连接、WAL、在线备份、完整性校验与迁移记账
  event_log.py            SSE 重连事件日志（open_connection 显式关闭）
  persistence_registry.py 全部持久化文件名注册表（由 test_persistence_tripwire.py 守护）
  llm_json.py             统一 LLM JSON 提取与修复

service/
  agent_service.py        Provider、会话和 Agent 运行入口
  kb_service.py           资料同步、导入、文档列表、检索（KBService 入口）
  library_files.py        文件树、移动 / 重命名、AI 整理与撤销台账、文件夹、归档（mixin）
  wiki_maintenance.py     高级 Wiki 维护：健康检查、修复、页面、计划与运行（mixin）
  turn_policy.py          每轮预检索 + 运行时证据门禁，Web 与 CLI 共用
  concept_service.py      概念提取、候选审查和知识地图
  memory_service.py       个人知识、候选、事件和旧记忆迁移
  quiz_service.py         出题、练习、批改、错题变式
  learning_service.py     学习计划、SM-2 复习和掌握度
  backup_service.py       整库在线备份（WAL 一致）、SHA-256 校验、干净目录恢复与失败回滚

rag/
  sqlite_store.py         documents/chunks/FTS5 真相源；中文 CJK 2-gram
  qdrant_store.py         可降级的向量索引
  hybrid.py               vector + FTS5 → RRF
  directory.py            文档级路由
  grep_retriever.py       原文定位
  retriever.py            按资料库缓存的统一检索入口和能力状态

graph/
  concept_store.py        已审查概念、关系、证据、候选和布局位置

memory/
  personal_store.py       全局 / 资料库个人知识、学习事件和候选队列
  legacy.py               旧 Markdown 记忆只读解析

wiki/
  extractor.py            概念提取器：LLM 从资料提取概念候选与关系
  workflow.py             维护计划和用户确认工作流
  orchestration.py        大型任务、预算、恢复和检查点
  lint.py                 只读健康检查
  utils.py                共享文件名和 LLM JSON 工具

web/backend/              FastAPI 路由、稳定 SSE、错误信封与 /api/backup/*
web/frontend/             React 19 桌面 UI；Zustand 跨页状态；路由按需加载
```

---

## 3. 依赖方向（由 `scripts/check_architecture.py` 强制检查）

- 允许：`React UI → FastAPI → Runtime Composition / service → domain modules (rag/graph/quiz/learning/memory/knowledge/wiki/research)`。
- 禁止：
  - `FastAPI router` 直接 `import sqlite3` 或绕过 service 查库；
  - `providers → tools`；`rag → quiz / learning`；`domain modules → cli / web`。

---

## 4. 关键运行时契约

### Agent 和证据

- 知识型问题默认以 `rag_search` 的原始 chunk 为证据骨架（不存在 `library_search` 工具）。
- `concept_map_query` 只读取已审查图谱，用来补充结构；候选不能绕过审查进入回答。
- 个人知识经 `MemoryService.personalization_context` 注入请求上下文（不是工具），只调整讲解方式或补充明确标注的个人上下文。
- `service/evidence_policy.py` 和 AgentLoop 结束前验证共同构成运行时证据门禁。Prompt 只是指导，不是质量保证。
- stale 概念证据可以继续展示关系，但不能满足原文证据门禁；需要重新定位或重新检索。
- 回答引用用 `[Sxxxxxx]` 标签：`rag/citations.py::cite_label(source_id)` 确定性生成，工具结果、预检索块、网页快照共用同一标签。`CitationPolicy` 无条件挂载，标签必须来自本轮证据，否则先要求重写，重写用尽则剥掉未知标签并说明；它只核对「引用真实」，不核对「引用支持结论」。

### RAG

- SQLite `knowledge.db` 是唯一 RAG 真相源；不存在时返回 `retrieval_mode="unavailable"`，不回退旧 JSON。
- 无向量能力时返回 `fts_only`，前端必须让降级可见。
- FTS5 索引含 NFKC/casefold 和中文 2-gram 搜索文本；旧索引在打开时按需迁移重建。
- RetrievalOrchestrator 按 workspace + RAG 配置缓存；缓存连接跨线程使用时必须由管线锁保护，reset 前必须清缓存。
- `document_id` 是资料稳定 ID；新概念证据尽量带 `chunk_id`。旧证据可空，不强制模糊回填。

### 知识地图和迁移

- 资料同步不再写旧 JSON / Neo4j 图。概念必须经过「提取候选 → 用户审查 → 写入图谱」。
- `graph_store.json` 只在「设置 → 记忆与数据」惰性检测。
- Concept 和语义关系进入迁移候选；Memory 永远不进入概念图谱，只能进入个人知识候选。
- 薄 Memory、可能重复和被旧 Markdown 流程覆盖的项目必须在预览里说明；模糊重复只提示，不自动跳过。
- 迁移成功并校验后才归档旧 JSON，同时记录 SHA-256、迁移时间和数量；中途失败必须回滚写入并保留原文件。

### 个人知识

- `personal_knowledge` 是长期知识真相源；请求级 `personalization_context` 有长度上限。
- 旧 `.bobodan/memory/*.md` 和 `.bobodan/daily/*.md` 不再写入、不再注入 system prompt。
- 明确用户要求通过确认卡或管理页面写入；自动整理只能生成候选。
- 资料库请求必须带正确 library 上下文，不能跨库读取资料、错题或学习事件。

### 练习和复习

- Question 的来源由检索结果确定性保存，模型只能选择 `source_ids`，不能自行编造来源。
- 批改解析失败重试一次；仍失败返回 `grading_unavailable`，不能记为答错。
- 错题重练使用「原题 + 用户错误答案 + 原文证据」生成不同问法，不能只重放原题。
- 复习调度使用保守 SM-2：首次 1 天、第二次 6 天、之后按 ease factor 增长；答错重置为 1 天，ease 最低 1.3。
- 掌握度只有一个读取口径：`learning/contract.py`。事实是 `mastery_attempts`（`evidence_key` 幂等），估计是 `engine` 的纯函数（带 `algorithm` 版本），调度是 SM-2 的 `next_review`。库里的 `mastery.status` / `mastery.score` 只是历史快照与无历史时的回退值，不得用于判断；手动标记存 `manual_status` / `manual_at`。

### Provider

- `LLMProvider` 必须提供 `name`、`model`、`complete()`、`complete_stream()` 和 `get_name()`。
- Provider 失败使用 `ProviderError`、`ProviderTimeout`、`ProviderConnectionError`、`ProviderConfigError`。
- 配置错误不可静默降级；流式输出一旦已经 yield 内容，中途失败不得从头重试，避免重复回答。
- MiniMax 流式工具调用在完整拒绝检测前缓存；拒绝回答不得执行缓冲工具调用。
- 编辑已保存供应商时，拉取 `/models` 仅在请求 `base_url` 与已存配置同源时在服务端复用已存 API Key，绝不下发原密钥给前端。

### 服务和 Web

- 服务返回 `service/_result.py` 的 `{ok, ...}` 或 `{ok: false, code, error}`。
- FastAPI 使用 `unwrap_service_result`，按结构化 code 映射 HTTP，不用错误字符串猜状态。
- SSE 事件解析必须容忍坏帧；会话保存放在流生成器 `finally`，断线也保存已完成内容。
- 正文不展示模型原始思维链。过程只显示中文状态、工具摘要、引用和结构化 artifact。

### 备份、恢复与迁移回滚（W4-RESTORE-01）

- SQLite 数据库备份必须通过 `core/db.py::backup_sqlite`（SQLite 在线备份 API + `PRAGMA integrity_check`），不得裸拷贝带 `-wal`/`-shm` 的活跃数据库文件；替换本地 `.db` 前必须清理过期 sidecar。
- 备份默认严格排除 `provider.json`（云端 API 密钥）、`.env*` 与本机 `libraries.json` 路径表，并在 `backup_manifest.json` 显式披露包含/排除清单。
- 备份内 `knowledge.db` 的工作区路径归一化为相对 POSIX 路径，恢复到新目录时自动重定位，确保跨路径恢复后原件阅读、引用与错题回溯可用。
- 恢复前必须完成 Zip Slip / 符号链接防御、全量 SHA-256 与 SQLite 完整性校验；拒绝覆盖非空目标目录；恢复或迁移（资料库迁移、旧图谱迁移）中途失败必须回滚到操作前状态。
