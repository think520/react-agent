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

主界面分成 **Study** 和 **Workbench** 两组。

Study 是一等入口：

```text
Today
Chat
Practice
Review
Library
Roadmap
```

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

## 3. 当前阶段

当前阶段已经收尾。

已完成：

- ReAct AgentLoop + 多 Provider + 多模型切换。
- tools / skills / memory。
- RAG v2：SQLite + FTS5 + Qdrant + hybrid / directory / grep retrieval。
- quiz / learning / review / mastery。
- Obsidian 写回：学习计划 + 做题总结。
- Event Trace：JSONL trace + `/trace` 命令。
- MCP client：stdio / SSE / streamable_http。
- Learning Agent Orchestrator v1：`doc_reader` / `triage` / `planner`。
- CLI Tool Display UX。
- Service 层：`learning_service` / `quiz_service` / `memory_service` / `kb_service` / `agent_service`。
- FastAPI skeleton：`web/backend` 路由、SSE 事件流、service 协议转换和 Web API 测试。

验证状态：

- 最近一次全量测试：`998 passed`，2 个既有 warning。
- 当前结论：P0-P4 完成，P5 前置 service 层和 FastAPI skeleton 完成。

当前阶段：

> FastAPI skeleton 已完成。下一步做 chat-first Web shell：左侧导航 + 对话页 + 练习页占位。

## 4. 下一步路线

### P5B：FastAPI skeleton（已完成）

目标：接已完成的五个 service，跑通 Web 所需的 HTTP 和 SSE 事件流。

建议目录：

```text
web/backend/
  app.py
  routers/
    chat.py       # /api/chat/runs, /api/chat/runs/{id}/events
    kb.py         # /api/kb/*
    quiz.py       # /api/quiz/*
    learning.py   # /api/learning/*
    memory.py     # /api/memory/*
    settings.py   # /api/settings/*
```

原则：

- FastAPI 路由只做协议转换。
- 业务逻辑继续放在 `service/`。
- SSE 优先，WebSocket 后置。
- 不在 API 层重写 `core/`、`tools/`、`learning/`、`memory/`。

验收：

- 能启动本地 FastAPI app。
- 能创建 chat run。
- 能通过 SSE 收到 agent event。
- 能调用知识库、题库、学习、记忆和设置相关 service。

当前实现：

```text
web/backend/
  app.py
  deps.py
  sse.py
  routers/
    chat.py
    kb.py
    quiz.py
    learning.py
    memory.py
    settings.py
```

运行方式：

```powershell
.\.venv\Scripts\python.exe -m uvicorn web.backend.app:app --reload
```

### P5C：Web Chat MVP

目标：先做一个能用的对话主页，而不是完整后台。

建议目录：

```text
web/frontend/
  src/
    pages/
    components/
    hooks/
    api/
```

第一版页面：

- 对话主页。
- 左侧会话列表。
- 右侧学习上下文。
- 资料库入口。
- 今日复习入口。

验收：

- 用户打开 Web 后第一眼知道“这是一个 AI 对话工具”。
- 用户可以在对话里问学习问题，并看到来源。
- 用户可以从一次回答继续生成题目或复习项。
- 用户不需要理解 RAG / MCP / specialist。

## 5. 练习系统产品决策

本节记录后续练习系统的产品决策。它是规划，不代表 Web 端已经实现。实现时按这里收口，不重新发散成传统题库后台。

### 5.1 产品位置

练习是和对话并列的主页面，但交互要像对话一样自然。

主导航建议：

```text
对话
练习
复习
资料
进度
```

页面边界：

- 对话页：开放式学习问答。
- 练习页：结构化训练，一题一卡。
- 复习页：今日到期知识点、错题和薄弱点。

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
| 来自我的资料 | 题目直接基于用户导入资料 |
| 基于我的资料扩展 | 题目围绕用户资料扩展 |
| 来自联网资料 | 本地资料不足，经用户确认后联网搜索并基于网页资料生成 |
| AI 补充 | 不直接来自资料或联网来源，作为拓展练习 |

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
来源：来自联网资料
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

练习中保存：

- `practice_session_id`
- 当前第几题。
- 已答题目。
- 未答题目。
- 用户答案。
- 批改结果。
- 当前题追问记录。
- `started_at`
- `updated_at`

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

下一阶段从 Web shell 开始，但 Web MVP 从一开始按 **对话 + 练习双主线** 规划，分阶段实现。

不要先只做聊天壳，也不要先做完整练习系统。

推荐顺序：

```text
1. FastAPI skeleton（已完成）
2. Web shell：左侧导航 + 对话页 + 练习页占位
3. 对话页 SSE 跑通
4. 练习创建流程 + 一题一卡
5. 批改 / 解释 / 追问 / 沉淀
6. 再补资料页、复习页、进度页
```

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
  CLI / future Web UI

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
- `rag/` 管检索、切块、embedding、vector store。
- `knowledge/` 管知识库状态、manifest、导入报告和统计。
- `quiz/` 管题库、练习、批改、错题。
- `learning/` 管学习路径、掌握度、复习。
- `memory/` 管用户长期上下文，不替代知识库。
- `cli/` 和未来 `web/` 只负责交互，不写核心业务。

依赖方向：

```text
UI -> service/core
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
domain modules -> cli
providers -> tools
rag -> quiz
rag -> learning
knowledge -> cli
memory -> cli
```

## 8. 数据边界

`.knowledge/`：

- 运行时知识库。
- 包含 SQLite、Qdrant、manifest、sync state、import report 等。
- 可删除后重建。

`.bobodan/`：

- 个性化数据。
- 包含 permanent memory、daily memory、trace、memory db。
- 不应随便删除。

`.session/`：

- 会话历史。

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
