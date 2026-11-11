> **归档（2026-11-11，GOV-01）**：`docs/PROJECT_GUIDE.md` 原 §4「历史阶段记录与发布验收要求」的完整原文（P5C–P5G 阶段决策、实现边界、当时的验收数字）。仍然有效的**发布验收要求**已提到 `PROJECT_GUIDE.md` §4，本文件只用于追溯。文中的测试数量、分支名、「完成 / 推迟」都是当时的状态。相对链接已按新位置改写。

## 4. 历史阶段记录与发布验收要求

> 历史阶段记录说明：本章的 P5C-P5G 保留已完成阶段的产品决策、实现边界和验收证据，便于理解现有架构；它们不构成当前排期，也不应从中恢复已被取代的方案。当前工作批次、优先级和完成状态只以 [`ROADMAP.md`](../ROADMAP.md) 为准。

### 4.1 目标架构

```text
React Web UI
  ↓ HTTP / streamed response
FastAPI Web DTO & Event Adapter
  ↓
Runtime Composition + Service Layer
  ↓
Agent / RAG / Quiz / Learning / Memory
  ↓
.session / .knowledge / .bobodan / Obsidian
```

关键边界：

- React 只调用 FastAPI，不直接理解 Python domain 数据结构。
- FastAPI 负责 HTTP、DTO、状态码和事件转换，不承载学习业务。
- Service 层负责可复用业务和跨域聚合。
- Runtime Composition 负责 provider、skills、memory、tool catalog、trace，以及按能力开关装配 MCP / specialist。
- CLI 与 Web 最终共用同一套 runtime 装配规则，避免行为长期分叉。

### 4.2 技术选择

- 前端：React + TypeScript + Vite。
- UI：Tailwind CSS 与现有本地组件样式，所有颜色、字体、间距和动效必须映射 `docs/DESIGN.md` tokens；不为获得组件而引入整套 UI 主题。
- 路由：React Router。
- 数据请求：第一版使用原生 `fetch`；POST 流式回答使用 `ReadableStream` 解析 SSE frame，不使用原生 `EventSource`。
- 状态：服务端数据留在 API / domain；前端使用局部 React state 与已有的小型 Zustand UI store，禁止把学习业务真相复制到全局 store。
- 开发模式：Vite dev server + FastAPI，Vite proxy `/api`。
- 发布模式：Vite production build 由 FastAPI 托管静态文件，一个本地进程启动。
- 运行边界：默认只绑定 `127.0.0.1`，按单用户本地应用设计，本阶段不做登录和多租户。
- 保留现有 SQLite、Qdrant 以及必要的配置 / 元数据 JSON；RAG、概念图谱和个人知识使用各自 SQLite truth source。旧 Markdown / JSON 用户数据只保留只读迁移边界，不为兼容继续维护第二套 runtime。

### P5C：产品化基础

**状态：已完成（2026-07-10）。** Web 已能通过稳定、安全、可恢复的产品合约调用真正的 Bobodan；本阶段没有实现 React 页面。

#### P5C.1 统一运行时装配

范围：

- 抽取 CLI 与 Web 可复用的 runtime composition，统一加载 config、provider、skills prompt、memory prompt 和 trace。
- Web MVP 默认启用内置学习工具、skills、memory 和 trace。
- MCP 与 specialist 在 Web MVP 默认关闭；启用前先把 delegate tool 从“闭包捕获 CLI session”改为请求级 ToolContext。
- memory 写入或删除后，下一次 run 必须使用刷新后的 memory prompt。
- 所有 LLM 相关 service 使用同一份 config / provider 解析规则，不再隐式读取另一个默认配置。

验收：

- 同一个问题在 CLI 和 Web 使用相同 provider、workspace、skills 和 memory 配置。
- Web run 能调用 RAG / quiz / learning 工具，并产生 trace。
- 两个并行 session 不共享 cwd、session 或用户上下文。

#### P5C.2 稳定 Web DTO 与事件协议

范围：

- 为 chat、session、quiz、review、library 定义 Pydantic request / response schema。
- Web 层把 AgentLoop 事件转换为稳定事件：`run_started`、`message_delta`、`status`、`citation`、`run_completed`、`run_failed`。
- 每次 run 生成 `run_id`，Web 事件不直接暴露原始 tool output、secret、内部路径或 specialist 日志。
- RAG 等工具通过白名单 artifact 输出结构化公开数据；Web 不解析 `ToolResult.content` 获取引用。
- 统一错误结构：`code`、`message`、可选 `details`，按 not found / invalid / conflict / unavailable 使用正确 HTTP 状态码。
- 增加 session list / detail / rename / delete API。

浏览器流方案：

```text
POST /api/chat/runs
→ fetch()
→ response.body.getReader()
→ 逐帧解析 SSE
```

第一版不做断线后继续同一 run；断线后提供“重新发送本轮”操作。只有确实需要 run 重连时，再升级为 POST 创建 run + GET events。

验收：

- API contract tests 覆盖正常、空数据、非法参数、provider 不可用和 stream error。
- 前端不需要解析 tool 文本来判断来源、状态或下一步动作。
- 保存后的 chat session 能通过 API 完整恢复为用户 / AI 消息视图。

#### P5C.3 资料、来源与练习数据合约

定义统一归因对象：

```text
Attribution
  kind: local | local_extension | web | ai | unverified
  sources: SourceRef[]

SourceRef
  source_type: local | web
  source_id
  title
  url                 # 仅网页来源
  document_id / chunk_id
  heading / page / slide
```

`AI 补充` 与 `待核实` 可以没有 `SourceRef`；本地绝对路径只保留在服务端，不直接发送给前端。

范围：

- 增加面向普通用户的资料导入 API，第一版支持 Markdown、PDF、DOCX、PPTX；上传文件复制到应用管理的本地 source 目录后再进入现有 sync 流程。
- 增加 document list / detail / sync status API，Library 不直接遍历服务器文件系统。
- 保留“高级本地路径同步”给已有 vault 用户，但路径必须位于明确配置的 allowed roots 内。
- Chat citation、Question、Practice summary 共用同一套 `Attribution + SourceRef` 语义。
- Question 从单个 `source` 字符串迁移为可保存多个来源的结构；迁移必须兼容已有 SQLite 数据。
- 出题时由系统确定性保留 RAG chunk 来源，不依赖 LLM 自己编造 source 字段。
- 增加 practice session detail / attempts / abandon / summary API。
- submit answer 返回题目概念、来源、批改、解释、session 进度和掌握度变化。
- Review service 聚合到期概念、错题和薄弱点，前端只负责展示和操作。

验收：

- 用户不进入 CLI 就能导入一份受支持资料，并在 Library 看见同步结果。
- 任意一道生成题都能解释“基于哪份资料生成”。
- 刷新后可从后端恢复练习进度，不依赖浏览器保存完整答案副本。
- 一次答错后，Practice 返回掌握度变化，Review API 能看到对应复习项。

### P5D：本地学习闭环 Web MVP

**状态：已完成（2026-07-11）。** React 工程、混合字体系统、响应式双侧栏、四步首次配置、Chat / Library / Practice / Review 真实 API 交互、资料范围约束和完整学习闭环均已通过验收。

第二轮已完成：

- Luo 不再覆盖全站；高频 UI、阅读正文、品牌与代码分别使用独立字体 token。
- Library 将用户学习资料和 Bobodan 生成的 Wiki 分开显示；结构文件隐藏，重复生成页只归档不删除原资料。
- 左右栏独立折叠、持久化、按 720px 主内容宽度自动收起，并支持桌面边缘悬停预览。
- 首轮回答完成后异步生成会话标题，失败时本地回退，手动标题受保护。
- 六学习状态图和四表情开始进入真实页面状态，不再使用突兀的右下角大图或装饰 Emoji。
- Library / Wiki 正文使用 Kami 同款仓耳今楷 W04/W05，AI 回答继续使用 Noto Serif SC，高频 UI 保持系统黑体。
- 资料选文可直接带入 Chat；当前学习范围会同时约束 Chat 检索和 Practice 出题，不只作为前端标签展示。
- Practice 的“问 AI”在当前题目内打开轻量抽屉，桌面、窄屏与移动端均不会跳出练习流程。
- Wiki 分类增加健康检查、断链 / 孤立页 / 过期页详情，以及只归档生成重复页的规范索引重建。
- Chat composer 输入 `/` 可选择 Web 安全命令与 `course-learning / exam-prep / study-loop` 三个学习 Skills（P5D 当时 3 个；2026-10 起为 4 个，含 `socratic-persona`，见 `web/backend/capabilities.py:3-9`）；CLI 管理能力继续隐藏。

#### P5D.1 前端地基

- 建立 `web/frontend`、路由、Vite proxy 和 API client。
- 落地 `DESIGN.md` tokens、字体和核心组件。
- 建立响应式三栏骨架：左侧会话 / 学习空间，中间 Chat 主画布，右侧可折叠学习上下文；移动端使用抽屉，不压缩主对话列。
- Today 作为 Chat 无活动会话时的起始状态，不单独搭第二套首页。
- Today 使用 Bobodan 正式头像或学习场景图，显示当前学习空间与记忆状态；只提供“开始提问、导入资料、开始练习”等真实可执行动作。
- 增加四步首次配置：用户与目标、AI 连接、首个学习空间、记忆与联网边界；模型职责默认自动配置。
- 第一批真实入口只开放 Chat、Practice、Review、Library；没有数据的入口显示“导入资料 / 开始对话”等可执行空状态，不放假按钮（历史：当时 4 项；当前 6 项，见 §2.3；校验：2026-10-28，web/frontend/src/components/shell/nav.ts:5-10）。

#### P5D.2 最小 Library 与资料导入

- 上传 Markdown、PDF、DOCX、PPTX，显示导入和索引状态。
- 展示文档列表、基础元数据和可读错误，不先做全文编辑、highlight 或大图谱。
- 选择一份或一组资料作为 Chat / Practice 的学习范围。
- 当前资料范围同步显示在右侧上下文面板；面板首版只做资料列表和来源详情，不实现完整文件管理器。

#### P5D.3 Chat 纵向切片

- 会话列表、主对话区、composer、流式回答、状态反馈、来源 chip。
- 新建、恢复、重命名、删除会话。
- Composer 支持附件、当前资料范围和引用选中文字；解释、总结、出题等学习动作复用同一个输入与发送流程。
- 右侧上下文根据当前回答展示来源、相关知识点和“生成练习”入口，无上下文时自动收起或显示轻量空状态。
- 思考与工具过程使用渐进披露：默认一句学习过程摘要，展开后显示资料、工具、耗时和失败恢复，不展示原始思维链。
- 输入草稿按首页 / 会话持久化；切换页面不丢失当前运行状态，刷新或断线后恢复已完成内容并提供“重新发送本轮”，同一 run 断点续传留到后续按需升级。
- 工具过程默认折叠，只展示用户能理解的状态。
- 失败可重试，刷新后恢复最近已完成会话。

#### P5D.4 Practice 纵向切片

- 从主题、资料或 Chat 回答创建练习，默认 5 题。
- 单选、判断、简答混合，一题一卡。
- 提交、批改、解释、来源、进度、结束小结。
- 继续 / 放弃未完成练习，后端 SQLite 为真相源。

#### P5D.5 Chat → Practice → Review 闭环

- Chat 回答可带上下文创建练习。
- Practice 内有只围绕当前题目的轻量“问 AI”。
- 答题自动更新错题、掌握度和复习计划。
- Review 展示今日到期概念、错题和薄弱点，并能继续生成针对性练习。

P5D 验收结果：通过。

- 新用户能完成“导入资料 → 提问 → 查看来源 → 生成 5 题 → 做题 → 查看批改 → 进入复习”。
- 关键流程全部使用真实后端数据，无 mock 业务数据。
- Chat → Practice → Review 至少有一条 Playwright 端到端测试。
- 刷新和会话切换后，输入草稿、已完成回答和当前学习范围可恢复；短暂断线有明确的重试动作。
- 验证结果：Python `1037 passed`、Vitest `3 passed`、生产构建通过、Playwright `27 passed`。

### P5E：用户主动触发的 LLM Wiki

目标不是在资料导入时自动生成 Wiki，而是在用户明确要求后，将指定资料整理为人和大模型都能阅读、跳转和检索的知识结构。

默认流程：

```text
导入资料
→ 只解析、切分并建立原文检索索引
→ 用户说“把这些资料整理成 Wiki”
→ AI 生成整理计划，不立即写文件
→ 展示预计新增、更新、合并和冲突页面
→ 用户确认
→ 写入 Wiki、建立互链与原文引用
→ 重新建立 Wiki 检索索引
→ 用户审查结果并可撤销
```

必须实现：

1. 用户主动触发：上传资料本身不得自动创建 Wiki 页面。
2. 范围发现：默认通过全库检索发现相关或未覆盖资料；用户选择项作为优先种子，只有明确启用严格模式时才限制为指定资料。
3. 计划优先：`/wiki plan` 只输出新增、更新、合并、冲突和跳过计划，不写文件。
4. 确认写入：聊天侧命令只有 `/wiki plan`（出计划）与 `/wiki update`（增量计划），用户确认计划后才执行；`generate` 只是 `wiki/workflow.py` 的内部 action，不是命令（校验：2026-10-28，web/frontend/src/lib/commandRouter.ts:21-26、wiki/workflow.py:241-243）。
5. 页面结构：生成概念页与实体页，保留摘要、相关概念、来源、更新时间和 AI 整理标记。
6. 内部跳转：支持 Wiki 页面之间的双向链接和相关概念导航。
7. 原文定位：每个重要结论可跳回资料标题、heading、PDF 页码、PPT 页或 RAG chunk。
8. 双层检索：大模型先用 Wiki 理解概念与关系，再回到原始资料核实事实与引用。
9. 增量更新：资料变化后只更新受影响页面，显示新增、修改、冲突和过期内容。
10. 可恢复：写入前创建检查点，支持撤销本轮 Wiki 整理。

维护动作必须区分：

- `生成 Wiki`：从资料创建新页面。
- `更新 Wiki`：根据变化资料更新已有页面。
- `维护 Wiki`：检查重复、断链、孤立页、冲突和过期内容。

P5E 验收：

- 导入资料后不会自动生成 Wiki。
- 用户能从 Chat 或 Wiki 页面发起计划，并在确认前看到完整变更摘要。
- 生成页面能互相跳转，也能跳回原始资料位置。
- Chat 能区分 Wiki 摘要与原始资料证据，不把 AI 整理内容伪装成原文。
- 至少有一条“资料 → Wiki 计划 → 确认生成 → 页面互链 → 原文定位”的 Playwright 测试。

P5E 验收结果：通过。

- 导入资料继续只建立原文索引，不会自动创建 Wiki。
- Chat 支持 `/wiki plan`、`/wiki update`（`generate` 是内部 action，不是聊天命令）；Library 支持从学习资料或已有 Wiki 页面发起（校验：2026-10-28，web/frontend/src/lib/commandRouter.ts:21-26、web/backend/routers/chat.py:1222）。
- 计划卡在确认前展示完整变更计数与页面预览，冲突用户页面不会被覆盖。
- 生成页保存结构化 `source_refs`，相关概念与原始资料均可在 Web 阅读器内跳转定位。
- 写入前检查点、显式撤销和失败自动恢复均有测试覆盖。
- Playwright 已覆盖“资料 → Wiki 计划 → 确认生成 → 页面预览 → 原文定位”，并通过桌面、窄屏和移动端验证。
- 验证结果：Python `1049 passed`、Vitest `3 passed`、生产构建通过、Playwright `30 passed`。

### P5E.1：文件夹资料库与持久化 LLM Wiki 工作流

正式产品不再把项目内 `note/vault` 当作用户默认资料。它只保留为开发和自动化测试数据。一个真实资料库就是一个可移动、可备份、可由 Obsidian 打开的本地文件夹：

```text
<library-root>/
├── BOBODAN_LIBRARY.yaml
├── WIKI_SCHEMA.md
├── raw/
│   ├── inbox/ assets/ articles/ papers/ books/ misc/
├── wiki/
│   ├── index.md log.md templates/
│   ├── sources/ entities/ concepts/ analyses/ questions/
└── .bobodan/
    ├── manifest.json knowledge.db checkpoints/ archive/
```

核心规则：

1. `BOBODAN_LIBRARY.yaml` 保存 schema version、稳定 UUID、名称和创建时间，不保存密钥。
2. `~/.bobodan/libraries.json` 只注册资料库 ID、名称、路径和最近打开时间；测试必须设置 `BOBODAN_HOME` 隔离。
3. 用户可以创建和切换多个资料库，但同时只有一个活动资料库。资料、会话、RAG、题库、练习、复习和学习进度不得串库。
4. 用户界面的主动作始终是“导入资料”。第一次导入先选择文件；若尚无资料库，再在同一流程中确认资料库名称和父目录，创建结构后自动继续写入 `raw/inbox/` 并初始化原文索引。继续导入只更新当前资料库。
5. 上传、初始化和同步永远不自动生成 Wiki。文件系统中手动放入资料后，使用 `python agent.py library sync <path>` 建立或更新索引。
6. AI 对 `raw/` 只有读取权限。用户在 UI 删除原文时，文件进入 `.bobodan/archive/raw/<timestamp>/`，引用它的 Wiki 标记为 `needs_update`。
7. `WIKI_SCHEMA.md` 是人和所有模型共同读取的规则真相源。AI 只能提出规则变更计划，确认后才能更新。

资料库切换、新建空资料库、打开 Bobodan 资料库和旧文件夹接入统一放在资料库页面顶部的“资料库管理”，不使用左下角按钮承担主要建库操作。旧资料文件夹优先通过 Web 的“资料库管理 → 接入旧文件夹”处理。系统先只读扫描资料数量、文件夹体积、现有 Wiki 与旧资料子目录；用户确认后才增加资料库描述文件、注册只读来源并重建索引。原文件、图片、源码和 Wiki 保持原位，不要求重新上传。CLI 保留为批处理与故障恢复入口。

命令行：

```text
python agent.py library init <path> [--name <name>]
python agent.py library sync [path]
python agent.py library list
```

Wiki 页面统一为五类：

| 类型 | 目录 | 用途 |
|---|---|---|
| `wiki_source` | `wiki/sources/` | 一份原始资料的可追溯摘要，计划中必须至少有一页 |
| `wiki_entity` | `wiki/entities/` | 人物、组织、系统、算法等实体 |
| `wiki_concept` | `wiki/concepts/` | 定义、原理、方法和知识点 |
| `wiki_analysis` | `wiki/analyses/` | 确有价值的跨资料综合分析 |
| `wiki_question` | `wiki/questions/` | 未解决问题、矛盾与新发现 |

每页 frontmatter 必须包含 `type`、`title`、`summary`、`schema_version`、`generated_by`、`created`、`updated`、`sources`、`source_refs`、`status`、`indexable`。`index.md` 按五类使用“页面 / 摘要 / 来源数 / 更新时间”表格，`log.md` 最新操作写在顶部。模板、索引、日志和内部状态不进入普通检索。

对话工作流固定为：

```text
用户发送 /wiki plan 或 /wiki update
→ 命令立即显示并保存为用户消息
→ AI 阅读资料并给出 wiki_focus 重点卡
→ 用户确认或用自然语言调整重点
→ 生成并保存 wiki_plan 计划卡
→ 用户确认写入
→ 保存 wiki_result、检查点与撤销状态
```

命令、重点讨论、计划、执行结果和撤销状态均属于 Chat session artifact，刷新、切换会话和重启后必须恢复。Library 的“整理成 Wiki / 更新 Wiki”只携带范围进入 Chat，不在资料页直接写入。

旧 Wiki 升级固定为“迁移预览 → 用户确认 → 检查点 → 机械升级”。升级只补齐 frontmatter 与 schema version，不移动原文，不调用 LLM 改写正文。健康检查覆盖孤立页、断链、缺失页、索引不同步、过期页和矛盾候选；任何修复都先生成计划，确认前不得修改文件。

P5E.1 主体流程与可靠性收尾已经完成：`source_roots` 使用资料库内相对路径，并能在重新打开已移动资料库时修复旧绝对路径；旧文件夹迁移在同步成功后才激活，失败会恢复迁移前的注册表和活动资料库。P5E.2 已在此基础上完成 Wiki 写入可靠性增强。

#### 桌面端资料进库设计（2026-08-12 历史规划）

> 本节保留当时的产品设计和架构约束。其尚未交付的内容必须先映射到 [`ROADMAP.md`](../ROADMAP.md) 的当前批次后再实施，不能把“等待实现”直接当作当前排期。

> 决策来源：针对"安装桌面端后直接往文件夹放资料，agent 识别并初始化"的逐项追问；借鉴 OpenHanako（`~/.hanako` 点目录 + `~/Desktop/OH-WorkSpace` 工作区 + chokidar 增量监听）。本小节是 P5E.1 的增量规格，冲突处以本文为准。

1. **应用数据位置：`~/.bobodan` 点目录**（Windows 即 `C:\Users\<名>\.bobodan`）。撤销 P5G.1 的 `%APPDATA%\Bobodan` 切换；`BOBODAN_HOME` 环境变量仍可覆盖。与 Codex（`.codex`）、OpenHanako（`.hanako`）同风格，用户在用户目录一眼可见。
2. **资料库与应用数据分离**。原文资料库文件夹由用户自选（可放 D 盘 / OneDrive），`.bobodan` 只放小体积应用数据（个人知识库、资料库注册表、用量账本）。产品提供"打开数据目录"入口，不让用户在文件管理器里猜位置。
3. **默认资料库文件夹**：首次启动自动创建 `Documents\Bobodan 资料库`，可一键换成任意位置。该文件夹对用户就是"往里丢文件"的文件夹——**根目录与任意子目录全格式扫描**（修复当前 PDF/DOCX 丢根目录不被索引的盲区），内部结构（`raw/`、`wiki/`、`.bobodan/`）对用户隐藏。
4. **新增文件检测**：桌面端实时轻量监听当前资料库文件夹（只"看"不"索引"，参考 OpenHanako chokidar：忽略点目录 / `.git`、等待写入完成、防抖）。小文件（<5MB 且落盘 >5 秒）自动索引；大文件 / 批量检测后走 agent 确认。
5. **agent 对话式确认**：检测到新资料后，无论用户当前在哪个页面，agent 主动提议（"我在资料库发现 3 份新文件，要整理进知识库吗？"）→ 全局确认卡 → agent 执行并汇报结果。复用并扩展现有 Chat 确认卡机制（依赖 AG-0 事件总线 / 通知机制，排期为 AG-0 之后）。
6. **增删改待遇**：修改自动增量重建索引（内容变了索引跟着变，不打扰）；删除必须确认（级联失效概念证据、错题引用，确认时说明影响范围）；重命名提示一次后重建（文档身份变化，旧证据标记 stale）。
7. **初始化范围**：索引免费自动（解析 → 切片 → SQLite，本地计算）；概念提取按需提议（LLM 花费，agent 完成后单独提议，用户确认才执行）。保持 P5E.6"本地立即可用，AI 渐进补充"。
8. **阅读体验**：切片优先在句子 / 段落边界断开（超长段落不再字符硬切腰斩句子）；阅读器把同一文档相邻切片视觉无痕衔接。**原文视图已交付（2026-09-23）**，不再"留作远期"：阅读器现在有「原文 | 按小节」两种视图——Markdown / TXT 页内渲染原件（frontmatter 折叠、图片走受限附件端点），PDF 交给浏览器内置阅读器，DOCX / PPTX 保持分段并给「用系统打开」；视图偏好全局记忆，从引用或搜索结果带 chunk 进入时切到分段并高亮。详见 [`ROADMAP.md`](../ROADMAP.md) 的「原文查看 + 资料联动」交付记录。
9. **实现顺序**：① 撤销 %APPDATA% 切换（恢复 `~/.bobodan`）→ ② 根目录全格式扫描 → ③ 默认资料库创建 → ④ 切片句子边界软切 + 阅读器衔接 → ⑤ 文件监听 + agent 确认卡（依赖 AG-0，桌面端常驻后生效）。

### P5E.2：Wiki 可靠性增强（完成）

目标是在不改变用户确认工作流的前提下，让 Wiki 能安全处理持续更新、批量任务和更大规模资料：

1. `index.md`、`log.md`、来源映射和反向链接由程序确定性维护，模型不得直接生成或整体重写结构文件。
2. 写入前校验 Schema、路径、页面类型、frontmatter 和来源是否存在；无效内容进入 `.bobodan/wiki/staging/`。普通用户界面称为“待修正草稿”，显示具体页面与可读原因，不直接暴露内部路径。
3. 页面更新确定性合并来源、标签与关系，锁定 `type`、`title`、`created` 等元数据；正文异常缩减时拒绝写入并恢复检查点。
4. Wiki 计划、生成、批量解析和后续联网研究使用按资料库隔离的持久化任务队列，支持重启恢复、重试和取消。
5. 原始资料变化、归档或删除前生成依赖影响预览；多来源页面保留仍有效的来源贡献，不执行静默级联删除。
6. 结构检查由程序执行，AI 只提出矛盾、过时和知识缺口候选；重复页面合并与所有修复先生成计划，再由用户确认。
7. 计划被安全校验暂停后提供两个明确恢复动作：保留现有页面并生成其余内容，或携带校验原因补全后重新规划；重复尝试不得累积相同错误。

验收：

- 模型输出无法覆盖结构文件或写入资料库外部路径。
- 无效页面不会进入正式 Wiki，用户能查看失败原因并重试。
- 同一页面被多份资料更新时不丢失既有来源，异常合并可以恢复。
- 中断或重启后 Wiki 任务能够继续，切换资料库不会串任务。
- 资料变更前可看到受影响页面、保留项和建议动作。

P5E.2 已完成：结构文件由程序确定性维护；模型输出在写入前经过类型、路径、来源和 frontmatter 校验；无效输出进入 staging，并在 Web 中转译为可操作的待修正草稿；页面合并保留来源、标签与关系并防止正文异常缩减；暂停计划可保留原页继续或补全后重新规划；Wiki 任务支持持久化、重启恢复、重试与取消；资料归档前展示依赖影响；结构检查与 AI 语义建议保持分层，所有实际修改仍需用户确认。

### P5E.3：Web UI 系统体验与设置中心（完成）

本阶段在进入联网资料扩展前，完成系统级但仍面向普通学习用户的设置与交互基础：

1. 用户级偏好原子保存到 `BOBODAN_HOME/preferences.json`，使用 `schema_version + revision` 处理迁移和并发冲突；设备布局状态继续留在浏览器本地。
2. 设置中心采用左侧搜索导航和右侧分组内容，桌面为居中弹窗，移动端为全屏页面，并通过 `?settings=<section>` 支持深链接和刷新恢复。
3. 助手称呼、教学方式、回答深度、反馈强度、用户资料、阅读排版、默认 Provider、记忆和 Web 安全 Skills 均有明确设置入口。
4. Composer 支持会话 Provider、回答深度、停止生成、结构化 `@资料 / @会话` 引用和按启用状态过滤的 Slash / Skills 菜单。
5. 后端断开时显示全局恢复条并按 `2s → 5s → 10s → 30s` 重试；正常状态不常驻，状态页不暴露密钥、绝对路径、Trace 或原始日志。
6. 对话只能提出回答深度、教学方式、反馈强度和记忆开关的修改建议；用户确认后才应用，拒绝或关闭不会修改设置。

阶段验收结果：Python `1082 passed`；Vitest `4 passed`；TypeScript 与生产构建通过；Playwright 桌面、窄屏和移动端 `42 passed`。随后进入并完成 P5F。

### P5E.4：LLM Wiki 全库编排与覆盖系统（完成）

> 历史阶段说明：本节记录 P5E.4 当时的实现与验收。其“每份资料生成 Wiki 页面 / 以覆盖率驱动日常流程”的产品位置已被 P5E.6 取代；当前只在高级维护 / 历史整理中保留 workflow 和 orchestration。

P5E.4 修正早期 Wiki 将大量选中文档顺序截断后交给一次模型调用的问题。正式 Wiki 流程以整个活动资料库为发现边界，不要求用户记住哪些资料已经整理，也不把手动选择默认解释为排除其他资料。

默认流程：

```text
扫描资料与 Wiki 来源映射
→ 标记未覆盖、部分覆盖、已覆盖和原文变化
→ 每批最多 5 份资料读取全部有效章节
→ 全库检索补充跨资料关系
→ 每份资料生成独立摘要页
→ 规范化合并概念、实体、分析和问题候选
→ 按小页互链规则生成计划
→ 用户整轮确认一次
→ 安全页面写入，冲突和拆分项保留处理
```

核心约束：

1. Library 主动作是“整理未覆盖资料”；人工多选、课程和严格选中属于高级范围控制。
2. 普通 Chat 默认全库检索，选择资料只提高排序；“仅这些”才向 RAG 发送严格 `document_ids`。
3. 每份原始资料必须有一个 `wiki_source` 页面；概念与实体跨资料、跨批次去重。
4. 每个概念页只处理一个规范主题；正文超过 7 个二级章节或约 4500 字符时进入拆分候选。
5. 大型旧页面在来源覆盖检查完成前不得被短草稿缩减；拆出的子页面可以先作为安全新增项。
6. 覆盖状态从 Wiki frontmatter 的 `source_refs`、`source_hash` 和当前资料指纹重建，缓存不成为第二真相源。
7. 长计划使用资料库内持久化 Wiki run；进程中断后标记为可重试失败，不伪装成仍在运行。
8. 运行完成前不写正式 Wiki；用户确认后才创建检查点并应用整轮安全变更。

公开接口包括 `GET /api/kb/wiki/coverage`、`POST/GET /api/kb/wiki/runs` 以及 Chat run 的应用、取消和恢复入口。旧 `/wiki/plans` 与历史 artifact 继续兼容。

阶段验收结果：Python `1135 passed`；Vitest `5 passed`；TypeScript 与生产构建通过；Playwright 桌面、窄屏和移动端 `69 passed`。真实资料验收使用 5 份现有学习资料完成 1 个批次，生成并写入 5 个资料摘要页与 5 个概念 / 实体页，检查 74 个来源定位均有效，5 份资料全部转为已覆盖；浏览器可从资料摘要跳转并高亮原文 chunk，最后通过运行级检查点恢复为写入前状态。

### P5F：可信资料扩展（完成）

本阶段已经交付用户确认优先的普通网页研究流程：

1. 本地资料不足时由无网络副作用的 `request_web_search` 生成确认卡，不静默联网。
2. 用户确认、一次性联网或 `/web search` 后，使用 Tavily / Exa 搜索并展示候选标题、域名、摘要和来源类型建议。
3. 候选默认不勾选；用户选择 1–4 个来源后才直接读取正文，失败时可使用明确标注的 Jina Reader 后备。
4. 每个资料库使用独立 `research.db` 保存 URL、访问时间、读取方式、正文哈希、引用片段和不可变证据快照。
5. 已确认网页证据可用于 Chat 和练习生成；搜索摘要、AI 常识和失败网页不能伪装成证据。

P5F 收尾修正进一步补齐：

1. 联网权限升级为“每次询问 / 模型自动”双模式，默认询问；自动模式只开放受限 `web_research`，不开放任意 HTTP、MCP 或浏览器工具。
2. 自动研究按官方 / 参考资料优先、搜索排名和域名去重选择最多 3 个来源，读取正文快照后继续同一轮模型执行。
3. Practice 在检索无结果时先读取选中资料章节，再对资料标题与课程名做确定性模糊匹配；模型格式异常只修复重试一次。
4. Chat 的 `question_generate` 产出持久化练习就绪卡，用户点击后幂等创建 Practice session，不在对话正文展开整套题目。
5. Chat 运行状态使用正文流内的 Bobodan 图片表达理解、阅读、写作与完成阶段，不展示原始思维链。

验收：

- 用户能区分本地资料、网页来源、AI 补充和待核实。
- Web 搜索失败不会阻塞本地资料问答与练习。
- 不允许把搜索摘要或 AI 常识伪装成用户资料。

验收结果：Python `1102 passed`；Vitest `5 passed`；TypeScript 与生产构建通过；Playwright 桌面、窄屏和移动端 `57 passed`。这条记录属于历史阶段；后续工作按 [`ROADMAP.md`](../ROADMAP.md) 的当前批次推进。

### P5F.1：个人学习知识库（完成）

目标是让用户长期使用 Bobodan 后，系统逐渐理解“学过什么、掌握了什么、容易在哪里出错，以及怎样讲解最有效”，而不是只保存聊天记录。

沉淀规则：

1. `LearningEvent` 记录资料库、事件类型、知识点、结果、来源和时间。做题、掌握度、错题、阅读进度和复习记录属于确定性学习数据，自动保存。
2. `KnowledgeCandidate` 保存候选内容、形成原因、证据、建议范围和确认状态。用户观点、长期结论、画像推断、个人总结与跨资料发现先进入候选区。
3. `PersonalKnowledgeItem` 保存已确认知识的全局 / 资料库范围、类型、状态、置信度、证据和更新时间。未确认候选不得作为稳定用户事实。
4. 称呼、教学偏好和长期目标属于用户级全局数据；掌握度、错题、课程进度、学习笔记和资料相关结论按 `library_id` 隔离。
5. SQLite 是个人学习知识库的 truth source；确认后的高价值内容可以导出为 Markdown / Obsidian，但导出文件不反向成为第二真相源。
6. 用户可以查看、确认、拒绝、编辑、固定、删除、导出和清空个人知识；删除后 Chat、Practice 和 Review 的个性化上下文必须同步失效。
7. Chat、Practice 和 Review 可以使用已确认知识与确定性学习状态调整讲解、出题和复习，并向用户展示形成依据与更新时间。

实现继续扩展现有 `MemoryService`，没有创建第二套记忆服务。当前数据边界为：

- 全局已确认知识与全局候选：`BOBODAN_HOME/personal-knowledge.db`。
- 资料库知识、候选、学习事件、阅读进度与整理任务：`<library>/.bobodan/bobodan.db`。
- 称呼、教学方式、回答深度和长期目标：`BOBODAN_HOME/preferences.json`。
- 旧 `.bobodan/memory/*.md` 与 `.bobodan/daily/*.md`：只读迁移来源，不再自动写入或注入提示词。

已实现接口：

- `GET /api/memory/overview`、`GET /api/memory/knowledge`、`POST /api/memory/knowledge`：读取概览、筛选和新增个人知识。
- `PATCH /api/memory/knowledge/{id}`、`DELETE /api/memory/knowledge/{id}`：编辑、固定或删除。
- `GET /api/memory/candidates`：列出待确认候选。
- `POST /api/memory/candidates/{id}/confirm`、`POST /api/memory/candidates/{id}/reject`：确认或拒绝候选。
- `GET /api/memory/events`、`PUT /api/memory/reading-progress/{document_id}`：读取学习时间线并更新阅读进度。
- `POST /api/memory/consolidate`：手动触发候选整理，不直接提升为长期知识。
- `GET /api/memory/legacy/preview`、`POST /api/memory/legacy/import`：把旧 Markdown 记忆预览为待确认候选。
- `GET /api/memory/export`：导出已确认知识；导出文件不反向参与运行时检索。
- `POST /api/chat/memory/proposals/{artifact_id}/confirm|reject`：处理 Chat 中的明确记忆确认卡。

资料库级请求继续携带 `X-Bobodan-Library-ID`。自动整理只能读取当前资料库的学习事件；全局偏好由服务端单独合并，不能借此跨库读取资料、错题或课程进度。

验收：

- 做题、阅读和复习事件自动记录，但不会自动创建资料 Wiki 页面。
- 用户观点只进入候选区，确认前不会成为长期事实或影响高置信度回答。
- 全局偏好可以跨资料库使用，课程知识和学习状态不会串库。
- 删除个人知识后，检索、提示词和个性化行为同步更新。
- 已确认知识可以导出 Markdown，导出文件不参与双向自动同步。

阶段验收结果：Python `1118 passed`；Vitest `5 passed`；TypeScript 与生产构建通过；Playwright 桌面、窄屏和移动端 `63 passed`。

### P5E.5：Wiki 易用性、手写编辑与 AI 成本控制（完成）

> 历史阶段说明：本节记录 P5E.5 当时的实现。P5E.6 之后 Library、Chat 和知识地图不依赖 Wiki 整理完成度，`wiki_note` 等历史页面也不是原始资料证据。

P5E.5 解决 P5E.4 验收后暴露的产品问题：修复预览没有后续动作、首次用户不理解资料与 Wiki 的关系、完整未覆盖范围耗时过长，以及模型调用没有真实用量和缓存可见性。

默认流程调整为：

```text
导入并直接检索原始资料
→ 查看下一批 5 份资料的耗时与 Token 估算
→ 选择快速建档 / 标准整理 / 深度整理
→ 审查并确认 Wiki 计划
→ 写入、手写修改或新增个人笔记
→ 通过持久化修复计划维护索引、断链和过期候选
```

核心约束：

1. 标准整理每次最多 5 份，深度全库必须二次确认；快速建档不调用模型。
2. Wiki run 使用请求、输入 Token 和输出 Token 三重预算。达到上限后保存草稿并暂停，继续时复用严格输入缓存。
3. 全部 Wiki 页面可编辑。用户修改 AI 页面后标记为共同维护，AI 计划必须校验 `content_revision`，不能覆盖计划创建后的手写变化。
4. `wiki_note` 是用户个人笔记，可参与 RAG 并显示“个人笔记”来源，但不能伪装成原始资料证据。
5. 修复按钮创建持久化 `WikiRepairPlan`；本地可确定项、AI 审核项和人工确认项分别展示，安全修复写入前创建检查点。
6. 偏好升级到 schema v4，支持 Wiki 发现与页面撰写的任务级 Provider、默认整理模式和预算。
7. Provider 响应保留实际 usage；DeepSeek 与 OpenAI-compatible 缓存字段统一进入 `BOBODAN_HOME/usage.db`。未报告缓存时显示“未报告”，不伪装成零命中。
8. Wiki 提示词采用稳定 system 前缀和动态 user 尾部；精确生成缓存按 Provider、模型、提示词版本、资料指纹、指令和页面 revision 失效。
9. Wiki 页面分为知识页、资料索引和个人笔记。资料索引只提供短摘要、学习地图、关键结论和原文入口，不逐章复刻资料；概念、实体、分析与问题页才承载可复用知识。
10. 运行估算按同 Provider、同模型的真实发现 / 写作样本分别计算，排除测试调用并显示样本量与可信度；本地缓存不计入预估，完成后显示本轮真实请求、Token、模型等待和两级缓存数据。

阶段验收结果：Python `1148 passed`；Vitest `5 passed`；TypeScript 与生产构建通过；Playwright 桌面、窄屏和移动端 `75 passed`。

### P5E.6：知识地图产品重置（已完成）

P5E.4 与 P5E.5 证明了全库发现、可恢复运行、编辑保护和用量账本可用，但真实使用暴露出产品模型混杂：资料摘要、概念百科、个人笔记、批量生成和维护任务共同使用“Wiki”名称，用户无法判断其用途、下一步和生成成本。P5E.6 不推翻已有的资料、来源、版本、缓存与运行保护；它重置主界面的心智模型。

产品定义：

```text
Chat：提问、全库检索、基于原始资料回答
知识地图：浏览主题和概念关系、定位原文、补充个人笔记
资料卡：查看一份原始资料的目录、检索状态、关联概念和原文位置
高级维护：批量整理、深度解读、修复、预算和 Provider 路由
```

核心决策：

1. 主入口从“Wiki”更名为“知识地图”。首页是课程 / 主题簇总览；点击后逐层展开概念和资料来源节点，不在知识地图内重复提供 AI 搜索框。用户提问和搜索仍由 Chat 承担，Chat 可深链至相关概念。
2. 图谱默认显示概念节点和较小的资料来源节点。资料节点打开资料卡并可直接跳到章节、页码、幻灯片或 chunk；个人笔记只在概念详情中出现，不默认混入图谱。
3. 导入资料后立即用本地目录、标题、章节、课程和原文定位建立基础资料索引，不调用 LLM。资料始终可以直接进入 RAG；“没有 Wiki”不能阻塞问答、练习或阅读。
4. `wiki_source` 不再作为知识页的强制产物。它迁移为资料卡中的可追溯索引信息；概念、关系和用户笔记才属于知识地图内容。每份资料不再为了覆盖率强制生成一篇 AI 摘要。
5. AI 概念提取只在两种场景按需发生：用户在资料卡中选择“提取本资料概念”，或 Chat 遇到尚无概念页的相关主题。每次产生约 5-12 个候选，用户一次审查、改名、合并或排除后才写入正式地图；不在导入后自动全库生成。
6. 概念页默认为证据优先的短卡：一句定义、3--7 个要点、关系、1--5 条原文摘录与定位、独立个人笔记。长篇“深度解读”是按需、可删除、明确显示成本的衍生内容，不能替代原文证据。
7. Chat 以知识地图定位概念和资料，但正式回答、练习和复习仍读取并引用原始资料。个人笔记可以作为标记清楚的辅助上下文，不得伪装成事实来源。
8. 用户笔记由用户主控。AI 可以提出结构化、补充关联或冲突检查建议，必须显示差异并经用户确认；不得直接覆盖笔记。概念 AI 更新也必须保持版本检查和可撤销性。
9. 性能主流程是“本地立即可用，AI 渐进补充”：单份资料概念候选目标约 30 秒，最多 5 份资料增量显示，完成一份即可审查；离开、刷新、取消和 Provider 失败都保留已完成候选。全库深度生成只存在于高级维护，不在新手流程自动触发。
10. 当前测试资料库允许用户显式执行“备份并重置旧 Wiki”：旧目录改名保存后创建空知识地图。该动作绝不作为正式用户升级策略；真实资料库只能迁移预览、保留旧内容或由用户单独确认归档。

第一阶段验收：

- 用户从资料库进入知识地图，能浏览主题簇、概念关系和资料来源节点。
- 用户点击概念可见结构化短卡，并从来源摘录跳回原文位置。
- 用户可从资料卡提取概念候选，单次审查后写入地图；候选失败不会影响原始资料检索。
- 用户可写个人笔记，AI 修改只以差异建议出现。
- 当前测试资料库可执行备份式重置；其他资料库不会被自动删除、覆盖或迁移。
- 深度解读、全库批量生成、修复计划、预算和 Provider 路由仍可用，但只放在折叠的“高级维护”入口。

P5E.6 不在本阶段做：复杂全图一次性可视化、导入即自动概念生成、无来源的 AI 教材页、自动覆盖用户笔记，以及把知识地图作为 Chat 的必经前置步骤。

已实施内容（P5E.6 完成）：

1. **`graph/concept_store.py`** — SQLite 概念图谱后端（6 张表：`concepts`、`relationships`、`evidence`、`concept_candidates`、`concept_extraction_runs`、`concept_positions`），支持 CRUD、候选审查、位置持久化和图状态快照。
2. **`wiki/extractor.py`** — `ConceptExtractor`：LLM 从资料内容提取 3–8 个核心概念 + ≤12 个细节概念，输出候选及关系，有效关系类型受约束。
3. **`service/concept_service.py`** — `ConceptService`：封装所有概念图谱业务逻辑，确认候选自动创建概念和关系，reject 支持按天压制。
4. **`web/backend/routers/graph.py`** — 19 个 REST 端点，覆盖图状态、子图、概念 CRUD、关系 CRUD、候选操作、提取触发与恢复、位置保存和旧图谱迁移；`/api/graph` 纳入 library-scoped 中间件。
5. **前端** — Sigma.js v3 + Graphology WebGL 渲染；`KnowledgeMapPage`（三视图：地图 / 目录 / 来源）、`GraphCanvas`、`ConceptSidebar`（180ms 滑入侧栏）、`CandidateReviewPanel`（底部 sheet + 键盘快捷键）；导航新增"知识地图"入口。
6. **`tests/test_concept_store.py`** + **`tests/test_concept_service.py`** — 覆盖 DDL、CRUD、候选压制、图状态、子图邻居、服务层验证和 LLM 提取 mock。
7. **旧图谱迁移** — “设置 → 记忆与数据”惰性检测 `graph_store.json`，展示 Concept / Memory / 关系与风险预览；用户选择后导入候选，校验完成才归档源文件。旧 JSON / Neo4j 图不再参与同步、Agent 工具或 Library 状态统计。

### P5G：文档完整性、Windows 桌面发布与支撑页面（历史阶段记录）

P5G 不先堆叠新页面。执行顺序固定为：

```text
P5E.5 Wiki 易用性、手写编辑与 AI 成本控制（完成）
→ P5E.6 知识地图产品重置（完成）
→ P5G.0 文档提取完整性与发布合规（完成）
→ P5G.1 单进程本地 Web（完成）
→ P5G.4 模型供应商管理（Provider Catalog，完成）
→ R0 质量与调试基建（完成，2026-08-28，分支 feat/r0-quality-infra）
→ P5G.2 Windows Electron 桌面版（推迟：先推进 docs/ROADMAP.md 的 W1–W4 主体）
→ P5G.3 支撑页面与体验收尾
```

当前唯一路线文档是 **[`ROADMAP.md`](../ROADMAP.md)**（合并了 openhanako 研究路线 R0-R3、DeepTutor/OpenMAIC/qiaomu 调研借鉴清单、整机优化计划遗留与 2026-08-01 体验审查未决项；已完成的部分归档于 [`archive/`](.)）。
P5G.2 启动前必须吸收其 W5 门禁与研究结论：sidecar 独立进程、server-info 握手、契约测试替代浏览器 e2e。

首发版本不集成 OCR。Bobodan 只处理文档已有文本层，并明确告诉用户哪些页面、幻灯片或图片没有形成可检索文字。OCR 不是技术上永久禁止，而是保留为未来可选组件；当前不加入引擎、模型、下载入口或安装包依赖。

#### P5G.0：文档提取完整性与发布合规

文档提取：

1. PDF 移除 PyMuPDF，统一使用宽松许可证的 `pypdf` 提取文本、页码和空白页状态。
2. DOCX 提取标题、段落和表格并统计内嵌图片；PPTX 保留标题、文本框、备注和幻灯片定位，同时统计图片与无原生文字幻灯片。
3. Markdown 和纯文本继续直接切块；图片文字不识别，也不把空白结果伪装成已索引内容。
4. 导入和同步为每份资料保存 `complete / partial / empty / error` 提取状态。零 chunk 资料仍登记到 Library，但标记“当前不可检索”。
5. `empty` 和 `error` 资料不进入 RAG、Practice 或 Wiki 编排；Wiki 覆盖增加 `unavailable`，避免后台反复尝试同一份不可读资料。
6. SQLite 是提取状态真相源；旧资料通过第一次完整同步补齐报告，不维护第二份运行真相。

公开类型：

```ts
type ExtractionStatus = "complete" | "partial" | "empty" | "error";

interface DocumentExtractionReport {
  document_id: string;
  file_type: "md" | "txt" | "pdf" | "docx" | "pptx";
  parser: string;
  status: ExtractionStatus;
  total_units: number;
  extracted_units: number;
  empty_units: number;
  extracted_characters: number;
  image_count?: number;
  warnings: Array<
    | "scanned_or_empty_pages"
    | "images_not_recognized"
    | "slides_without_text"
    | "no_searchable_text"
    | "parser_error"
  >;
}
```

- `DocumentSummary` 增加 `extraction_status` 和简要提取统计。
- `GET /api/kb/documents/{id}/extraction` 返回完整提取报告。
- 导入和同步响应增加状态计数及本轮变化资料的提取报告。

发布合规：

1. 项目采用 Apache-2.0，根目录增加 `LICENSE`；移除 AGPL / 商业双许可的 PyMuPDF，CI 阻止重新引入 GPL / AGPL 依赖。
2. 增加 `THIRD_PARTY_NOTICES.md`，审计 Python、npm、Electron、字体、图标和品牌资源；无法确认再分发许可的资产不得进入安装包。
3. 增加 `PRIVACY.md`，明确本地资料、远程模型、Tavily、Exa 和 Jina Reader 的数据流与删除边界。
4. 发布产物必须附 Python / npm SBOM、依赖许可证清单和 SHA256 校验值。
5. 首个 GitHub Prerelease 允许暂不签名，但必须说明 Windows SmartScreen 的“未知发布者”提示；取得代码签名证书前不启用自动更新。

#### P5G.1：单进程本地 Web

**状态：已完成（2026-08-12）。** `python agent.py web` 单进程启动完整产品；验证：Python 1212 passed / Vitest 19 passed / 生产构建通过，真实启动冒烟覆盖健康检查、SPA 深链接与静态资源。

1. FastAPI 在生产模式托管 React `dist`，并为 `/chat/*`、`/library`、`/practice/*` 等 SPA 深链接回退到 `index.html`。
2. 增加 `bobodan web`，默认绑定 `127.0.0.1`、选择可用端口并自动打开浏览器；开发模式继续使用 Vite + FastAPI。
3. 应用数据写入 `~/.bobodan`（2026-08-12 桌面端资料进库设计确认，替代原 `%APPDATA%\Bobodan`），日志写入 `%LOCALAPPDATA%\Bobodan\logs`；用户资料库继续保存在用户选择的文件夹中。
4. SQLite FTS5 是零模型默认检索。Ollama、Embedding 和远程服务保持可选，不自动下载或随应用分发模型权重。
5. 生产启动必须提供明确的健康检查、端口冲突、后端崩溃和配置缺失恢复信息。

#### P5G.2：Windows Electron 桌面版

1. 采用 OpenHanako 式 `Electron + React + Python FastAPI sidecar`，不重写现有 Python service、RAG、Wiki 和学习逻辑。
2. PyInstaller 使用 `onedir` 构建 `bobodan-server.exe`；Electron 负责单实例、窗口、文件夹选择、外部链接、sidecar 生命周期和崩溃提示。
3. Electron 等待 `/api/health` 成功后进入主界面，退出应用时终止 sidecar；端口冲突和启动失败必须有可操作恢复入口。
4. 启用 `contextIsolation`，禁用 renderer Node.js 权限，只通过白名单 preload IPC 暴露桌面能力。
5. Provider 密钥真相源是 `~/.bobodan/provider.json`（P5G.4 建立，web / CLI / Electron 共享）；Electron 可选用 `safeStorage` 把密钥升级为系统加密后作为进程环境注入 sidecar，不强制。密钥不得出现在 HTTP 响应、URL、日志、资料库或安装目录。
6. electron-builder 生成 Windows x64 NSIS 安装包 `Bobodan-Setup-x64.exe`，同时发布 `SHA256SUMS.txt`、SBOM 和第三方许可清单。
7. GitHub Actions 在干净 Windows runner 上构建并执行安装包启动测试。首版不内置 OCR、Embedding、本地大模型、离线模型包或自动更新。

#### P5G.3：支撑页面与体验收尾

桌面发布链路稳定后，再按以下顺序补齐：

1. Roadmap：学习目标、当前阶段和今日任务。
2. 会话增强：正文搜索、归档、恢复和引用历史。
3. 完整 Memory Browser：跨资料库浏览、完整搜索和发布级数据恢复。
4. 复习自动化：用户确认后创建间隔复习提醒和阶段总结，不暴露通用 Cron 配置。
5. 数据保护：资料编辑检查点、备份恢复、记忆导出和安全审计入口。
6. Workbench 只展示后端、资料库、索引、模型与备份状态，不开放通用 Agents、MCP 或 Logs 后台。

P5G 总体验收：

- 混合文本 / 扫描 PDF、含表格或图片的 DOCX、含图片或无文字页的 PPTX 都能产生准确、可理解的提取报告。
- 零 chunk 文档仍显示在 Library，并从 RAG、Practice 和 Wiki 安全排除。
- 无 Ollama、Embedding、Python 和 Node.js 的干净 Windows x64 环境可以安装并启动 Bobodan。
- FastAPI 静态托管、SPA 深链接、SSE Chat、Practice、Review 和 Wiki 在生产模式通过。
- Electron 覆盖端口冲突、sidecar 失败或崩溃、重复启动、正常退出和用户数据目录隔离。
- API Key 不写入资料库、日志、URL、HTTP 响应或安装目录。
- CI 通过 Python、Vitest、TypeScript、生产构建、Playwright、PyInstaller、Electron smoke test、许可证审计、SBOM 和 SHA256 检查。

### P5G 补充规划（2026-08-01 体验审查补充）

以下五项在 2026-08-01 体验审查（[`archive/experience_review_2026-08-01.md`](experience_review_2026-08-01.md)）中被确认为计划缺口：P5G 章节原有条目停留在功能名级别，缺少桌面本地产品发布所需的落地细节。**验收要求留在本节**（按 `docs/README.md` 的权威划分，发布门槛以本文为准）；**排期与门禁在 [`ROADMAP.md`](../ROADMAP.md) W5**。两者不是互相让渡的关系——不要写"以对方为准"。不能脱离该路线单独恢复执行。

1. **数据备份 / 恢复专项**：明确备份对象清单（资料库、`personal-knowledge.db`、`usage.db`、`research.db`、`preferences.json`）、备份格式与 SQLite WAL 一致性方法、手动 / 自动触发、校验与恢复 UI、失败恢复验证。这是本地优先产品用户信任的根基。
2. **复习提醒交付机制**：指定 Windows 系统通知或托盘常驻方案；Electron 不常驻时提醒无法送达，Review 闭环缺最后一环。
3. **应用升级路径**：定义安装器覆盖安装行为、数据目录版本检测、升级前备份提示；自动更新可继续延后，但升级动作本身必须规划。
4. **卸载清理与数据保留策略**：NSIS 卸载器的行为契约（保留用户资料库 vs 清理应用数据 vs 完整清除），写入 P5G.2 验收。
5. **桌面环境适配与性能预算**：DPI / 高分屏 / 多显示器验收项（纳入 P5G 总体验收），以及首启时间、安装包体积目标值。

### P5G.5：Chat 体验与个人笔记统一（2026-08-13 确认，完成）

用户在真实对话中发现四类体验问题，逐项 grill 确认后落地：

1. **概念关系卡片重复 + 空卡片**：`concept_map_query` 结果为空（如提问的概念不在图谱中）不再附带 `knowledge_context` artifact；一轮内多次图谱查询只保留第一张卡片；收到卡片不再自动弹开右侧「学习书桌」面板，改为卡片内「在学习书桌查看」按钮按需打开。
2. **笔记入口缺失**：原 Wiki note「新建」按钮从未接线，用户无法写笔记。决策：个人笔记统一到**个人知识**（`personal_knowledge`），Wiki note 停止新建、隐藏「个人笔记」Tab，已有 `notes/*.md` 原地只读保留；侧栏新增一级「笔记」导航 → `/notes` 页面（列表 + 搜索 + 写笔记 + 管理全部入口）。
3. **笔记 ↔ 资料库双向轻联动**：个人知识条目新增 `references` 字段（`[{document_id, chunk_id, title}]`）；写笔记时可勾选关联资料，笔记卡片显示引用并可跳转原文；资料阅读器显示「相关笔记」。笔记 ↔ 知识地图的关联**暂缓**（第二步，待笔记量上来后再做概念级关联）。**架构边界**：个人笔记永不进入概念图谱，只做关联展示，不污染证据链。
4. **流式观感**：后端为证据门禁先完整生成再回放 token（`emit_content=False`），前端收到的是瞬时连续到达的 token、经 React 批处理呈现为"整段弹出"。修复：前端 `useChatStream` 加渐进显示缓冲（匀速 flush 模拟打字机），不改变后端证据门禁安全契约。

验证：Python `1233 passed`（新增 references 往返 + 反向查询回归）、Vitest `19 passed`、前端 lint 与生产构建通过。

### P5G.6：前端视觉统一与沉浸式笔记编辑器（2026-08-13 完成）

用户实际使用后反馈两个 UI 问题（笔记是"填表"、模型下拉未适配主题），并授权做一轮"总体不变、全面视觉优化"（grill 确认范围 = 所有页面视觉细节统一，布局和配色主基调不动）：

1. **主题化下拉组件**：原生 `<select>` 的下拉面板是浏览器系统样式，无法跟随暖纸色主题。新建 `DropdownSelect` 组件（portal 定位、键盘导航、点击外部/滚动关闭），模型下拉做成「供应商分组 → 模型」两级、回答深度做成简单单选；全面替换 composer、设置页、Library、知识地图、记忆管理、供应商管理、候选审查的所有原生 `<select>`。
2. **沉浸式 Markdown 笔记编辑器**：`/notes` 写笔记从"标题框 + 正文框 + 复选框堆叠"的表单，改为沉浸式 Markdown 编辑——正文为主角、第一行 `# 标题` 自动提取为标题、编辑/预览切换、`Ctrl+Enter` 保存 `Esc` 关闭、关联资料折叠到底部。笔记列表卡片加 hover 态、内容三行截断、空状态加引导按钮。
3. **视觉细节统一**（保持布局和配色主基调不变）：
   - 补缺失设计 token：`--sage-deep`（成功绿）、`--ink-soft`（柔和墨色）、`--accent`（复选框）、`--shadow-dialog`（弹窗阴影）；替换散落的硬编码绿色 `#4f6e4c`/`#486545`（13 处）为 `--sage-deep`，hover 深蓝 `#142a4a` → `--blue-soft`，hover 浅蓝 `#dde5ee` → `--blue-wash`。
   - 统一弹窗阴影为一个 token（6 处冷蓝/墨色混用 → `--shadow-dialog`）。
   - 统一圆角：composer 10→8px、run-summary 10→8px、candidate-panel 12→8px、session-row 输入框 5→7px。
   - 补缺失 hover 态：send-button、wiki-editor-toolbar、5 个 tab 组（memory/wiki-view/library/mention/library-mode）。
   - 复选框主题化（accent-color），修 `--ink-soft`/`--accent` 未定义导致的无效值。

验证：Vitest `19 passed`、前端 lint 与生产构建通过（纯前端改动，Python 未变）。

### P5G.4：模型供应商管理（Provider Catalog，2026-08-12 完成）

对标 OpenHanako（Electron 桌面 agent：38 个 provider 插件 + `~/.hanako/provider-catalog.json` 用户配置目录）对现有多供应商能力做差距分析。会话级切换、默认模型、任务路由、测试连接已存在，本次补的是**配置管理产品化**：用户不再需要碰 `config.yaml` 和 `.env`。与桌面版无关，Web 端（`python agent.py web`）即可完整使用；Electron 只是入口不同，共享同一后端与 `~/.bobodan`。

**8 项决策（grill 确认，2026-08-12）：**

1. **API key 设置页 UI 输入，明文存 `~/.bobodan/provider.json`**。本地单机明文风险可接受（OpenHanako 同款模式）；加密升级留给 P5G.2 safeStorage。
2. **供应商下挂多模型**：聊天框下拉改为「供应商分组 → 选模型」两级选择；会话级切换保留。
3. **完全开放自定义供应商**：名称 + base_url + api_key + 模型列表，保存即用（OpenAI 兼容协议）；现有 6 个预设（deepseek / minimax / openai / dashscope / siliconflow / openrouter）变成可复制的模板。
4. **本期只做 OpenAI 兼容协议**（`/chat/completions`，含 streaming 与工具调用）；协议层留可扩展抽象，Anthropic / Gemini 原生协议后续按同一接口加入。
5. **模型列表远程自动拉取**：`GET {base}/models`（OpenAI 兼容端点普遍支持）拉回模型名自动填入；不支持该端点的服务手输兜底。
6. **旧配置零断供迁移**：首次启动把 `config.yaml` 的 `llm.providers` 自动迁入 `provider.json`；`api_key` 为空时回退读 `api_key_env` 环境变量，用户在 UI 补填后自然覆盖。
7. **任务级路由升级到模型级**：主题发现 / 页面撰写等任务选择器与主聊天共用同一两级选择器（供应商 → 模型）。
8. **Ollama 作为内置模板**：免 key（authType none）、`base_url=http://localhost:11434/v1`、自动拉取本地已下载模型。仅连接用户已安装的 Ollama，不属于「本地大模型安装包」范围（见下方本轮明确不做）。

**技术要点：**

- 新增 `providers/catalog.py`：读写 `~/.bobodan/provider.json`（schema：`{version, providers: {name: {type, provider_name, base_url, api_key, api_key_env, model_default, models: [{id, name}], preset}}}`）。配置解析优先级：`provider.json` → `config.yaml` `llm.providers` → 内建模板。
- 后端 API：`GET /api/providers`（key 脱敏 + 配置状态）、`POST /api/providers/test`（已有测试连接升级为按 key 字段）、`POST /api/providers/fetch-models`、`PUT /api/providers`（新增 / 编辑）、`DELETE /api/providers/{name}`。
- `deps.get_default_provider_name` 升级为「默认供应商 + 其默认模型」解析；`LLMProvider` 契约不变。
- 前端：「AI 与模型」tab 从只读升级为完整管理（供应商列表、添加 / 编辑表单、key 输入、测试连接、拉取模型）；新增两级模型选择器组件，ChatPage 与任务路由共用。
- 与 P5G.2 的协调：P5G.2 第 5 条的 safeStorage 成为**可选项**——Electron 层可把 `provider.json` 密钥升级为系统加密（进程环境注入），`provider.json` 本身保持为可迁移的普通配置；「API key 不写入资料库、日志、URL、HTTP 响应或安装目录」验收不变（`~/.bobodan` 是应用数据目录，不是资料库 / 安装目录）。

**验收：**

- 旧环境（仅 `.env` 有 key）：启动后 6 个模板可用且环境变量 key 生效；UI 补填 key 后不再依赖环境变量。
- UI 添加自定义 OpenAI 兼容供应商（如 Kimi）→ 保存 → 拉取模型列表 → 聊天切换成功。
- Ollama 模板免 key 可用，拉取本地模型列表成功。
- 密钥在 API 响应中脱敏；`provider.json` 不进入资料库、日志或安装目录。
- Python 单测 / Vitest / 生产构建通过。

**完成验证（2026-08-12）**：Python `1231 passed`、Vitest `19 passed`、前端 lint 与生产构建通过；真实启动冒烟覆盖 settings 列表（迁移 6 供应商 + ollama 模板）、PUT / DELETE 供应商、密钥脱敏、fetch-models 失败兜底、DeepSeek 测试连接（853ms 真实响应）与 `provider::model` chat 引用。

### 本轮明确不做

- 完整 Agent / MCP / Logs 管理后台。
- 频道、社交平台入口和多 Agent 群聊。
- 独立 Canvas 产品、复杂知识图谱和完整知识编辑器。
- 模拟考试、限时训练、复杂题型和完整能力模型。
- 多用户 SaaS、跨设备同步、移动端原生 App。
- 主题 / 封面画廊、插件市场、角色卡市场、班级协作、排行榜或社交分享。
- OCR 引擎、OCR 模型、Embedding 模型、本地大模型和离线模型安装包。
- macOS / Linux 安装包、代码签名和自动更新；这些在 Windows 无签名 Prerelease 稳定后再评估。
