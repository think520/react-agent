# AGENTS.md

Bobodan（波波蛋）是本地优先、Chat-first 的个人学习助手。开始产品、架构或界面工作前，先按 `docs/README.md` 的「按任务查文档」路由表定位：产品边界 / 发布看 `docs/PROJECT_GUIDE.md`，界面看 `docs/DESIGN.md`，常用命令、架构目录与关键契约见 `docs/ARCHITECTURE_AND_CONTRACTS.md`。

（本文件是根目录唯一指令源；`CLAUDE.md` 与其保持内容一致，由 `tests/test_architecture_boundaries.py` 守护，修改时需同步。）

## 红线（每轮都适用）

- 知识型回答以 `rag_search` 的原始 chunk 为证据骨架（不存在 `library_search` 工具）；`concept_map_query` 只读已审查图谱补结构。证据门禁由 `service/evidence_policy.py` + AgentLoop 结束前校验共同构成——Prompt 只是指导，不是质量保证；stale 概念证据可展示关系但不能满足原文证据门禁。
- 引用用 `[Sxxxxxx]` 标签（`rag/citations.py::cite_label` 确定性生成），必须来自本轮证据；`CitationPolicy` 只核对「引用真实」，不核对「引用支持结论」。
- 正文不展示模型原始思维链；过程只显示中文状态、工具摘要、引用和结构化 artifact。
- 配置错误不可静默降级。`knowledge.db` 不存在时返回 `retrieval_mode="unavailable"` 不回退旧 JSON；无向量能力返回 `fts_only` 且前端必须让降级可见；流式输出一旦已 yield 内容，中途失败不得从头重试。
- 资料库请求必须带正确 library 上下文，不能跨库读取资料、错题或学习事件。
- 掌握度只有一个读取口径：`learning/contract.py`（事实 `mastery_attempts`，估计 `engine` 纯函数，调度 SM-2 `next_review`）；库里的 `mastery.status` / `mastery.score` 只是历史快照，不得用于判断。
- 原始资料是知识型回答和练习的事实来源；Wiki、概念摘要和个人知识不能冒充原文证据。原始资料不会被 AI 擅自修改、移动或删除；任何移动/重命名只在用户确认后执行，且可一键撤销（完整约束见 `docs/LIBRARY_TREE_DESIGN.md:81`）。
- 知识地图只包含用户已审查的概念和关系；未审查候选只显示状态摘要，不参与回答。
- `.knowledge/` 是可重建运行时索引，但旧 `rag_index*.json`、`graph_store.json` 和旧记忆文件可能是用户唯一历史数据，迁移完成前不得静默删除。
- Wiki 是高级维护与历史整理能力，不是一级导航，也不是默认 RAG 中间层（决策见 `docs/ROADMAP.md` §5「D-WIKI」：旧数据只读保留、可生成但只作高级维护入口、底座服务 AI 整理、绝不作为回答或出题证据）。
- 已删除模块禁止恢复为正常运行时依赖：`core/memory.py`、`memory/store.py`、`memory/search.py`、`memory/daily.py`、`rag/chunker.py`、`rag/vector_store.py`、`rag/embeddings.py`、`graph/local_store.py`、`graph/neo4j_store.py`、`graph/store.py`、`graph/schema.py`、`wiki/compiler.py`。
- 已退役、不要重新接回：旧 `/wiki ingest`、旧 memory save/recall/daily 工具、旧 `graph_query`。
- 个人知识使用结构化 SQLite 存储，按全局和资料库隔离；旧 Markdown memory / daily 只读保留用于迁移。

## 编码纪律

- 修改前先定义可验证成功条件，优先写回归测试复现 bug；改动保持 minimal，不顺手重构邻近代码。
- 文件搜索优先 `rg`；不可用时再用 PowerShell `Select-String`。
- 编辑时保留用户已有未提交改动。
- 删除或归档用户数据前先验证精确路径和迁移结果；不把旧 JSON、旧 Markdown 记忆或 Wiki 整理页重新接成回答事实来源。
- 当前发布目标是 Windows 桌面端；除非用户重新要求，不执行移动端验收。

## Git

- Commit 使用简洁英文 conventional prefix。
- 不提交 API key、个人配置、`.knowledge/`、构建产物或临时文件。
- 只在用户明确要求时 push；本任务只提交，不推送。
