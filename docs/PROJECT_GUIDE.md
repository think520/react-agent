# Bobodan 项目指南

这份文档是 Bobodan 后续给人和 AI 看的唯一主入口。想知道产品是什么、当前到哪一步、下一步做什么、哪些功能该隐藏、代码边界怎么守，先读这里。

## 1. 产品定位

Bobodan 是一个 **ChatGPT / Gemini 形态的个人学习 AI**。

用户从一个对话主页开始提问、上传资料、询问课程、生成练习和安排复习；系统在背后调用本地知识库、RAG、题库、掌握度、记忆和 Obsidian 能力，把每次对话沉淀成可追踪的学习进度。

它不是知识库后台，也不是通用 Agent 平台。

更准确地说：

> Bobodan 是一个 chat-first、local-first 的个人学习助手。主入口是自然对话，核心价值是基于用户自己的资料回答问题，并把对话转化为练习、复习和学习路径。

## 2. 第一屏应该是什么

Web 第一屏应该是 AI 对话主页，而不是 dashboard。

### 2.1 视觉硬约束

任何 Web UI、页面原型、组件、练习页、对话页、资料页、复习页、进度页、TUI 或官网设计，开工前必须先读 `docs/DESIGN.md`。

`docs/DESIGN.md` 不是可选参考，而是 Bobodan 的主题色、视觉气质和设计边界。后续设计必须沿用其中定义的 Natural Editorial Zen / Warm Paper Knowledge Garden 方向，以及暖纸色、墨蓝、植物绿、原木色、橘棕、花瓣粉等主题色。

不要临时发明一套新颜色，也不要做通用 SaaS dashboard 风格、紫色 AI 渐变风格或高密度后台风格。若实现中需要新增 token，必须从 `docs/DESIGN.md` 的色彩系统延展。

推荐结构：

```text
左侧：会话 / 课程 / 最近学习
中间：AI 对话主区域
右侧：学习上下文面板
底部：输入框 + 附件 + 学习动作按钮
```

中间像 ChatGPT / Gemini：

- “帮我解释这份 PDF。”
- “根据我的笔记出 10 道题。”
- “我哪里还没掌握？”
- “今天该复习什么？”
- “把这个知识点讲得像老师一样。”
- “根据这门课给我安排 7 天学习计划。”

右侧不是后台，而是随对话变化的学习上下文：

- 当前学习范围。
- 引用来源片段。
- 相关知识点。
- 推荐练习。
- 今日复习。
- 当前掌握度。
- 错题和薄弱点。

输入框附近提供短动作：

- 解释
- 总结
- 出题
- 复习
- 制定计划
- 导出到 Obsidian

### 2.2 产品参考吸收原则

Bobodan 不照抄任何单一产品。它吸收这些产品的功能骨架，再用 `docs/DESIGN.md` 的 Kami 纸面审美重画一遍：

| 模块 | 可参考产品 | Bobodan 吸收什么 |
|---|---|---|
| 对话区 | ChatGPT | 左侧历史 / 项目上下文、中央对话、文件和工具入口、Canvas 思路 |
| 首页氛围 | Pi | 低压、温和、像学习伙伴，不像控制台 |
| 学习卡片 | Gemini | flashcards、quizzes、study guides、互动学习材料 |
| 知识库 | Obsidian | 本地 vault、双链、概念关系、个人 Wikipedia |
| 阅读器 | Readwise Reader | distraction-free reading、highlight、摘录、复习回流 |
| Agent 管理 | ClawPort / Agent Hub | Agent 状态、任务队列、记忆浏览、MCP/Cron/Logs，但不吸收控制台视觉 |
| 本地助手 | OpenClaw | local-first、工具执行、设备/渠道连接、隐私感 |

一句话：

> Bobodan 是看起来像高级纸质学习笔记本的 Agent Operating System，不是黑色终端风 Agent 控制台。

### 2.3 信息架构

长期信息架构分成 **Study** 和 **Workbench** 两组。

Study 是一等入口：

```text
Today
Chat
Practice
Review
Library
Roadmap
```

Web MVP 不一次开放六个一级导航。第一版主导航收敛为：

```text
Chat
Practice
Review
Library
```

- Today 作为 Chat 在无活动会话或用户回访时的起始状态。
- Roadmap 在学习闭环稳定后再升级为独立入口；第一版可从 Today / Review 进入。
- 未实现页面不放一级占位入口。

Workbench 是高级区，默认折叠，可展开或固定：

```text
Workbench / 工作台
  Memory
  Agents
  Skills
  MCP
  Automations
  Logs
  Settings
```

规则：

- Study 负责日常学习，不暴露工程概念。
- Workbench 承载 Agent OS 能力，但视觉低优先级。
- Agents / MCP / Automations / Logs 不进入第一层学习主导航。
- Workbench 不叫 Control Center、Command Center、Admin 或 Dashboard。

### 2.4 关键页面定位

Today：

- 学习伙伴首页，不是 dashboard。
- Web MVP 中复用 Chat 主学习画布，不单独维护第二套页面框架。
- 结构是“一句低压问候 + 一条记忆/上下文 + 2-3 个行动建议”。

示例：

```text
今天想学点什么？

我记得你昨天卡在 Dijkstra 的贪心证明。
今天可以先从 3 道基础题开始，或者继续整理图算法笔记。
```

Library：

- 资料树 + 阅读/来源面板为主。
- 局部概念关系为辅。
- 不做大图谱主舞台。

推荐结构：

```text
左侧：资料树 / vault / 课程 / 标签
中间：文档阅读视图或资料摘要
右侧：来源、双链、相关概念、小型局部图谱
```

Reader：

- 第一版不作为主导航。
- 先作为 Library 内的阅读视图。
- 后续等 highlight、摘录、稍后读、复习回流成熟后，再升级为独立入口。

Practice：

- 主练习入口。
- Cards 是内部题目展示方式，不作为主导航命名。

Review：

- 今日复习入口。
- 承接错题、薄弱点、到期知识点和手动加入内容。

Roadmap：

- 只表示用户学习路线。
- Agent 任务、自动化、日志不叫 Roadmap，放 Workbench。

Canvas：

- 第一版作为 Chat 内的临时展开面板。
- 不作为独立主功能。

示例：

```text
Chat 回答
→ [整理到学习白纸]
→ 打开 Canvas 面板
→ 可编辑摘要 / 提纲 / 练习清单
```

Memory：

- 不进 Study 第一层。
- 学习相关记忆自然出现在 Today / Review / Roadmap。
- Workbench 里提供 Memory Browser。
- Memory Browser 必须支持查看、编辑、删除、固定。

Memory 不只记录学习数据，还要沉淀：

- 学习画像。
- 用户偏好。
- 长期人设 / 关系。
- 讲解方式偏好。
- Obsidian 写回偏好。
- 用户不喜欢的表达方式。

## 3. 全项目复盘结论

### 3.1 总体判断

Bobodan 已经完成“学习 Agent 引擎”和“Web 产品化基础”阶段，但还没有完成普通用户可持续使用的 Web 产品。

现有技术路线不需要推倒重来。Python + FastAPI + SQLite / Qdrant + React Web UI 仍然适合本地优先的个人学习助手。P5C 已把 CLI 能力整理成稳定、可复用、可追踪的 Web 产品合约；下一步进入 P5D，按 Library → Chat → Practice → Review 的纵向闭环实现真实页面。

一句话结论：

> 底层能力与 Web 合约已经就绪，下一阶段停止横向扩功能，优先交付“导入资料 → 提问 → 查看来源 → 做题 → 复习”的本地学习闭环。

### 3.2 当前成熟度

| 模块 | 当前判断 | 说明 |
|---|---|---|
| Agent Runtime | 可用且测试充分 | ReAct、流式输出、工具调用、session、provider 已稳定运行 |
| RAG v2 | 较成熟 | SQLite / FTS5 / Qdrant / hybrid / directory / grep 已具备完整检索骨架 |
| Quiz / Learning | Web 合约就绪 | 支持题目归因、练习恢复、提交进度、掌握度变化、放弃练习和 Review 聚合 |
| Memory | Web 合约就绪 | Web Chat 注入并按 run 刷新 memory prompt，公开 API 不返回本地绝对路径 |
| Service Layer | 产品化基础完成 | CLI / Web 共用 runtime、config 与 service，Review / Practice 聚合已补齐 |
| FastAPI | P5C 完成 | 已有稳定错误结构、流式事件适配、session CRUD、资料导入、Library / Practice / Review API |
| Web UI | 未开始 | 当前没有 frontend 工程、组件、路由或端到端 Web 流程 |
| 测试 | 后端较强 | P5C 完成后全量测试 `1020 passed`，Web API 已覆盖安全事件、错误、会话、练习、复习和导入合约 |

### 3.3 P5C 已解决的问题与剩余边界

已解决：

1. CLI / Web 共用 runtime composition，统一 provider、workspace、skills、memory、trace 和 LLM service config。
2. `/api/chat/runs` 固定使用 POST + `fetch` / `ReadableStream` 消费 SSE，事件收敛为稳定 Web 协议。
3. Web 只接收白名单状态与 artifact，不暴露原始 tool output、specialist 日志、secret 或本地绝对路径。
4. Chat session 已支持 list / detail / rename / delete，并只恢复用户可见消息。
5. Library 已支持托管上传、文档列表与详情；Markdown、PDF、DOCX、PPTX 能进入现有同步流程。
6. Question 支持结构化 `Attribution + SourceRef`，旧 SQLite 数据可迁移，出题来源由 RAG chunk 确定性保留。
7. Practice 已支持 session detail、attempt、progress、active list 和 abandon；Review 已聚合到期概念、错题和薄弱点。
8. Web Agent 使用学习 / RAG / memory 工具白名单；文件写入、任意 HTTP、MCP 与 specialist 不进入 Web MVP 运行时。

仍待 P5D / P5F 解决：

- React 前端、真实交互状态、Playwright 闭环测试尚未开始。
- 开发期仍是 Vite + FastAPI 两个进程；单进程静态托管与一键启动留到发布阶段。
- MCP / specialist 要等请求级 ToolContext 完成后，才能考虑在 Web Workbench 中开放。

### 3.4 优化原则

- 以“用户完成一次学习闭环”为进度单位，不以页面或模块数量为进度单位。
- 服务器端存储是学习状态真相源；浏览器只保存草稿、当前页面和 session 指针。
- 来源必须是结构化数据，不能让前端从自然语言回答里猜引用。
- 主流程只保留 Chat、Practice、Review、Library；Today 作为 Chat 的起始状态，Roadmap 后补。
- MCP、specialist、trace、模型切换继续保留，但不阻塞 Web 学习 MVP。
- 新增代码优先扩展现有 service，不创建重复的前端业务层或第二套学习逻辑。

## 4. 推荐技术路线与执行计划

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
- UI：Tailwind CSS + shadcn/ui 基础组件，强制映射 `docs/DESIGN.md` tokens。
- 路由：React Router。
- 数据请求：第一版使用原生 `fetch`；POST 流式回答使用 `ReadableStream` 解析 SSE frame，不使用原生 `EventSource`。
- 状态：服务端数据留在 API / domain；前端先用 React state + 小型 context，不提前引入复杂全局状态框架。
- 开发模式：Vite dev server + FastAPI，Vite proxy `/api`。
- 发布模式：Vite production build 由 FastAPI 托管静态文件，一个本地进程启动。
- 运行边界：默认只绑定 `127.0.0.1`，按单用户本地应用设计，本阶段不做登录和多租户。
- 保留现有 SQLite、Qdrant、JSON / Markdown 存储，不进行无收益的数据层重写。

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

#### P5D.1 前端地基

- 建立 `web/frontend`、路由、Vite proxy 和 API client。
- 落地 `DESIGN.md` tokens、字体和核心组件。
- Today 作为 Chat 无活动会话时的起始状态，不单独搭第二套首页。
- 第一批真实入口只开放 Chat、Practice、Review、Library；没有数据的入口显示“导入资料 / 开始对话”等可执行空状态，不放假按钮。

#### P5D.2 最小 Library 与资料导入

- 上传 Markdown、PDF、DOCX、PPTX，显示导入和索引状态。
- 展示文档列表、基础元数据和可读错误，不先做全文编辑、highlight 或大图谱。
- 选择一份或一组资料作为 Chat / Practice 的学习范围。

#### P5D.3 Chat 纵向切片

- 会话列表、主对话区、composer、流式回答、状态反馈、来源 chip。
- 新建、恢复、重命名、删除会话。
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

P5D 验收：

- 新用户能完成“导入资料 → 提问 → 查看来源 → 生成 5 题 → 做题 → 查看批改 → 进入复习”。
- 关键流程全部使用真实后端数据，无 mock 业务数据。
- Chat → Practice → Review 至少有一条 Playwright 端到端测试。

### P5E：可信资料扩展

在本地资料闭环稳定后，再补用户已确认的联网资料流程：

1. 本地资料不足时明确提示，不静默联网。
2. 用户确认后搜索，并先展示候选网页标题、域名和摘要。
3. 用户确认来源后再生成回答或题目。
4. 网页内容保存来源 URL、访问时间和引用片段。
5. 无可靠来源时只能标记为 `AI 补充` 或 `待核实`。

验收：

- 用户能区分本地资料、网页来源、AI 补充和待核实。
- Web 搜索失败不会阻塞本地资料问答与练习。
- 不允许把搜索摘要或 AI 常识伪装成用户资料。

### P5F：支撑页面与发布收尾

按优先级补齐：

1. Library 增强：文档阅读、highlight、摘录回流和相关概念；基础导入与列表已在 P5D 完成。
2. Roadmap：学习目标、当前阶段和今日任务。
3. Memory Browser：查看、编辑、删除、固定；用户人设配置后置于此。
4. Workbench：只提供必要的设置和状态入口，Agents / MCP / Logs 继续低权重。

发布门槛：

- `npm run build` 和后端全量测试通过。
- FastAPI 能托管 frontend build，一个命令启动本地应用。
- API 错误、空知识库、无来源、provider 未配置和流中断都有明确恢复动作。
- 桌面与移动端 Chat / Practice / Review 完成截图复核，符合 `docs/DESIGN.md`。
- 键盘操作、焦点状态、基础可访问性和文本溢出通过检查。

### 本轮明确不做

- 完整 Agent / MCP / Logs 管理后台。
- 独立 Canvas 产品、复杂知识图谱和完整知识编辑器。
- 模拟考试、限时训练、复杂题型和完整能力模型。
- 多用户 SaaS、跨设备同步、移动端原生 App。
- 插件市场、班级协作、排行榜或社交分享。

## 5. 练习系统产品决策

本节记录后续练习系统的产品决策。它是规划，不代表 Web 端已经实现。实现时按这里收口，不重新发散成传统题库后台。

### 5.1 产品位置

练习是和对话并列的主页面，但交互要像对话一样自然。

长期 Study 导航：

```text
Today
Chat
Practice
Review
Library
Roadmap
```

Web MVP 一级导航只开放 Chat、Practice、Review、Library；Today 复用 Chat 起始状态，Roadmap 后补。

页面边界：

- Today：低压问候、记忆提示和 2-3 个学习动作，与 Chat 共用主学习画布。
- 对话页：开放式学习问答。
- 练习页：结构化训练，一题一卡。
- 复习页：今日到期知识点、错题和薄弱点。
- 资料页：资料树、阅读内容、来源和相关概念。
- 路线页：学习目标、当前阶段和今日任务。

### 5.2 练习页形态

第一版采用 **一题一卡**，不做题库列表优先，也不把所有题目混在聊天气泡里。

推荐结构：

```text
顶部：本轮练习信息
中间：当前题目卡片
下方：选项 / 输入答案
提交后：即时批改 + 简短解释
右侧：来源、知识点、掌握度变化、下一步建议
```

### 5.3 题目来源

题目来源策略：

1. 用户资料优先。
2. 用户资料不足时，提示用户确认后联网搜索补充资料。
3. AI 可以补充，但必须清楚标注。

来源标签：

| 标签 | 含义 |
|---|---|
| 本地资料 | 题目或结论直接基于用户导入资料 |
| 本地扩展 | 围绕用户资料推导或扩展，但不是资料原文直接结论 |
| 网页来源 | 本地资料不足，经用户确认后联网搜索并基于网页资料生成 |
| AI 补充 | 不直接来自资料或联网来源，作为拓展练习 |
| 待核实 | 当前证据不足或来源尚未确认，不能按确定事实展示 |

联网策略：

- 默认不自动联网。
- 当本地资料不足时提示用户确认。
- 用户确认后再联网搜索资料并生成题目。

示例提示：

```text
本地资料不足，暂时只能生成 3 道题。
是否联网搜索资料，补充生成更多练习？
[联网补充] [只用本地资料]
```

### 5.4 批改与解释

提交答案后先给简短解释，用户需要时再展开追问。

答对示例：

```text
答对了。
简短解释：Dijkstra 适用于非负权图，因为每次确定当前最短距离后不会再被更短路径更新。

[展开讲解] [为什么其他选项不对] [再来一道类似题] [加入复习]
```

答错示例：

```text
答错了，正确答案是 B。
你可能混淆了“贪心选择”和“动态规划状态转移”。

[讲一下这个知识点] [看来源] [再练一道] [加入复习]
```

### 5.5 当前题目追问

练习页保留“追问 AI”，但只围绕当前题目和相关知识点，不嵌完整聊天窗口。

推荐快捷追问：

- 为什么 A 不对？
- 用更简单的话讲。
- 举个例子。
- 回到原文位置。

边界提示：

```text
这个问题只会围绕当前题目和相关知识点回答。
想换主题，请回到对话页。
```

### 5.6 题型范围

第一版只做：

- 单选。
- 判断。
- 简答。

后续再加：

- 多选。
- 填空。
- 材料题。
- 编程题。
- 拖拽 / 连线。
- 拍照搜题。

### 5.7 练习模式

第一版做三种模式：

| 模式 | 用途 |
|---|---|
| 按资料练 | 刚导入一份资料后，围绕这份资料练习 |
| 按薄弱点练 | 根据错题和掌握度，练用户薄弱知识点 |
| 今日复习 | 按复习计划练今天到期的知识点 |

后续再加：

- 错题重练。
- 章节练习。
- 模拟考试。
- 限时训练。
- 收藏题。
- 专项训练。

### 5.8 练习沉淀

每轮练习结束后，第一版沉淀：

- 分数 / 正确率。
- 新增错题。
- 掌握度变化。
- 推荐复习。

结束页示例：

```text
本轮练习完成

正确率：7/10
新增错题：3
掌握度提升：2 个知识点
需要复习：Dijkstra、堆排序
建议下一步：再练 5 道「最短路径」题

[继续练薄弱点] [加入今日复习] [导出到 Obsidian] [回到对话问老师]
```

后台沉淀：

- `quiz_attempts`
- wrong answer book
- mastery update
- review schedule
- daily memory / learning log

### 5.9 对话页与练习页跳转

练习页可以带着当前题目上下文跳到对话页，请教完再回到练习。

体验示例：

```text
当前题目卡片
[问问 AI 老师]
```

进入对话页时带上下文：

```text
我正在做这道题，帮我解释一下但不要直接给答案。
```

对话页顶部显示：

```text
来自练习：最短路径算法 · 第 3 题
[回到练习]
```

### 5.10 难度策略

练习系统支持三档难度：

- 基础：概念识别、定义、事实判断。
- 标准：理解、比较、原因分析。
- 挑战：应用、迁移、综合解释。

默认使用自动难度：

- 薄弱点先出基础 / 标准题。
- 掌握较好后出挑战题。
- 用户也可以手动选择基础 / 标准 / 挑战。

### 5.11 考试模式

第一版不做正式考试模式，只做学习型练习。

第一版练习模式允许：

- 即时批改。
- 查看解释。
- 追问 AI。
- 加入复习。

考试模式后续再加：

- 限时。
- 不显示解释。
- 交卷后统一解析。
- 生成考试报告。

### 5.12 练习入口

练习可以从四个入口开始，但必须统一进入同一个创建练习流程，不要每个入口各写一套逻辑。

入口：

| 入口 | 场景 |
|---|---|
| 对话页 | 从一次解释或回答生成练习 |
| 资料页 | 围绕某份资料练习 |
| 复习页 | 开始今日复习 |
| 练习页 | 自由选择范围开始练习 |

统一流程：

```text
入口
→ 创建练习
→ 选择范围 / 题量 / 题型 / 难度
→ 开始一题一卡练习
```

### 5.13 创建练习参数

第一版创建练习时提供轻量参数，不做复杂组卷后台。

题量：

```text
[5题] [10题] [15题]
```

- 默认：5 题。
- 第一版不做任意自定义题量。

题型：

```text
[x] 单选
[x] 判断
[x] 简答
```

- 默认全选，由系统自动混合。
- 用户可只选择某一种或某几种题型。
- 如果用户全不选，自动恢复全选。

难度：

```text
[自动] [基础] [标准] [挑战]
```

- 默认：自动。
- 用户可手动切换基础 / 标准 / 挑战。

自动难度策略：

```text
薄弱点 → 基础 / 标准
普通资料练习 → 标准为主
已掌握知识点 → 标准 / 挑战
```

### 5.14 联网资料确认

当本地资料不足且用户确认联网后，第一版不要让系统静默挑来源。

流程：

```text
本地资料不足
→ 提示是否联网
→ 搜索资料
→ 展示候选来源
→ 用户勾选
→ 基于选中来源生成题目
```

候选来源展示示例：

```text
搜索到这些资料：
[x] 官方文档 / 教材页面
[x] 百科 / 公开资料
[ ] 论坛 / 博客 / 问答

[用选中资料生成题目]
```

每道联网题必须显示：

```text
来源：网页来源
引用：网页标题 + 链接
```

### 5.15 简答题批改

简答题第一版用三档判断，不做百分制评分。

三档：

- 正确。
- 部分正确。
- 需要复习。

反馈格式：

```text
结果：部分正确
理由：你说到了“非负权”，但没有说明为什么每次选择当前最短点是安全的。
建议：复习“贪心选择性质”。
```

掌握度映射：

```text
正确 → mastery up
部分正确 → slight up / remain learning
需要复习 → needs_review
```

### 5.16 能力模型策略

长期要做完整能力模型，但第一版不要把完整算法放进 MVP。

第一版策略：

- 数据结构预留能力模型字段。
- 计算逻辑先简化。
- 后续再升级完整能力模型。

第一版建议保存：

- `concept_id`
- `question_id`
- `difficulty`
- `question_type`
- `result`：`correct` / `partial` / `needs_review`
- `score_bucket` 或 `confidence`
- `answered_at`
- `source_type`
- `time_spent`
- `hint_used`
- `followup_asked`

第一版计算：

```text
mastered / learning / needs_review
```

后续升级：

- 能力分。
- 遗忘曲线。
- 题型维度。
- 难度校准。
- 个性化出题。

### 5.17 错题与复习计划

错题自动进入复习计划，但用户可以移除或改为稍后复习。

规则：

```text
答错 / 简答需要复习
→ 自动进入复习计划
→ 结束页展示“已加入复习”
→ 用户可点 [移除] [改为稍后复习]
```

复习来源标签：

- 错题。
- 薄弱点。
- 手动加入。
- 学习计划。

今日复习来源：

- 错题自动加入。
- 简答“部分正确 / 需要复习”加入。
- 掌握度低的薄弱点加入。
- 到期复习知识点加入。
- 用户手动加入。

复习页显示示例：

```text
Dijkstra 算法
来源：错题 + 到期复习
建议：先做 3 道基础题
```

### 5.18 Obsidian 写回

第一版不要每轮练习自动写回 Obsidian，避免污染 vault。

策略：

- 练习结束后提供手动导出。
- 今日总结可以提示生成。

练习结束页：

```text
[导出本轮总结到 Obsidian]
```

今日复习完成后：

```text
今天完成了 12 道题，要不要生成今日学习总结？
[生成总结] [不用]
```

建议写回位置：

```text
学习记录/
  2026-07-09.md

错题整理/
  Dijkstra.md
```

不要每道题都写一个文件。

### 5.19 练习状态恢复

第一版要支持本地恢复当前练习状态，不做跨设备同步。

状态真相源：

- `quiz_sessions`、`quiz_attempts` 和题目数据保存在本地后端 SQLite。
- 前端不得维护一份独立的完整练习副本。
- 浏览器只保存 `practice_session_id`、当前界面位置和未提交草稿；恢复时重新请求后端 session detail。

后端练习状态应包含：

- `practice_session_id`
- 题目顺序和当前进度。
- 已答 / 未答题目。
- 用户答案和批改结果。
- 当前题追问记录。
- `started_at`
- `updated_at`
- `completed_at`

用户回来时提示：

```text
你有一轮未完成练习：数据结构 · Dijkstra · 已完成 4/10
[继续练习] [放弃本轮]
```

### 5.20 练习系统 MVP 范围

第一版要做学习闭环 MVP，不做薄 demo，也不做完整刷题中心。

MVP 必须跑通：

```text
创建练习
→ 一题一卡
→ 答题批改
→ 简短解释
→ 当前题追问
→ 更新错题 / 掌握度 / 复习计划
→ 练习结束小结
→ 可恢复未完成练习
```

明确不做：

- 完整错题页。
- 章节练习。
- 模拟考试。
- 限时训练。
- 收藏题。
- 周报 / 月报。
- 完整能力模型计算。
- 跨设备同步。
- 复杂题型。

### 5.21 下一阶段实现顺序

实现顺序以第 4 章为唯一执行路线，本节不再维护第二份重复计划。

```text
P5C 产品化基础
→ P5D 本地学习闭环 Web MVP
→ P5E 可信资料扩展
→ P5F 支撑页面与发布收尾
```

P5C 是进入前端开发前的硬门槛。任何阶段都不能只交付静态占位页；进入下一阶段前，当前阶段的验收条件必须成立。

## 6. 功能分层

### 一等功能

这些应该出现在主流程里：

- AI 对话。
- 上传或同步资料。
- 基于资料问答。
- 来源引用。
- 生成练习题。
- 做题与批改。
- 今日复习。
- 学习进度。
- Obsidian 导入 / 导出。

### 二等功能

这些保留，但默认隐藏在高级设置、调试页或内部实现里：

- RAG 模式选择。
- Qdrant / SQLite / FTS5 细节。
- MCP。
- Trace。
- Specialist。
- Skills。
- Model provider 切换。
- Graph query 原始命令。
- Memory promotion。

### 暂不做

这些方向容易稀释定位：

- 多用户 SaaS。
- 插件市场。
- 移动端 App。
- 复杂图谱可视化。
- 通用 Agent 平台。
- 更多 specialist。
- Neo4j 深度产品化。
- 社交分享 / 班级协作。
- 大规模 OCR。
- 过早官网营销页。

## 7. 架构边界

顶层分层：

```text
UI Layer
  CLI / React Web UI

Web Protocol Layer
  FastAPI routers / Pydantic DTO / event adapter

Runtime Composition Layer
  config / provider / prompts / tool catalog / trace / optional extensions

Service Layer
  service/learning_service
  service/quiz_service
  service/memory_service
  service/kb_service
  service/agent_service

Agent Runtime Layer
  core / providers / session / event stream

Tool & Extension Layer
  tools / skills / MCP

Knowledge Layer
  rag / graph / wiki / knowledge

Learning Layer
  quiz / learning / review / mastery

Memory Layer
  memory / daily memory / permanent memory / FTS5

Storage Layer
  .knowledge / .bobodan / .session / Obsidian vault
```

核心规则：

- `core/` 只管 Agent 运行，不管具体学习业务。
- `providers/` 只管模型调用。
- `tools/` 只做 Agent 能力入口，不承载复杂业务状态。
- `service/` 是 CLI 和 Web API 的业务入口。
- Runtime Composition 只负责装配，不复制 service 或 domain 逻辑。
- `web/backend` 只负责 HTTP、DTO、事件过滤和依赖注入。
- `web/frontend` 只负责呈现与交互，不能从自然语言文本反推业务状态。
- `rag/` 管检索、切块、embedding、vector store。
- `knowledge/` 管知识库状态、manifest、导入报告和统计。
- `quiz/` 管题库、练习、批改、错题。
- `learning/` 管学习路径、掌握度、复习。
- `memory/` 管用户长期上下文，不替代知识库。
- `cli/` 和 `web/` 只负责交互，不写核心业务。

依赖方向：

```text
React UI -> FastAPI Web Protocol
CLI -> Runtime Composition / service
FastAPI Web Protocol -> Runtime Composition / service
Runtime Composition -> core/providers/tools/skills/memory/MCP/agents
service -> domain modules
tools -> service/domain modules
core -> providers/tools/session
learning -> quiz/knowledge/graph/memory
quiz -> rag/knowledge
knowledge -> rag/graph
rag -> parsers/embeddings/vector stores
```

禁止方向：

```text
React UI -> core/domain/storage
FastAPI router -> direct SQLite business queries
domain modules -> cli
domain modules -> web
providers -> tools
rag -> quiz
rag -> learning
knowledge -> cli
memory -> cli
```

实现原则：

- 跨域聚合优先扩展现有 service；只有 Today / Review 这类确实跨越 quiz、learning、memory 的场景才增加小型 facade。
- 不为每个页面创建一套 backend service。
- 不建立泛化 repository、event bus 或微服务；当前是单进程本地应用。
- MCP / specialist 接入 Web 前必须改为请求级上下文，不能捕获某个 CLI session 的全局闭包。

## 8. 数据边界

`.knowledge/`：

- 运行时知识库。
- 包含 SQLite、Qdrant、manifest、sync state、import report 等。
- 可删除后重建。

`.bobodan/`：

- 不可从索引重建的本地用户数据。
- 包含 permanent memory、daily memory、trace、memory db，以及 Web 上传资料的托管副本目录 `sources/`。
- 不应随便删除。

`.bobodan/sources/`：

- 保存通过 Web 上传的原始资料副本，是托管资料的 truth source。
- `.knowledge/` 只保存它们生成的索引；重建索引时不能删除这里的文件。
- 外部 Obsidian vault 不复制时，vault 本身继续作为 truth source。

`.session/`：

- 会话历史。

浏览器存储：

- 只保存 UI 偏好、草稿、最近的 `chat_session_id` / `practice_session_id`。
- 不保存知识库真相、完整练习记录、掌握度或长期记忆副本。

来源数据：

- `Attribution + SourceRef` 是 Chat、Practice、Review 共用的可信来源边界。
- 本地来源保存文档 / chunk 标识和可读定位；网页来源保存 URL 和访问时间。
- 本地绝对路径只在服务端保存，前端只接收可展示标题、source id 和定位信息。
- `AI 补充` 与 `待核实` 不是引用来源，必须作为独立归因状态保留。

标识命名：

- 对话统一使用 `chat_session_id`，保持 UUID。
- 练习统一使用 `practice_session_id`，可继续使用 SQLite integer id。
- API 和前端不得都简称为 `session_id`，避免跨页面传错。

Obsidian vault：

- 用户原始资料和可读输出目标。
- 原始资料是 truth source。
- wiki 页面是编译层。
- `.knowledge/` 是运行时索引。

## 9. 新功能判断

新增功能前先问：

1. 它是否让对话入口更好用？
2. 它是否直接改善学习闭环？
3. 它是否能把用户资料转化为更可信的回答、练习或复习？
4. 它是否会迫使普通用户理解底层技术名词？

如果一个功能只服务工程可玩性，而不服务前三点，就应该降级、隐藏或暂缓。

## 10. 常用专题文档

日常只需要读本文。需要深入时再看：

- `docs/DESIGN.md`：Web / TUI / 官网视觉硬约束。任何界面设计开工前必须先读。
- `docs/rag_design.md`：RAG v2 详细设计。
- `docs/MCP.md`：MCP 客户端使用。
- `docs/tools/skills.md`：Skills 系统说明。

## 11. 最终结论

Bobodan 后续应该避免做成“知识库后台 + 聊天框”，也不要走向“万能 Agent 工具箱”。

它应该成为：

> 一个像 ChatGPT / Gemini 一样自然的 AI 对话主页，但默认懂用户的本地资料，并能把每次对话沉淀为练习、复习、学习计划和长期进度。
