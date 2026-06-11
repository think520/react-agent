# 更新日志

所有重要变更都记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/)，版本号遵循 [语义化版本](https://semver.org/)。

## [未发布]

### 新增
- **P2 Event Trace 轻量版**: 每次 Agent run 记录关键事件到 JSONL trace 文件，支持事后查看"做了什么、花了多久、哪步失败"。
  - `core/trace.py`（新）: `TraceWriter` 类写入 `.bobodan/traces/{session_id}_{timestamp}_{run_suffix}.jsonl`，只记录 `tool_start` / `tool_end` / `assistant_done` / `error` 事件（不含 `assistant_delta`）。Secret 字段自动 redact，content 超 500 字符截断。线程安全（`threading.Lock`）。
  - `core/agent_loop.py`: `assistant_done` 事件增加 `termination_reason` 字段（`final_answer` / `max_iter` / `error`）；`run_stream` 异常时 yield `assistant_done(termination_reason="error")` 再 re-raise；构造函数接受可选 `trace_writer` 参数，有则自动写入 trace。
  - `cli/repl.py`: 每次 run 创建 `TraceWriter` 并注入 `AgentLoop`；新增 `/trace` 命令（列出最近 run、查看 tool timeline）。
  - `core/trace.py`: 新增 `list_traces` / `read_trace` / `summarize_trace` 读取函数。
  - `tests/test_agent_loop.py`: 覆盖三种 `termination_reason`、`TraceWriter` 文件创建/唯一 run 路径/过滤/截断/redact/错误事件、`AgentLoop` trace 集成、trace 读取/汇总。

- **P3 Workflow Runtime**: 学习计划从"看一眼"变成"可以执行"——自动推断完成状态、追赶模式、手动标记、合并今日任务视图。
  - `learning/schema.py`: `LearningPlan` 增加 `status`（active/completed）和 `current_day` 字段。
  - `learning/store.py`: 新增 `plan_progress` 表（plan_id, day, task_index, source）+ 迁移逻辑 + CRUD 方法（`mark_task_done` / `mark_step_done` / `get_progress` / `get_active_plans` / `update_plan_status`）。
  - `learning/workflow.py`（新）: `PlanWorkflowTracker` — 自动推断 step 完成（所有 topics mastered → 标记完成）、plan 完成时自动 status=completed、进度查询、追赶模式今日任务。
  - `learning/progress.py`: `update_from_quiz` 在答对后自动调用 `check_plan_completion`。
  - `tools/learning_tools.py`: 新增 `learning_plan_progress` 工具（status / complete_task / complete_step / today）。
  - `cli/repl.py`: `/learning today` 合并显示未完成计划任务 + 到期复习清单。
  - `tests/test_workflow.py`（新）: 覆盖 plan_progress CRUD、自动推断、追赶模式、进度汇总、工具集成、ProgressTracker 联动、手动 mastery 标记联动和 SQLite 连接关闭。
  - 769 测试全通过。

- **P1 Obsidian 写回**: 学习计划和做题总结可导出为 Obsidian Markdown，兑现 README 承诺。
  - `tools/obsidian_export.py`（新）: `obsidian_export_plan` 从 LearningStore 读取计划，生成 YAML frontmatter + 按天 checkbox 任务 + `[[双链]]` 知识点引用的 Markdown，写入 `{vault}/学习计划/{title}.md`；`obsidian_export_quiz_summary` 从 QuizStore 读取错题和薄弱点分析，生成按概念分组错题本 + 薄弱点表格 + 掌握度概览的 Markdown，写入 `{vault}/做题总结/{date}.md`。
  - 路径安全检查：`_is_within_workspace` 防止写入 workspace 外路径。
  - `tests/test_obsidian_export.py`（新）: 16 个测试覆盖文件生成、frontmatter、checkbox、wikilink、错题分组、薄弱点表格、掌握度概览、空数据、路径越界、plan 不存在。
  - 716 测试全通过。

- **P0 学习闭环补全**: quiz_submit 自动写每日记忆 + 更新掌握度 + session 完成汇总，做题→记忆→掌握度链路真正跑通。
  - `learning/quiz_integration.py`（新）: `record_quiz_learning_effect` 做题后自动写每日记忆（tags: quiz + 概念）并更新掌握度；`record_quiz_session_summary` 全部答完后写汇总记忆并标记 session 完成。
  - `tools/quiz_tools.py`: `quiz_submit` 在 `store.record_attempt()` 后调用集成函数，失败只 warning 不阻塞返回。返回 data 新增 `session_completed` 字段。
  - `learning/__init__.py`: 导出 `record_quiz_learning_effect`、`record_quiz_session_summary`。
  - `tests/test_quiz_integration.py`（新）: 13 个测试覆盖正确/错误/连续答对→mastered/记忆写入/标签/独立调用/累积状态/未完成不触发汇总/完成触发汇总/弱概念/全对。
  - 掌握度规则：连续答对 2 次 → `mastered`，答对 1 次 → `learning`，答错 → `needs_review`。
  - 700 测试全通过。

- **CLI 轻量状态行收尾**: `Thinking` / `Checking` / `Working` / `Drafting` / `Polishing` 状态词按 Bobodan 设计语言分色显示，spinner 保持稳定强调色，elapsed 保持 dim，减少单色刷新疲劳；tool running 行统一为 clay/orange，success/error 继续使用 green/red。覆盖 `cli/tool_display.py`、`cli/repl.py` 和对应回归测试。
- **Bobodan 设计参考文档**: `docs/DESIGN.md` 作为后续 Web UI / TUI / 官网设计的长期视觉基准，收敛为 Warm Paper Knowledge Garden / Natural Editorial Zen 方向，并明确 ink blue、clay、sage、petal pink 等色彩角色。
- **CLI Tool Display UX (P0)**: 工具调用显示更清晰，specialist 内部 tool events 较多时不刷屏。详见 `docs/NEXT_STEPS_EXECUTION_PLAN.md` P0 节。
  - **B-lite single-active-line UI**: 同一时刻只动画一行 —— thinking line 或 tool spinner 占据光标位置，每 100ms tick 原地切换帧。
  - **工具参数摘要** (`cli/tool_display.py: summarize_tool_args`): `read_file` / `write_file` / `list_dir` / `stat_path` 取路径尾部；`rag_search` / `graph_query` 取 query/concept；`delegate_doc_reader` 取 source_paths 尾 + goal；`delegate_triage` 取 query；`delegate_planner` 取 goal；`change_dir` / `http_request` 走特殊规则；MCP 和其他内置工具走 60 字符 short JSON fallback。
  - **连续同名 tool call 合并** (`CoalescerStack`): 第 1-2 次正常显示，第 3 次触发 `✓ name ×3` inline marker，4+ 静默计数，turn 结束或 name 变化时 flush `✓ name ×N total {elapsed:.1f}s`。错误不计入成功合并组，立即显示 `✗ name: msg`。scope 隔离：主 agent 一套，每个 active specialist 一套。
  - **thinking 动词轮换** (`THINK_VERBS`): `["Thinking", "Checking", "Working", "Drafting", "Polishing"]`，2.5s 等距切换；不用 stage-specific 词（具体动作由 tool active line 表达）。
  - **`core/agent_loop.py`**: `tool_end` event 新增 `elapsed`（必填）和 `result_summary`（可选，仅白名单工具）字段，作为未来 trace 元数据。`_compute_result_summary` 为 `change_dir` 生成 `→ {cwd}`，为 `http_request` 生成 `status {code}`。
  - **`/ui tools on|off` 低噪音模式** (`_b_should_show`): off 时隐藏 tool_start / 成功 tool_end / 成功 coalesce summary / 成功 specialist_event，但**保留所有 ok=False 错误行**（包括 specialist 内部错误）—— errors 是安全网，不进低噪音模式。
  - **删除 specialist running 占位行** (`◐ doc_reader_specialist running...`): B-lite 下 delegate active line 已经表达 running 状态，额外 running 行是噪音；specialist scope 只用 4 空格缩进表达。
  - **`tests/test_repl_display.py`** (新): 42 个 L1（参数化摘要规则）+ L2（7 个 coalesce 状态机 case + flush without pending emits empty）单元测试。
  - **`tests/test_repl.py`** 扩 L3 结构测试：B-lite active line seal on assistant_delta / seal on new tool_start / in-place update / off mode 隐藏成功保留错误；并覆盖 coalesce wall-clock total、delegate parent scope 记账、thinking spinner tick。
  - **Streaming 文本输出修复**: assistant 正文开始后清除 thinking active line，避免 `Thinking` / `Checking` / `Working` 状态行被 seal 到正文中反复刷屏。
  - **Streaming 速度修复**: 移除 `_flush_stream_buffer()` 的逐字符 `sleep`，避免格式化整行输出时阻塞 UI loop，改善流式输出和 thinking spinner 的卡顿感。
  - **Partial preview 节流**: 短 token/chunk 先缓冲，攒到一小段再直接输出，避免当前行被频繁清除重写造成视觉疲劳。
  - **`agents/runner.py`**: specialist 内部 `display_events` 透传 `elapsed` / `result_summary`，避免内部 tool success 显示退化为 `(0.0s)`。
  - 完整测试 683 个通过（1 个既有 MCP coroutine warning）。

- **Learning Agent Orchestrator（多 agent 骨架 v1）**: 主 bobodan 派活给 specialist，不是 peer-to-peer。3 个 built-in specialist（doc_reader / triage / planner），每个配一个 `delegate_*` tool。详见 `docs/archive/agents_design.md`。
  - `agents/base.py`: `BaseSpecialist` ABC（name / system_prompt_template / data_to_content / defaults 契约）。
  - `agents/config.py`: `SpecialistConfig` Python defaults + YAML merge，未知 key 报错。
  - `agents/registry.py`: `SpecialistRegistry` + `last_invocations` deque(maxlen=10)。
  - `agents/runner.py`: `run_specialist()` — fresh session 隔离，工具过滤（hard deny `delegate_*`/`memory_*`），per-specialist timeout（非阻塞返回，provider request timeout cap 到 specialist budget），guarded catch（无自动重试），triage 窄合约校验。content cap 2000 chars，error cap 500 chars，centralized。
  - `agents/specialists/doc_reader.py` / `triage.py` / `planner.py`: 3 个 specialist 实现，documented return contracts。`doc_reader` 明确要求按 `source_paths` 原样调用 `read_file`，禁止缩短为 basename。
  - `agents/prompt.py`: system prompt 模板渲染。
  - `tools/agents.py`: `register_delegate_tools(registry, get_session, get_app_config)` 只为 enabled specialists 注册 `delegate_*` tool（每个独立 schema）；delegate wrapper 将结构化参数转换成 task text，并完整保留 `doc_reader.source_paths`。`delegate_doc_reader` description 明确要求读并总结文件时优先于 `read_file`。
  - `tools/file_ops.py`: `read_file` description 明确 raw-text 定位，并提示 read-and-summarize 任务优先使用 `delegate_doc_reader`。
  - `core/agent_loop.py`: 新增 `tools_schema` 和 `max_iterations` 可选构造参数（specialist runner 用）；支持 UI-only `specialist_event`，用于展示 specialist 内部 tool events，且不写入父 session。
  - `cli/repl.py`: 新增 `/specialists` 命令组（list / status / tools），启动时 `register_builtin_specialists()` + `register_delegate_tools()`。delegate tool 运行时显示 specialist running header 和缩进内部 tool events。
  - `config.yaml`: 新增 `specialists:` section（3 个 specialist 各自 timeout/iter/allowed_tools/allow_mcp）。
  - `tests/test_agents_*.py` + `tests/test_agent_loop.py`: 回归测试覆盖 7 条 runtime invariant、真实 `AgentLoop.run_stream(task)` 调用契约、非阻塞 timeout、disabled specialist 不暴露 delegate tool、triage `(none)` 契约、`doc_reader.source_paths` 路径保真、specialist display events 不污染父 session。
  - `docs/archive/agents_design.md`: 完整设计文档（14 决策 + 13 runtime invariant + 10 章）。

- **Runtime model switch (`/model` command)**: REPL 启动后可切换 active provider 不重启会话。`AgentLoop.set_provider()` + `REPL._make_active_provider()` helper。详见 `feature/model-switch` 分支。


- **MCP (Model Context Protocol) 客户端**: 接入外部 MCP server，把它们暴露的 tools 注入到 agent loop。
  - `mcp_client/event_loop.py`: `AsyncEventLoop` 单例，后台 daemon 线程跑 asyncio event loop，`run_sync(coro, timeout)` 桥接 sync→async。
  - `mcp_client/manager.py`: `MCPManager` 单例，per-server 状态（config/transport/connected/tools/last_error），懒连接，`reload()` diff 配置。
  - `mcp_client/config.py`: YAML 加载 + `${ENV_VAR}` 占位符替换（fail-fast 缺失）。`type` 字段作为 `transport` 的别名，兼容 Claude Desktop 配置格式。
  - `mcp_client/naming.py`: `build_safe_tool_name()` 按 OpenClaw 规则做 sanitization（替换特殊字符为 `-`，server 截断 30 字符，总长 64 字符，冲突加 `-2`/`-3` 后缀）。
  - `mcp_client/catalog.py`: 跨所有 enabled server 拉取 tool specs，连接失败隔离。
  - `mcp_client/tool_wrapper.py`: 把 MCP tool 包装成 Bobodan `ToolResult`，None kwargs 过滤，异常透传。
  - `mcp_client/prompt.py`: `build_mcp_status_prompt()` 生成 system prompt 段。
  - `mcp_client/transport_stdio.py` / `transport_sse.py` / `transport_http.py`: 三个 transport 真实实现，官方 SDK 1.19+ 驱动。stdio 子进程 stderr 走 DEBUG 日志。call_tool 用 `btype` 区分 text/image/resource block。
  - `tools/mcp.py`: `register_mcp_tools(config)` REPL 集成入口，per-server 失败隔离。
  - `core/agent_loop.py`: 新增 `mcp_prompt` 参数，`_inject_mcp_prompt()` 幂等注入 system message。
  - `cli/repl.py`: 新增 `/mcp` 命令组（list/status/restart/tools/reload）。启动面板增加 `mcp: ...` 行。
  - `tests/test_mcp_*.py`: 76 个测试覆盖 config、event loop、manager、naming、catalog、prompt、tool_wrapper、三个 transport、REPL 命令、agent_loop 注入。
  - `docs/MCP.md`: 用户文档（配置、命令、troubleshooting、架构图、限制）。

- **Ollama RAG 嵌入后端**: 接入本地 Ollama embedding 模型，提升 RAG 检索的语义匹配能力。
  - `rag/ollama.py`: `OllamaEmbeddingClient` Ollama embedding API 客户端。三层探测（服务可达→模型能力→真实 embed 请求），结果缓存，超时控制。
  - `rag/dense_store.py`: `DenseVectorStore` dense 向量索引，纯 Python cosine similarity，预存 norm 加速搜索。索引文件包含 model/dim 元数据，支持模型变化检测。
  - `rag/router.py`: `VectorStoreRouter` 路由层。auto 模式探测 Ollama 后自动选择后端，`/kb sync` 双写 dense + sparse 索引，搜索失败自动降级。
  - `config.yaml`: 新增 `rag:` section（`embedding_backend`、`ollama_url`、`ollama_model`、`probe_timeout`、`request_timeout`）。
  - `cli/repl.py`: 启动时探测 embedding 后端并打印状态。`/kb status` 增加 embedding 后端信息。
  - `tests/test_ollama_embedding.py`: 38 个测试覆盖 OllamaEmbeddingClient、DenseVectorStore、VectorStoreRouter、retriever 集成。

- **LLM Wiki 编译层**: 新增 `wiki/` 模块，基于 Karpathy LLM Wiki 模式，将源文档编译为结构化 wiki 页面写入 Obsidian vault。
  - `wiki/schema.py`: `WikiPage`、`CompileResult`、`WikiConfig` 数据模型。页面类型：`wiki_entity`（实体）、`wiki_concept`（概念）。来源追踪通过 `source_registry.json` 而非复制内容。
  - `wiki/compiler.py`: `WikiCompiler` LLM 编译引擎。读源文件 → LLM 提取实体/概念/摘要 → 生成 wiki 页面。支持增量更新（source hash 追踪，只编译变更文件）。
  - `wiki/index.py`: `WikiIndexer` 管理 `index.md`（内容目录）和 `log.md`（操作日志）。
  - `wiki/lint.py`: `WikiLinter` 健康检查——孤立页面、断链、缺失页面、过期页面。
  - `tools/wiki_tools.py`: 注册 `wiki_ingest`（编译源文件）、`wiki_lint`（健康检查）两个 Agent 工具。
  - `cli/repl.py`: 新增 `/wiki init`、`/wiki ingest`、`/wiki lint`、`/wiki status` 命令。
  - `tests/test_wiki.py`: 23 个测试覆盖 schema、index、lint、compiler、REPL 命令。

### 修复
- **Trace per-run 文件碰撞**: `TraceWriter` 文件名增加微秒时间戳和短 run suffix，同一 session 在同一秒内连续 run 不再写入同一个 JSONL；`list_traces()` 兼容旧秒级文件名。
- **Workflow 手动掌握度联动**: `ReviewScheduler.mark_manual(..., "mastered")` 后会触发 `PlanWorkflowTracker.check_plan_completion()`，手动标记已掌握后今日任务和计划状态会同步更新。
- **LearningStore SQLite 文件锁**: `LearningStore._conn()` 改为真正关闭连接的 context manager，避免 Windows 上临时 workspace 或后续 Web runtime 遇到 `bobodan.db` 文件锁。

### 变更
- **Docs cleanup**: 新增 `docs/README.md` 作为文档索引，新增 `docs/DESIGN.md` 作为长期视觉设计参考；将 `docs/OPENAI_AGENT_CODEX_REFERENCE_FOR_BOBODAN.md` 纳入当前工程边界参考；将已实现或历史详细设计移入 `docs/archive/`，当前执行入口收敛到 `docs/NEXT_STEPS_EXECUTION_PLAN.md`。
- **REPL UI 改进**: thinking 动效增加实时计时器（`⠋ thinking · 3.2s`）。工具调用显示改为 Claude Code 风格（`▸ tool_name(args)` → `✓ preview`），消除多余空白行。thinking 动效在工具执行期间保持可见。

## [0.12.0] - 2026-05-20

### 新增
- **记忆系统升级**: 新增 `memory/` 模块，实现"每日记忆 → FTS5 检索 → 晋升机制"记忆生命周期。
  - `memory/store.py`: `MemoryIndexStore` SQLite 索引 + FTS5 全文检索虚拟表。支持 `chunks`（文本块索引）、`recall_log`（召回记录）、`promotion_log`（晋升记录）三张表。FTS5 triggers 自动同步 chunks 表变更。
  - `memory/daily.py`: `DailyMemoryManager` 每日记忆文件管理，存储在 `.bobodan/daily/YYYY-MM-DD.md`。支持 `append`（带时间戳追加）、`read`、`get_today`、`get_yesterday`、`list_recent`、`get_all_dates`。文件带 YAML frontmatter（date, tags）。
  - `memory/search.py`: `MemorySearcher` 混合检索，FTS5 为主、向量为辅。FTS5 无结果时自动降级到现有 `LocalVectorStore`。支持 `search`、`search_daily`、`search_permanent` 三种模式。
  - `memory/promotion.py`: `PromotionEngine` 每日记忆晋升引擎。评分公式：`0.4×frequency + 0.4×quiz + 0.2×recency`（30天半衰期）。晋升阈值：score ≥ 0.6 且 recall_count ≥ 2。`promote()` 将每日记忆写入永久记忆并记录晋升日志。
  - `tools/memory_tools.py`: 新增 `memory_daily_save`（写入每日记忆）、`memory_daily_read`（读取每日记忆）、`memory_promote`（检查并执行晋升）三个 Agent 工具。`memory_recall` 改为 FTS5 优先检索。
  - `core/memory.py`: `save()` 自动索引到 FTS5，`forget()` 自动清理 FTS5。`build_memory_prompt()` 注入今日+昨日每日记忆到 system prompt。`search()` 改为 FTS5 优先、向量降级。`get_stats()` 增加 FTS5 统计。
  - `cli/repl.py`: 新增 `/memory daily [content|YYYY-MM-DD]`（写入/查看每日记忆）、`/memory promote [--dry-run]`（晋升检查）、`/memory review`（今日复习清单，联动 learning 模块）。`/memory stats` 增加 FTS5 统计。
  - `tools/__init__.py`: 导出新增的三个工具。
  - `tests/test_memory_upgrade.py`: 34 个测试覆盖 store、daily、search、promotion、core 集成、REPL 命令、Agent 工具。

### 设计决策
- 每日记忆定位：缓冲 + 学习日志 + 晋升。做题结束后自动写入，用户也可手动写入。
- FTS5 与向量：FTS5 为主（零依赖、支持中文、比稀疏向量更准确），向量为降级兜底。
- 晋升评分：出现次数(0.4) + 做题关联(0.4) + 时间衰减(0.2)。利用学习助手独有的做题数据驱动晋升。
- 晋升调度：启动时轻量检查 + `/memory promote` 手动触发（CLI 工具无常驻进程）。
- 存储格式：Markdown 文件 + SQLite 只做索引，保持人可读、易备份。
- 记忆生命周期：每日缓冲 → 晋升评分 ≥ 0.6 且出现 ≥ 2 → 永久记忆。

## [0.11.0] - 2026-05-19

### 新增
- **学习路线系统**: 新增 `learning/` 模块，实现"学习计划 → 掌握度追踪 → 间隔复习"闭环。
  - `learning/schema.py`: `Mastery`（知识点掌握度）、`LearningPlan`（学习计划）数据模型。
  - `learning/store.py`: `LearningStore` SQLite 存储，新增 `mastery` 和 `learning_plans` 两张表。
  - `learning/scheduler.py`: `ReviewScheduler` 简单间隔重复算法（1/3/7/14天），做对推进、做错重置。支持手动覆盖（`mark_manual`）。
  - `learning/progress.py`: `ProgressTracker` 掌握度概览、薄弱/最强知识点排行、从做题记录自动推断。
  - `learning/path.py`: `LearningPathGenerator` 基于 LLM 的个性化学习计划生成。数据优先级：做题记录 > 用户目标 > 图谱关系 > 课程结构。无 LLM 时回退到基于薄弱点的简单计划。
  - `tools/learning_tools.py`: 注册 `learning_path`、`learning_progress`、`learning_review` 三个 Agent 工具。
  - `cli/repl.py`: 新增 `/learning` 命令集（`plan`/`progress`/`review`/`mark`/`plans`）。
  - `tests/test_learning.py`: 28 个测试覆盖 schema、store、scheduler、progress、path generator、tool 集成。

### 设计决策
- 模块划分：learning/ 管路线+调度+进度，quiz/review 管诊断，职责不重叠。
- 复习策略：先用简单间隔重复，遗忘曲线（Ebbinghaus）放后续计划。
- 进度追踪：混合模式——自动从做题记录推断 + 用户手动覆盖。
- 路线输出：结构化 JSON 存 SQLite，可选写回 Obsidian（待实现）。

## [0.10.0] - 2026-05-19

### 新增
- **知识库状态产品化**: 新增 `knowledge/` 模块，包含 DocumentRecord（按文件追踪导入状态）、manifest（知识库清单）、import_report（同步后导入报告）、library（课程/chunk/图谱聚合统计）。新增 `knowledge_status` Agent 工具。`/kb status` 增强为显示课程分组、图谱节点类型、同步错误。
  - `knowledge/documents.py`: `DocumentRecord` 数据类，`build_document_records()` 从 ScannedNote/SourceDocument 构建记录。
  - `knowledge/manifest.py`: `.knowledge/manifest.json` 读写。
  - `knowledge/import_report.py`: `ImportReport` 数据类，同步后错误和摘要报告。
  - `knowledge/library.py`: `CourseSummary`、`LibrarySummary` 聚合统计。
  - `tools/knowledge_status.py`: Agent 工具，返回知识库概览 JSON。
  - `tests/test_knowledge_status.py`: 13 个测试。

- **题库系统 MVP**: 新增 `quiz/` 模块，实现"生成题目 → 做题 → 批改 → 错题记录 → 薄弱点分析"学习闭环。
  - `quiz/schema.py`: `Question`、`QuizSession`、`QuizAttempt` 数据模型，支持 single_choice / true_false / short_answer 三种题型。
  - `quiz/store.py`: `QuizStore` SQLite CRUD（questions、quiz_sessions、quiz_attempts 三张表），每操作独立连接，WAL 模式。
  - `quiz/generator.py`: `QuestionGenerator` 基于 RAG 检索 + LLM 出题，Prompt 约束 JSON 输出 + 后处理解析。
  - `quiz/evaluator.py`: `QuizEvaluator` 选择/判断题自动批改，简答题 LLM 批改。支持中文答案归一化（对/错、是/否、√/×）。
  - `quiz/review.py`: `QuizReviewer` 错题本和按概念的薄弱点分析。
  - `tools/quiz_tools.py`: 注册 `question_generate`、`quiz_start`、`quiz_submit` 三个 Agent 工具。
  - `tests/test_quiz.py`: 36 个测试覆盖 schema、store、evaluator、generator、review、tool 集成。

- **Session 命名与恢复**: Session 新增 `name` 字段，支持给 session 起名字。
  - `core/session.py`: 新增 `name` 字段、`list_session_summaries()` 方法、旧格式向后兼容（缺 name 字段默认空字符串）。
  - `/session save [name]`: 保存时可选命名。
  - `/session resume`: 交互式选择恢复，显示序号列表。
  - `/session load <id|name>`: 支持按名称模糊匹配、ID 前缀匹配、精确匹配。
  - `/session list`: 显示名称、消息数、最后活跃时间。
  - 加载 session 后自动显示最近对话历史。
  - `tests/test_session.py`: 新增 4 个测试。

- 共新增 49 个测试（知识库 13 + 题库 36）。

### 变更
- **Quiz JSON 解析容错增强**: `quiz/generator.py` 的 `_parse_json_from_llm()` 改用括号深度追踪匹配 JSON 数组边界（替代 `rfind`），先尝试直接解析再做提取，增加尾逗号修复，解析失败时日志输出原始内容便于排查。
- **Quiz 错误信息改善**: `tools/quiz_tools.py` 出题失败时列出可能原因（知识库无资料 / 材料不足 / LLM 格式异常），并提示用 `/kb search` 验证。

### 修复
- **MiniMax 2013 错误**: `providers/minimax.py` 将所有 system message（base、skills、memory）合并为一条发送，MiniMax 只支持单条 system message。同时移除所有消息角色的 `name` 字段。
  - `tests/test_providers.py`: 更新断言，验证 system 消息合并和无 name 字段。

## [0.9.0] - 2026-05-13

### 变更
- **MiniMax Provider 重构**: `MiniMaxProvider` 改为继承 `OpenAICompatibleProvider`，复用通用 HTTP 请求、重试和流式解析逻辑，仅保留 MiniMax 特有的消息转换（`_convert_messages`）和 refusal 检测（`_parse_response`）。
- **工具路径解析收敛**: 将重复的 `_resolve_path()` 提取到 `tools/base.py`，`file_ops`、`dir_ops`、`obsidian_tool` 统一复用。

### 修复
- **RAG 文件读取句柄**: `rag/ingest.py` 的文本和 PDF 读取改为 `with open(...)`，避免文件句柄泄漏。
- **DeepSeek 空测试**: 为 `test_deepseek_provider_complete()` 增加实际 payload 断言，避免空测试误报通过。
- **Provider 导出**: `providers.__all__` 补充 `OpenAICompatibleProvider`。

## [0.8.0] - 2026-05-09

### 新增
- **持久化记忆系统**: Agent 能在会话间记住用户偏好、学习上下文和反馈，跨 session 持久化。
  - `core/memory.py`: `MemoryManager` 核心模块，支持 save/load/forget/search/build_memory_prompt。记忆以单独 Markdown 文件存储在 `.bobodan/memory/`，每个文件带 YAML frontmatter（name, description, type, created, updated）。自动维护 `MEMORY.md` 索引表。
  - `tools/memory_tools.py`: 新增 `memory_save` 和 `memory_recall` 两个 Agent 工具，LLM 可主动保存和检索记忆。
  - `rag/vector_store.py`: `LocalVectorStore` 新增 `upsert()` 增量更新和 `remove_by_source()` 按来源删除方法，支持记忆的增量向量索引。
  - `core/agent_loop.py`: 新增 `memory_prompt` 参数和 `_inject_memory_prompt()` 方法，使用 `MEMORY_MARKER` 防重复注入（与 skills 同模式）。
  - `cli/repl.py`: 新增 `/memory` 命令集（`list`/`show`/`search`/`forget`/`stats`），startup panel 显示 memories 计数。
  - `config.yaml`: 新增 `memory: { enabled: true, dir: ".bobodan" }` 配置节。
  - `graph/schema.py`: 新增 `Memory` 节点标签和 `REMEMBERS` 关系类型。
  - `tests/test_memory.py`: 33 个测试覆盖 frontmatter 解析、文件读写、向量搜索、工具调用、prompt 注入、REPL 命令。

## [0.7.0] - 2026-05-06

### 变更
- **CLI 流式 UI 重写**: 全面重写流式渲染，提升交互流畅度。
  - **打字机效果**: 文本逐字符输出（~12ms/字符），完整行带内联 Markdown 渲染（加粗、代码、列表、表格、引用、标题），部分行实时预览。
  - **Thinking 动画**: `⠋ thinking` 旋转 braille 字符，文字到来时无缝消失（`\r\033[2K` 清除），无内容时自动恢复。
  - **紧凑工具调用**: `⏺ tool_name(args)` 格式替代 Rich 标签，结果预览 `✓/✗` + 80 字符摘要，不打断文本流。
  - **简化用户消息**: `> 用户输入` 前缀替代 Rich Panel，移除 `> assistant` 标题。
  - `cli/markdown_render.py`: 移除 `print_user_message` 和 `print_assistant_header`。
  - `cli/repl.py`: 重写 `_flush_stream_buffer`（typewriter + markdown）、`run_agent_streaming`（thinking/工具/部分行状态机）、thinking 动画方法。
  - `tests/test_repl.py`: 断言从 `"THINK"` 更新为 `"thinking"`。
- **工具调用默认显示**: `show_tool_calls` 默认值改为 `True`。
- **REPL UI 开关命令**: `/ui`、`/ui tools on`、`/ui tools off` 可切换工具调用显示。

### 修复
- **MiniMax 兼容性**: 移除遗留基础 system prompt 注入，避免 MiniMax 请求触发 `invalid chat setting (2013)`。

## [0.6.0] - 2026-04-30

### 新增
- **Rich CLI 渲染**: Agent 回复中的常见 Markdown 会通过 Rich 渲染为更易读的终端格式，不再原样显示 `###` 标题、代码围栏和表格分隔行。`/kb status` 和 `/kb search` 改为 Rich 面板/表格展示，并保留内置轻量 fallback。
- **启动页 Rich 面板**: REPL 启动界面改为 Rich Panel + grid 表格，避免手写框线在中文、长路径或窄终端下错位，并提示输入 `/` 查看命令建议。
- **Slash-command 实时提示**: REPL 接入 `prompt_toolkit`，输入 `/` 时显示可用命令候选；如果终端不支持实时提示，输入 `/` 回车会显示精简命令面板。
- **`/kb` 知识库命令入口**: 新增 REPL 直连命令，不依赖模型猜工具即可同步、检索和查询图谱。
  - `/kb sync <vault> [course_dir] [--full]`: 同步 Obsidian vault 和可选课程资料目录。
  - `/kb status`: 查看 `.knowledge/` 文件数、chunk 数、节点数、关系数和图谱后端。
  - `/kb search <query> [--course name] [--top-k n]`: 直接检索本地 RAG 索引。
  - `/kb graph <concept> [--intent related] [--limit n]`: 直接查询知识图谱关系。
  - `/kb reset --yes`: 删除生成的 `.knowledge/` 索引，不删除原始笔记或资料。
- **RAG + 知识图谱学习助手 MVP**: 新增面向课程学习的本地知识库闭环。
  - `obsidian/`: 扫描 Obsidian vault，解析 Markdown frontmatter、标题、`[[双链]]`、alias、tag、文件 hash。
  - `rag/`: 支持 Markdown/TXT/PDF 文档导入、文本切块、本地轻量 sparse vector 检索、引用结果格式化。
  - `graph/`: 新增知识图谱 schema、本地 JSON 图谱存储，以及可选 Neo4j adapter。未配置 Neo4j 时自动回退到 `.knowledge/graph_store.json`。
  - `tools/obsidian_tool.py`: 新增 `obsidian_sync`，同步 Obsidian 笔记和可选课程资料目录到 `.knowledge/`。
  - `tools/rag_search.py`: 新增 `rag_search`，返回 `results[{text, source, score, metadata}]`。
  - `tools/graph_query.py`: 新增 `graph_query`，支持 `related`、`tags`、`mentions`、`course`、`prerequisites` 等查询意图。
  - `skills/course-learning/SKILL.md`: 新增课程学习助手 skill，引导 Agent 根据问题类型选择 RAG、图谱或组合查询。
  - `docs/RAG_KNOWLEDGE_GRAPH_ASSISTANT.md`: 新增完整设计文档。
  - `docs/RAG_KNOWLEDGE_GRAPH_MVP.md`: 新增 MVP 使用说明、数据流、工具接口和演示步骤。

### 变更
- **README**: 补充课程学习助手 MVP 的用途、项目结构、快速演示和工具说明。
- **CLAUDE.md**: 补充 `obsidian/`、`rag/`、`graph/`、`.knowledge/` 的目录约定和运行数据规则。
- `.gitignore`: 忽略 `.knowledge/` 本地索引目录。
- `requirements.txt`: 新增 `pypdf>=4.0`（PDF 文本抽取）、`prompt_toolkit>=3.0`（slash-command 提示）、`rich>=13.0`（Markdown 渲染）。

### 验证
- 全部 123 个测试通过。

## [0.5.0] - 2026-04-29

### 新增
- **Skills 系统**: 新增 skills 功能，仿照 OpenClaw 的 skills 架构。每个 skill 是 `skills/` 目录下的子文件夹，包含 `SKILL.md`（YAML frontmatter + Markdown 指令）。
  - `core/skills.py`: skill 加载、frontmatter 解析、XML prompt 格式化。
  - `cli/repl.py`: 新增 `/skill` 命令（`list` / `<name>` / `run <name>`）。
  - `core/agent_loop.py`: 支持 `skills_prompt` 参数，首次 LLM 调用前注入 system message。
  - `core/session.py`: `_trim_messages()` 保留首条 system message 不被裁剪。
  - `config.yaml`: 新增 `skills.enabled` 和 `skills.dir` 配置节。
  - `skills/weather/SKILL.md`: 示例天气查询 skill。
  - `tests/test_skills.py`: 18 个单元测试覆盖 frontmatter 解析、skill 加载、prompt 格式化。

### 修复
- **MiniMax tool_call id not found (2013)**: 根因是消息顺序问题——MiniMax 要求 `assistant(tool_calls)` 出现在 `tool` 消息之前。Session 存储顺序为 `tool → assistant(tool_calls)` 但 MiniMax 需要反过来。在 `providers/minimax.py` 中重新排序消息修复。

## [0.4.0] - 2026-04-27

### 新增
- **CLI 流式输出**: OpenAI-compatible 和 MiniMax provider 新增 SSE 流式响应，支持增量解析 tool call delta，并正确累积工具参数。
- **Agent 过程事件**: 新增 `AgentLoop.run_stream()`，输出 assistant delta、工具开始、工具结束和最终回复事件，让 CLI 能展示 agent 正在做什么，而不是静默等待。
- **REPL 工具调用可见**: Agent 运行过程中显示工具名、参数摘要和成功/失败状态。
- **Provider 重试逻辑**: `OpenAICompatibleProvider` 和 `MiniMaxProvider` 的 `complete()` 方法增加指数退避重试。覆盖连接错误、超时、5xx、429。4xx（除 429）不重试，直接抛出清晰错误。
- **CLI 超时控制**: `run_agent()` 增加 per-turn 超时（默认 300s，来自 `agent.timeout` 配置）。超时后打印提示，不写入不完整 session。线程设为 daemon，主进程可干净退出。
- **Provider 配置校验**: `_validate_provider_config()` 校验 provider 类型、`api_key_env` 字段、环境变量是否设置。错误信息包含支持的类型列表和修复建议。
- `requirements.txt` + `requirements-dev.txt`: 核心依赖 `httpx`、`PyYAML`、`python-dotenv`；开发依赖 `pytest`。

### 变更
- **REPL 回复渲染**: 流式阶段改为批量消费事件，并按完整行/长段落阈值增量写入，不再每个 delta 都重绘完整 Markdown 文档，减少长回复时的卡顿。
- **流式 Markdown 清洗**: 流式输出会轻量处理标题、粗体、行内代码、列表和 Markdown 表格，避免用户看到原始 `**`、表格分隔行等格式标记。
- **CLI 主题降噪**: 去掉高饱和橙色/紫色强调色，改用白色、灰色、青色和绿色，让输出更容易扫读。

### 修复
- **CLI 乱码 UI 文案**: prompt 和启动面板中的中文应用名改为英文 `bobodan`，工具状态图标和分隔线改为更适合 Windows 终端的 ASCII 文本。
- **回复和 prompt 重叠**: 流式输出结束后强制补齐换行，避免下一轮输入提示贴在回复末尾。

### 验证
- 全部 80 个测试通过。

## [0.3.0] - 2026-04-27

### 新增
- **`ToolResult` 结构化返回**: 新增 `ToolResult(ok, content, data)` 数据类。所有工具返回 `ToolResult`，程序逻辑用 `ok` 和 `data` 判断状态，给 LLM 的 tool message 仍用 `content` 字符串。
- **Workspace 安全边界**: `tools/base.py` 新增 `_is_within_workspace()` 路径校验，工具只能访问 workspace 根目录内路径。新增 `_is_denied_path()` 拒绝列表，默认拒绝 `.env`、`.git`、`.session`、`__pycache__`、`.venv`。
- **`read_file` 保护**: 增加文件大小限制（1 MB）、二进制文件检测、workspace 边界检查、deny list 检查。
- **`write_file` 覆盖保护**: 新增 `overwrite` 参数，默认 `false`。已有文件需传 `overwrite=true` 才能覆盖。
- `tests/test_file_ops.py`、`tests/test_dir_ops.py`、`tests/test_tool_base.py`: 新增 deny list、binary 检测、大小限制、覆盖保护、workspace 边界等测试。

### 变更
- `tools/base.py`: `execute_tool()` 返回 `ToolResult` 替代 `Any`。自动将非 `ToolResult` 返回值包装为 `ToolResult(ok=True, content=str(result))`。注入 `workspace` 参数。
- `tools/dir_ops.py`: `change_dir` 通过 `data["cwd"]` 返回新路径，`_sync_session_state` 直接读取。
- `core/agent_loop.py`: `_sync_session_state` 使用 `ToolResult.data["cwd"]` 替代中文前缀解析。

## [0.2.0] - 2026-04-27

### 新增
- **`providers/types.py`**: 新增统一内部类型 `ToolCall(id, name, arguments)` 和 `LLMResponse(content, tool_calls)`。所有 provider 返回同一类型，`AgentLoop` 不再依赖 duck typing。
- **`providers/openai_compat.py`**: 新增 `OpenAICompatibleProvider` 基类，封装 OpenAI 兼容 API 的消息转换、HTTP 请求和响应解析。Deepseek 和 OpenAI provider 均继承此类。
- `tests/test_providers.py`、`tests/test_agent_loop.py`: 覆盖类型转换、多 tool call、消息顺序等。

### 变更
- **`providers/deepseek.py`**: 从 LangChain wrapper 改为继承 `OpenAICompatibleProvider`，移除 `langchain_openai` 依赖。同时修复了多 tool call 丢失 bug（原代码只取 `tool_calls_data[0]`）。
- **`providers/minimax.py`**: 返回 `LLMResponse` 替代 ad-hoc `Response` 类。使用共享 `ToolCall` 类型。
- **`providers/factory.py`**: `openai` 分支使用 `OpenAICompatibleProvider` 替代 `DeepseekProvider`，职责清晰。
- **`core/agent_loop.py`**: 直接访问 `LLMResponse.tool_calls` 和 `ToolCall.id/name/arguments`，移除所有 `hasattr` 和 `isinstance(tc, dict)` duck typing。

## [0.1.0] - 2026-04-22

### 新增
- **`.gitignore`**: 排除 `.env`、`.session/`、`.venv/`、`__pycache__/`、`.pytest_cache/` 等运行产物，防止敏感文件和缓存进入版本库。

### 修复
- **Tool call 消息顺序修正**: `core/agent_loop.py` 原代码先执行工具、添加 `tool` 消息，最后才添加 `assistant(tool_calls)`，形成 `user → tool → assistant(tool_calls)` 的错误顺序。现在改为：先解析 tool calls → 添加 `assistant(tool_calls)` → 再执行工具并添加 `tool` 消息。顺序始终为 `user → assistant(tool_calls) → tool`。
- **Session 裁剪保护 tool call 组**: `core/session.py` 重写 `_trim_messages()`，新增 `_group_messages()` 方法。消息按"对话轮次"分组：`assistant(tool_calls)` 和对应 `tool` 消息作为原子单元，裁剪时要么一起保留要么一起移除。
- `tests/test_repl.py`: 更新断言匹配实际 REPL 输出。

### 验证
- 全部 50 个测试通过。
