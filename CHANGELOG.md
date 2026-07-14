# 更新日志

所有重要变更都记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/)，版本号遵循 [语义化版本](https://semver.org/)。

## [未发布]

### 新增
- **P5F 可信联网资料扩展**: 在本地资料不足时提供用户确认优先、来源可选择、证据可复现的普通网页研究流程。
  - 新增 Tavily / Exa SearchProvider 与 `auto` 有序降级；Exa 通过现有 MCP 客户端连接公共 MCP，不向 Web Agent 开放任意 MCP 或 HTTP 工具。
  - 新增直接网页读取、逐跳 SSRF 校验、响应与上下文上限，以及明确标注的 Jina Reader 后备；用户提供的 URL 可直接进入候选流程。
  - 每个资料库使用独立 `research.db` 保存搜索、候选和不可变证据快照；网页不会自动进入 `raw/`、RAG、Wiki 或个人知识库。
  - Chat 增加联网确认、候选来源和证据 artifact；候选默认不勾选，用户选择 1–4 个来源后才读取正文并继续回答。
  - Composer 增加一次性联网入口和 `/web search`；设置中心增加搜索 Provider、真实连接测试和 Jina 后备开关，偏好 schema 升级为 v2。
  - `SourceRef` 增加域名、访问时间、快照 ID 和读取方式；联网回答与基于回答生成的练习共用 `Attribution(kind="web")`。
  - 验证：Python `1095 passed`、Vitest `5 passed`、TypeScript 与生产构建通过、Playwright 多视口 `45 passed`；Exa 真实连接测试通过。

- **P5E.3 Web UI 系统体验与设置中心**: 在进入联网资料扩展前，补齐本地学习产品的用户偏好、模型与通用交互基础。
  - 新增用户级 `preferences.json`，使用 schema、revision 和原子写入保存助手、用户、阅读、Provider、记忆和 Web Skills 偏好；旧浏览器学习资料可一次性迁移。
  - 新增桌面居中 / 移动全屏设置中心，支持中文搜索、键盘选择、URL 深链接、阅读字体与字号、内容宽度、纸纹、会话密度和减少动效。
  - 新增 Provider 状态与最小连接测试；新会话继承默认 Provider，已有会话持久化自己的 Provider，流式回答期间可停止生成但不能切换模型。
  - Chat Composer 增加回答深度、正文流状态条、`@资料 / @会话`、可恢复引用 chip，以及按用户启用状态过滤的 Slash / Skills 菜单。
  - 新增低风险对话式设置确认卡，只允许回答深度、教学方式、反馈强度和记忆开关；Provider、密钥、权限与安全设置不能通过对话修改。
  - 后端断开时按 `2s → 5s → 10s → 30s` 重试并提供手动重连；正常连接状态不常驻，状态页不暴露密钥、绝对路径、Trace 或原始日志。
  - 更新 `docs/PROJECT_GUIDE.md` 与 `docs/DESIGN.md`，固化设置中心、Composer 三层状态、引用、Provider 和动效规则。
  - 验证：Python `1082 passed`、Vitest `4 passed`、TypeScript 与生产构建通过、Playwright 多视口 `42 passed`。

- **P5E.2 Wiki 可靠性增强**: 在不改变用户确认工作流的前提下，为持续更新和批量 Wiki 操作补齐写入保护、失败恢复与维护检查。
  - 新增 Wiki 写入预检，校验目标路径、页面类型、来源范围和结构文件保护；无效模型输出进入 `.bobodan/wiki/staging/`，不会污染正式 Wiki。
  - 页面更新确定性合并 `sources`、`source_refs`、`tags` 与 `related`，保留关键 frontmatter；多来源正文异常缩减时拒绝写入并恢复检查点。
  - 新增按资料库隔离的持久化 Wiki 任务状态，支持进程重启恢复、失败重试、取消和并发锁定；计划卡可显示 staging 失败原因。
  - `index.md` 改为从磁盘页面确定性重建并移除过期条目；正常生成不再自动归档重复页面。
  - 资料归档前新增 Wiki 依赖影响预览，区分单来源归档候选与多来源待更新页面，不执行静默级联删除。
  - 维护页区分程序结构检查和 AI 语义审查；重复页、矛盾、过时内容与知识缺口只形成候选，实际修复仍需先生成计划并由用户确认。
  - 新增 Wiki 任务、语义维护和资料影响 API，并补齐后端、Vitest、生产构建和 Playwright 多视口覆盖。
  - 验证：Python `1077 passed`、Vitest `3 passed`、TypeScript 与生产构建通过、Playwright 多视口 `39 passed`。

- **P5E.1 文件夹资料库与 LLM Wiki 工作流修正**: 将开发工作区知识库升级为可供不同本地用户使用的便携资料库模型。
  - 一个文件夹对应一个资料库；新增 `BOBODAN_LIBRARY.yaml`、`WIKI_SCHEMA.md`、`raw/`、五类 `wiki/` 页面目录及 `.bobodan/` 本地状态目录。
  - 新增用户级资料库注册表与创建、打开、切换、同步、取消注册 API；Chat、RAG、Quiz、Review、学习进度和会话按资料库请求上下文隔离。
  - 首次导入改为用户先选择资料；若尚无资料库，再在同一流程中确认名称和保存位置，创建后自动继续写入 `raw/inbox/` 并建立原文索引。
  - 原始资料对 AI 保持只读；用户删除改为归档到 `.bobodan/archive/raw/`，关联 Wiki 页面标记为 `needs_update`。
  - Wiki 扩展为资料摘要、实体、概念、综合分析、问题与发现五类页面，统一 frontmatter、表格索引、顶部操作日志和健康检查。
  - `/wiki plan`、重点调整、计划确认、执行结果与撤销状态改为会话 artifact 持久化；刷新、切换会话和重启后可恢复。
  - 旧 Wiki 支持“迁移预览 → 用户确认 → 检查点 → 机械升级”，只补 schema 元数据，不移动文件或改写正文。
  - 新增 `python agent.py library init|sync|list`，并通过 `BOBODAN_HOME` 隔离测试注册表。
  - 资料库页面顶部集中显示当前资料库、切换与管理入口；Chat 与资料库空状态共用“导入资料”流程，左下角不再承担新建资料库操作。
  - 资料库管理新增“接入现有资料文件夹”：先预览可索引资料、文件夹体积、现有 Wiki 和旧资料子目录，确认后原地初始化、同步并自动切换，不要求用户重新上传。
  - 便携资料库的额外课程目录改为库内相对路径；重新打开已移动的资料库时会自动修复旧绝对路径，避免资料显示为空。
  - 旧文件夹迁移改为同步成功后再激活；同步或激活失败会恢复迁移前的注册表和活动资料库，不留下半注册状态。
  - 验证：Python `1066 passed`、Vitest `3 passed`、TypeScript 与生产构建通过、Playwright 多视口 `39 passed`。

- **P5E 用户主动触发的 LLM Wiki 完成**: 将资料导入与 AI 整理彻底分离，只有用户明确发起并确认计划后才写入 Wiki。
  - 新增持久化 Wiki 计划，支持当前学习范围、指定资料、课程和已有 Wiki 主题；计划展示新增、更新、合并、冲突和跳过项。
  - Chat 新增 `/wiki plan`、`/wiki update`、`/wiki generate`，Library 新增“整理成 Wiki / 更新 Wiki”入口和可展开页面预览。
  - 生成概念页与实体页，保存结构化 `source_refs`、双向相关概念链接，以及 heading、PDF 页、PPT 页或 chunk 级原文定位。
  - 写入前创建本地检查点，支持显式撤销；写入失败自动恢复，用户手写同名页只标记冲突且不会覆盖。
  - 无指定资料范围时，检索顺序优先用 Wiki 理解概念结构，再以原始资料作为事实证据，并继续在引用中区分 Wiki 与本地资料。
  - 参考 OpenHanako 的资源卡、渐进披露和预览分栏逻辑，保留 Bobodan 暖纸、墨蓝、仓耳今楷与三花猫品牌体系。
  - 验证：Python `1049 passed`、Vitest `3 passed`、生产构建通过、Playwright `30 passed`。

- **P5D 最终可用性收尾**: 补齐 Wiki 维护和 Chat Slash 命令 / Skills 入口。
  - Wiki 分类新增健康检查、孤立页 / 断链 / 过期页统计与详情；“整理并重建索引”只归档 Bobodan 生成的重复页，不删除用户原始资料。
  - Chat 输入 `/` 弹出贴近 composer 的命令面板，支持文本筛选、方向键、Enter / Tab 选择和 Esc 关闭。
  - 提供 `/new`、`/library`、`/wiki`、`/practice`、`/review`、`/kb search`、`/learning today`、`/quiz generate` 等 Web 安全命令。
  - Skills 面板只开放当前 Web runtime 可完整执行的 `course-learning`、`exam-prep`、`study-loop`；显式选择后服务端按本轮临时指令加载对应 `SKILL.md`。
  - 验证：Python `1037 passed`、Vitest `3 passed`、生产构建通过、Playwright `27 passed`。

- **P5D 本地学习闭环 Web MVP 完成**: 在第二轮 Web UI 基础上补齐首次配置、资料范围约束和 Chat → Practice → Review 纵向闭环。
  - 新增四步首次配置，覆盖用户与目标、AI 连接、首批学习资料、记忆与联网边界；已有会话或资料的工作区自动兼容。
  - Library 可维护共享学习范围并选中文字带到 Chat；Chat 与 Practice 请求都会把资料 ID 传到后端，RAG 检索和出题按范围强制过滤。
  - Chat 回答支持渐进式过程摘要，不暴露原始思维链；生成练习会使用本轮返回的精确题目 ID，避免旧题混入。
  - Practice 的“问 AI”改为当前题目内的轻量辅导抽屉，桌面、窄屏和移动端均保持在做题流程内。
  - 验证：Python 全量测试 `1037 passed`，Vitest `3 passed`，生产构建通过，Playwright `27 passed`。

- **P5D Web UI 第二轮完善**: 按 OpenHanako 的字体与工作区交互作为参考，修复第一版的字体覆盖、资料混排、侧栏和会话命名问题。
  - 字体改为五套 token：Luo 仅用于品牌与固定展示标题，系统黑体用于高频 UI，Noto Serif SC Unicode Range 分片用于 AI 回答，仓耳今楷 W04/W05 用于资料与 Wiki 正文，等宽字体用于代码与路径；Noto 字体及 OFL 许可随项目分发。
  - Library 增加“学习资料 / Wiki”分类，隐藏 Wiki 结构文件，按 NFKC 与标点归一化去重；两份旧生成页已归档到 `.bobodan/archive/wiki/<timestamp>/`，规范索引重建为 6 页。
  - 左右栏可独立折叠并保存用户状态；内容不足 720px 时按右栏、左栏顺序自动收起，桌面支持 200ms 边缘悬停预览，移动端继续使用抽屉。
  - 首轮回答后异步生成短会话标题，15 秒超时或模型失败时使用首问本地回退；手动标题不会被覆盖，会话按今天、昨天、本周、更早分组并显示时间。
  - 默认提示收敛装饰 Emoji 与重复小猫自称；欢迎、思考、阅读、写作、等待、休息和回答反馈开始使用现有品牌状态图与表情图。
  - 新增资料分类、Wiki 归档、会话标题和多视口侧栏/字体测试；生产构建、Vitest、Python 聚焦测试和 Playwright 多视口用例通过。
  - 资料与 Wiki 阅读器进一步采用 Kami 同款仓耳今楷 W04/W05 双字重本地字体；AI 回答继续使用 Noto Serif SC，高频 UI 不受影响。

- **P5D Web UI 第一版**: 建立 React 19 + TypeScript + Vite + Tailwind 本地 Web 应用，并按 `docs/DESIGN.md` 落地 Bobodan 暖纸、墨蓝、Luo 字体和三花猫品牌资产。
  - 完成桌面三栏、窄屏上下文抽屉、移动端底部导航，以及 Chat / Library / Practice / Review 四个一级入口。
  - Chat 使用 OpenHanako 式居中起始状态和中央阅读流，普通桌面保持完整侧栏；支持会话恢复、重命名、删除、草稿保存、POST SSE 流式回答、状态摘要、来源标签、失败重试与生成练习入口。
  - Web 后端与 CLI 一致加载工作区 `.env`，修复已配置 Provider 在浏览器中错误返回 `503 provider_unavailable` 的问题。
  - Library 支持真实资料列表、详情阅读和 Markdown / PDF / DOCX / PPTX 导入；Practice 支持出题、未完成练习恢复、答题、批改、小结和放弃；Review 支持真实队列与针对性练习。
  - 本地打包品牌字体与许可证；新增 Vitest API / 组件测试和 Playwright 桌面、移动布局验收。

- **Bobodan 品牌与 Web 视觉参考资产**: 完成三花猫品牌角色规范、正式透明头像、四表情、六学习状态和 Chat 起始插图，并导出前端可直接使用的 PNG / WebP 尺寸。
  - 新增 `docs/assets/brand/BOBODAN_MASCOT.md`，明确品牌角色与用户可配置人设的边界、固定识别特征和后续图片接收规则。
  - 新增 `web/frontend/public/assets/brand/` 前端资源清单，以及 `docs/prototypes/bobodan-study-workspace.html` 静态视觉预览。
  - `docs/DESIGN.md` 补充品牌角色规范；`docs/PROJECT_GUIDE.md` 补充 OpenHanako 的布局、过程披露、设置、记忆、恢复、权限和扩展借鉴边界。

- **P5C Web UI 产品化前置工作完成**: 在不实现 React 页面之前，完成 Web MVP 所需的运行时、API、资料、来源和练习状态基础。
  - 新增共享 `RuntimeService / RuntimeContext`，CLI 与 Web 统一加载 provider、workspace、skills、memory 和 trace；quiz / learning LLM 调用使用同一份 config。
  - Chat API 增加 `run_id`、安全 SSE 事件适配、session list / detail / rename / delete；Web 运行时只开放 RAG、学习、练习和记忆工具白名单。
  - Web 错误统一为 `code / message / details`，流式异常、工具原始输出、secret 和本地绝对路径不再直接返回浏览器。
  - Library 增加托管文件上传、document list / detail 和 source roots；Markdown、PDF、DOCX、PPTX 可进入现有 RAG v2 同步链路。
  - Question 增加 `Attribution + SourceRef` 持久化及旧 SQLite 迁移；Practice 增加 active session、状态恢复、进度、掌握度变化和 abandon；Review 增加聚合队列。
  - 更新 `docs/PROJECT_GUIDE.md` 与 `docs/DESIGN.md`，明确下一阶段为 P5D 本地学习闭环 Web MVP，所有 UI 必须遵循设计 token 与交互边界。
  - 验证：Python 编译检查通过；全量测试 `1020 passed`，2 个既有 warning。

- **Bobodan 当前阶段收尾**: 完成产品定位、文档合并、设计规范补强和 FastAPI skeleton，Web UI 留到下一阶段实现。
  - `docs/PROJECT_GUIDE.md`（新）: 作为后续给人和 AI 看的唯一主入口，整理产品定位、当前阶段、下一步路线、练习系统、功能分层和架构边界。
  - `docs/DESIGN.md`: 补充 Bobodan Web UI 设计硬约束，包括轻纸面质感、Study / Workbench 分区、阅读优先的中等密度、移动端 Chat / Practice / Review 优先、Tailwind / shadcn 语义 token、核心组件规范、来源 chip、Practice 一题一卡、温和状态反馈、用户可配置人设和硬性反模式清单。
  - `web/backend/`（新）: FastAPI skeleton，包含 app/deps/sse 以及 chat、kb、quiz、learning、memory、settings 路由，先完成后端协议边界，不实现 Web UI。
  - `tests/test_web_backend.py`（新）: 覆盖 Web backend health、路由协议、SSE 包装和 service 委托边界。
  - 文档整理：收敛旧架构、旧计划和 archive 文档，更新 `CLAUDE.md`、`README.md`、`docs/README.md`、`docs/MCP.md`、`docs/tools/skills.md`，强调后续 UI / 设计必须先读 `docs/DESIGN.md`。
  - 验证：最近一次全量测试 `998 passed`，2 个既有 warning。

- **RAG v2 — Qdrant + SQLite + Hybrid Retrieval**: 知识库检索升级为完整 RAG 基础设施。
  - `rag/schema.py`（新）: `RetrievalHit`、`DocumentHit`、`RetrievalResult`、`HybridResult` 统一结果 schema。
  - `rag/sqlite_store.py`（新）: `KBSQLiteStore` — SQLite + FTS5 存储层（documents, chunks, chunks_fts, directory_entries, retrieval_runs）。FTS5 content-synced triggers 自动同步。
  - `rag/qdrant_store.py`（新）: `QdrantStore` — Qdrant local persistent 向量存储，支持 upsert/search/delete_by_filter。Point id 使用 UUID5 确定性转换。
  - `rag/embedding_service.py`（新）: `EmbeddingService` — Ollama embedding 包装器，graceful degradation。
  - `rag/source_section.py`（新）: `SourceSection` — 多格式解析统一中间结构。
  - `rag/parsers/`（新）: 多格式解析器 — Markdown heading-aware、PDF page-aware (PyMuPDF)、PPT slide-aware (python-pptx)、Word heading-style (python-docx)。
  - `rag/chunker_v2.py`（新）: heading-aware adaptive chunking — heading_path 继承、长 section 二次切分、短 section 合并、embedding text heading context 注入。
  - `rag/rrf.py`（新）: RRF (Reciprocal Rank Fusion) — vector + FTS5 排名融合。
  - `rag/hybrid.py`（新）: `HybridRetriever` — vector + FTS5 → RRF → chunk candidates。
  - `rag/directory.py`（新）: `DirectoryRetriever` — 文档级路由，metadata lexical + chunk aggregation。
  - `rag/grep_retriever.py`（新）: `GrepRetriever` — rg 优先 + Python fallback，intent-aware evidence thin 判断（exact_lookup vs coverage），扩展阶梯。
  - `rag/orchestrator.py`（新）: `RetrievalOrchestrator` — 三种检索模式调度（hybrid/directory/directory_grep），auto 模式规则路由 + hybrid 空结果 fallback。
  - `rag/query_router.py`（新）: 规则路由（directory_grep > directory > hybrid）。
  - `obsidian/sync.py`: 改用新 parsers + chunker_v2 + SQLite + Qdrant 写入，incremental sync 保留 manifest。
  - `service/kb_service.py`: `search()` 新增 `mode` 参数（auto|hybrid|directory|directory_grep）。
  - `tools/rag_search.py`: tool schema 新增 `mode` 参数。
  - `rag/retriever.py`: 优先走 Orchestrator，legacy JSON index fallback。
  - `rag/citations.py`: 支持 heading、page/slide、retriever 信息。
  - `config.yaml`: 扩展 `rag:` section（vector_db, chunking, retrieval 配置）。
  - `requirements.txt`: 新增 `qdrant-client`、`python-docx`、`python-pptx`、`pymupdf`。
  - 112 个新测试覆盖 SQLite store、Qdrant store、parsers、chunker v2、RRF、hybrid/directory/grep retriever、orchestrator、query router。994 测试全通过。

- **Bobodan base system prompt**: `core/agent_loop.py` 新增稳定的 Bobodan 基础 system prompt，用 marker 幂等注入。
  - 定位从通用 CLI assistant 收敛为 "local-first personal assistant with strong learning capabilities"。
  - 学习能力仍是核心强项，但允许普通聊天、陪伴、头脑风暴、轻娱乐和日常问题。
  - 人设和语气继续由 memory / persona 偏好提供，base prompt 只固定产品主线和事实边界。
  - 保留 `LEGACY_BASE_SYSTEM_PROMPT` 清理逻辑，旧 session 会移除旧提示词并注入新提示词。
  - `tests/test_agent_loop.py`: 覆盖 base prompt 注入、幂等、防重复和 legacy prompt 清理。

- **内置 skills 调整**: 删除与学习助手主线无关的 `weather` 示例 skill，新增并收敛 Bobodan 学习场景内置 skill。
  - `skills/study-loop/SKILL.md`: 学习闭环引导，负责知识库检查、学习计划、今日任务、练习、进度和导出。
  - `skills/exam-prep/SKILL.md`: 考前冲刺和薄弱点训练，基于 `learning_progress` / `learning_review` / `quiz_start` / `question_generate`，不再引用不存在的 `quiz_weak` / `quiz_wrong` / `quiz_stats` 工具。
  - `skills/obsidian-workspace/SKILL.md`: Obsidian / 本地知识库工作区管理，负责同步资料、知识库状态、导出学习计划/做题总结和 wiki 整理。
  - 当前内置 skill 集合：`aihot` / `course-learning` / `study-loop` / `exam-prep` / `obsidian-workspace`。

- **P5 Service 层抽取**: 5 个 service 模块提取完成，CLI 和 tools 统一委托 service 层，为 FastAPI/Web 前后端分离做准备。
  - `service/learning_service.py`（新）: `LearningService` — 学习计划、进度、复习、掌握度（9 个方法）。
  - `service/quiz_service.py`（新）: `QuizService` — 出题、做题、批改、错题本、薄弱点（6 个方法）。
  - `service/memory_service.py`（新）: `MemoryService` — 永久记忆、每日记忆、晋升（9 个方法）。
  - `service/kb_service.py`（新）: `KBService` — 知识库同步、状态、RAG 检索、图谱查询、重置（5 个方法）。`sync()` 内置 workspace 路径安全边界。
  - `service/agent_service.py`（新）: `AgentService` — provider 创建/列表、session 持久化、agent 事件流（6 个方法）。`create_provider` 返回 LLMProvider 实例，`list_providers` 包含 `configured` 状态但不暴露 API key。
  - 所有 service 方法返回 `{"ok": bool, ...}` dict，无 ANSI/HTML 格式。
  - `cli/repl.py`: `/learning`、`/quiz`、`/memory`、`/kb`、`/model`、`/session` 命令全部委托对应 service。删除 `normalize_session_id`、`get_session_path`、`resolve_session_id` 等已迁移方法。
  - `tools/learning_tools.py`、`tools/quiz_tools.py`、`tools/memory_tools.py`、`tools/rag_search.py`、`tools/graph_query.py`、`tools/knowledge_status.py`、`tools/obsidian_tool.py`: 全部委托对应 service，保留 ToolResult 包装。
  - `tests/test_learning_service.py`（新，27）、`tests/test_quiz_service.py`（新，16）、`tests/test_memory_service.py`（新，21）、`tests/test_kb_service.py`（新，17）、`tests/test_agent_service.py`（新，19）: 共 100 个新测试。
  - 869 测试全通过。

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
- **Review 状态字体与滚动条**: `到期 / 错题 / 薄弱点` 使用 Luo 短标签强调；全局滚动条改为透明轨道与暖灰细滑块，并修复右侧资料名称撑宽面板造成的横向滚动条。
- **复习出题错误继承当前资料范围**: Review 现在按知识点关联并复用历史题目 ID，不再把用户当前选择的无关资料范围套到历史复习项上；只有没有历史题时才回退到重新生成，避免无资料报错和检索跑偏。
- **Trace per-run 文件碰撞**: `TraceWriter` 文件名增加微秒时间戳和短 run suffix，同一 session 在同一秒内连续 run 不再写入同一个 JSONL；`list_traces()` 兼容旧秒级文件名。
- **Workflow 手动掌握度联动**: `ReviewScheduler.mark_manual(..., "mastered")` 后会触发 `PlanWorkflowTracker.check_plan_completion()`，手动标记已掌握后今日任务和计划状态会同步更新。
- **LearningStore SQLite 文件锁**: `LearningStore._conn()` 改为真正关闭连接的 context manager，避免 Windows 上临时 workspace 或后续 Web runtime 遇到 `bobodan.db` 文件锁。

### 变更
- **后续路线调整**: 下一阶段改为 P5E“用户主动触发的 LLM Wiki”。资料导入只建立原文索引，用户要求整理后先生成变更计划，确认后才写入可互链、可回到原文、可撤销的 Wiki；可信联网顺延到 P5F，发布收尾顺延到 P5G。
- **侧栏品牌头像**: 左上角恢复使用正式主头像 `bobodan-avatar-64.png`，不再把低频 `friendly` 表情图作为固定品牌入口。
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
