# Bobodan 项目指南

这份文档是 Bobodan 后续给人和 AI 看的产品与架构主入口。想知道产品是什么、当前到哪一步、哪些功能该隐藏、代码边界怎么守，先读这里；具体排期只看 [`ROADMAP.md`](ROADMAP.md)，视觉和交互硬约束只看 [`DESIGN.md`](DESIGN.md)。

> 事实基准：§1–§3、§5–§9 是当前产品边界与架构说明；§4 保留当前生效的桌面发布验收要求（原 2026-08 之前的 P5C–P5G 历史阶段记录已移入 [`archive/PROJECT_GUIDE_PHASES_P5.md`](archive/PROJECT_GUIDE_PHASES_P5.md)）；常用命令、目录树与关键运行时契约已独立拆到 [`ARCHITECTURE_AND_CONTRACTS.md`](ARCHITECTURE_AND_CONTRACTS.md) 以便快速检索。
> 当前批次、门禁和下一步只看 [`ROADMAP.md`](ROADMAP.md)（v2.2，2026-11-20）；文档地图只看 [`docs/README.md`](README.md)（校验：2026-11-20）。
> 本文中的“已完成”表示阶段验收已通过，不代表后续体验轮不再发现问题。

## 1. 产品定位

Bobodan 是一个 **ChatGPT / Gemini 形态的个人学习 AI**。

用户从一个对话主页开始提问、上传资料、询问课程、生成练习和安排复习；系统在背后调用本地知识库、RAG、题库、掌握度、记忆和 Obsidian 能力，把每次对话沉淀成可追踪的学习进度。

它不是知识库后台，也不是通用 Agent 平台。知识地图、Wiki 维护和 Workbench 都是辅助能力，不能反过来成为普通用户的前置流程。

更准确地说：

> Bobodan 是一个 chat-first、local-first 的个人学习助手。主入口是自然对话，核心价值是基于用户自己的资料回答问题，并把对话转化为练习、复习和学习路径。

## 2. 第一屏应该是什么

Web 第一屏应该是 AI 对话主页，而不是 dashboard。

### 2.1 视觉硬约束

任何 Web UI、页面原型、组件、练习页、对话页、资料页、复习页、进度页、TUI 或官网设计，开工前必须先读 `docs/DESIGN.md`。

`docs/DESIGN.md` 不是可选参考，而是 Bobodan 的主题色、视觉气质和设计边界。后续设计必须沿用其中定义的 Natural Editorial Zen / Warm Paper Knowledge Garden 方向，以及暖纸色、墨蓝、植物绿、原木色、橘棕、花瓣粉等主题色。

不要临时发明一套新颜色，也不要做通用 SaaS dashboard 风格、紫色 AI 渐变风格或高密度后台风格。若实现中需要新增 token，必须从 `docs/DESIGN.md` 的色彩系统延展。

推荐结构（右侧只在有真实上下文时展开，空状态可收起）：

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
| 安静桌面工作区 | [OpenHanako](https://github.com/liliMozi/openhanako) | 三栏工作区、角色化欢迎页、工作空间与记忆状态、右侧书桌/便笺、纸面 Token；不吸收办公 Agent 的频道和社交入口 |
| LLM Wiki | [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) | 原始资料只读、Schema 约束、两阶段 Wiki 生成、安全增量合并、任务队列、来源依赖和结构 / 语义检查；不吸收自动摄入与知识库后台定位 |

#### 2.2.1 OpenHanako 借鉴边界

OpenHanako 与 Bobodan 都受到 Kami 纸面美学影响，适合作为 Web 工作区结构参考，但产品目标不同：OpenHanako 是通用私人 Agent，Bobodan 必须保持学习助手定位。

以下是 P5D 阶段的首要借鉴项，现已成为既有工作区结构；当前优先级以 [`ROADMAP.md`](ROADMAP.md) 为准：

| 借鉴点 | Bobodan 的实现方式 |
|---|---|
| 三栏工作区 | 左侧会话 / 学习空间，中间 Chat 主画布，右侧可折叠学习上下文；窄屏只保留主画布，左右栏改为抽屉 |
| 角色化欢迎页 | Today 复用 Chat 空状态，显示 Bobodan 小猫、“今天想学什么？”、当前学习空间、记忆状态和 2-3 个真实学习动作 |
| 工作空间绑定 | 一个学习空间绑定课程或项目、资料范围、聊天、笔记、练习记录和学习记忆，不把文件夹概念直接暴露给普通用户 |
| 右侧书桌 / 便笺 | 转化为“资料 / 学习笔记”上下文面板；根据任务切换来源、相关知识点、当前题目和解析，不固定显示后台信息 |
| Composer | 支持附件、资料范围、引用选中文字和短学习动作；模型、工具和推理等级保持低视觉权重 |
| 纸面设计系统 | 使用本地字体、暖纸 Token、轻纹理、小圆角、细分隔和短时动效；以 `docs/DESIGN.md` 为唯一色彩与排版标准 |

以下是当时列为 P5F.1 / P5G 或学习闭环稳定后再补的事项；是否继续实施及其顺序以 [`ROADMAP.md`](ROADMAP.md) 为准：

- 会话正文搜索、归档与恢复。
- 可查看和管理的学习记忆，明确区分用户画像、长期目标、课程进度、错题薄弱点和临时上下文。
- 复习提醒与定时学习任务，把通用 Cron 转化为间隔复习和阶段总结。
- 可导入、导出的教学人设或学习技能包；Bobodan 三花猫仍是固定品牌形象。
- 桌面端与移动 PWA 共享同一套会话、资料和练习身份，避免前端各自复制数据。

明确不照搬：

- 不把频道、社交平台、多 Agent 协作放进 Web MVP 一级导航。
- 不把多个角色选择器放在默认首页；用户人设属于配置层，Bobodan 小猫属于品牌层。
- 不长期固定展开右侧面板，也不在右侧堆叠 Todo、Workflow、Logs 等 Agent 控制卡。
- 不照搬过低对比度文字、过量空白、嵌套卡片和大面积胶囊按钮；阅读可访问性优先。
- 不提前建设主题画廊、插件市场、角色卡市场和完整自动化后台。
- 可以借鉴结构和交互思想；若直接复用 OpenHanako 代码，必须遵守其 Apache-2.0 许可证并保留必要声明，不复制其角色与品牌资产。

#### 2.2.2 OpenHanako 系统级参考

前面的三栏布局只是表层参考。后续实现还应持续检查 OpenHanako 在过程披露、配置、记忆、会话恢复、权限和扩展边界上的做法，但只吸收适合学习产品的部分。

##### 思考与任务过程

OpenHanako 将思考、工具组、子任务和工作流分别建模，并采用“聊天中显示摘要、按需展开详情、复杂流程放右侧面板”的渐进披露。Bobodan 采用相同的信息层级，但不得把模型原始思维链直接展示给用户。

Bobodan 的用户可见过程统一为：

```text
理解问题
→ 检索已选择的本地资料
→ 必要时请求联网确认
→ 对比来源并检查冲突
→ 组织回答 / 生成练习
→ 完成、失败或等待用户操作
```

规则：

- Chat 默认只显示一句过程摘要，例如“正在检索 3 份课程资料”。
- 展开后显示资料、工具、耗时、成功/失败与重试动作，不显示未经整理的内部推理文本。
- 多个同类工具调用自动归组；已经有来源卡、练习卡或设置回执承载结果时，不重复显示底层工具行。
- 复杂任务在聊天流中只保留静态概览，实时步骤放入右侧上下文面板。
- 面向普通用户提供“简洁 / 标准 / 深入”的回答深度，不直接暴露模型 thinking budget 名称。

参考实现：[ThinkingBlock](https://github.com/liliMozi/openhanako/blob/main/desktop/src/react/components/chat/ThinkingBlock.tsx)、[ProcessFoldBlock](https://github.com/liliMozi/openhanako/blob/main/desktop/src/react/components/chat/ProcessFoldBlock.tsx)、[ToolGroupBlock](https://github.com/liliMozi/openhanako/blob/main/desktop/src/react/components/chat/ToolGroupBlock.tsx)。

##### 首次配置与应用设置

OpenHanako 的首次流程依次处理语言、用户/助手名称、Provider、模型、主题和工作区；模型又区分 chat、utility、utility_large、embedding 与视觉能力。Bobodan 保留职责分工，但默认自动选择，避免把模型工程概念当成新用户门槛。

Bobodan 首次流程收敛为四步：

1. 语言、用户称呼和学习目标。
2. 连接 AI；提供推荐配置，高级用户再展开 Provider、Base URL 和模型职责。
3. 导入第一份资料或先跳过，并建立第一个学习空间。
4. 解释记忆、联网和本地数据边界，用户确认后进入 Chat。

长期设置结构：

| 设置组 | 内容 |
|---|---|
| 我的资料 | 称呼、头像、个人介绍、长期目标 |
| 学习偏好 | 讲解方式、反馈强度、回答深度、练习偏好 |
| 记忆与隐私 | 记忆总开关、分层记忆、删除与导出、联网确认 |
| AI 与模型 | 推荐自动路由；Provider、模型职责和视觉模型放在高级区 |
| 资料与搜索 | 默认资料范围、联网搜索服务、来源策略 |
| 复习与通知 | 间隔复习、学习提醒、阶段总结 |
| 界面与阅读 | 主题、字体、字号、内容宽度、纸张纹理、减少动态效果 |
| 技能与集成 | Obsidian、Skills、MCP；默认折叠 |
| 安全与数据 | 权限模式、备份、归档、代理和本地数据位置 |

设置页必须支持搜索。用户也可以在 Chat 中提出“关闭记忆”“回答简短一点”等配置请求；系统显示修改前后值并要求确认。沙盒、文件删除、密钥、网络边界等敏感设置只能由用户在设置页操作，AI 不能代为开启。

参考实现：[配置模板](https://github.com/liliMozi/openhanako/blob/main/lib/config.example.yaml)、[设置搜索](https://github.com/liliMozi/openhanako/blob/main/desktop/src/react/settings/settings-search-index.ts)、[对话修改设置](https://github.com/liliMozi/openhanako/blob/main/lib/tools/update-settings-tool.ts)。

##### 人格与学习记忆

OpenHanako 将身份、人格、用户资料、置顶记忆、事实库、今日、近一周、长期记忆和经验分开。Bobodan 使用同样的可解释分层，但必须按学习场景重新命名并隔离：

| OpenHanako 概念 | Bobodan 对应 |
|---|---|
| identity / persona | 教学人设与表达方式，不覆盖品牌、安全和来源规则 |
| user profile | 用户画像、学习目标、背景和偏好 |
| pinned memory | 用户明确固定的目标、约束和重要事实 |
| facts | 稳定学习事实、课程信息和用户确认内容 |
| today / week / longterm | 今日学习、近期进度、长期学习轨迹 |
| experience | 对该用户有效的教学方法；默认关闭或谨慎写入 |

记忆必须按学习空间隔离，同时允许少量全局用户偏好跨空间共享。用户能查看、编辑、固定、删除和清空；界面显示记忆健康与最近更新时间。错题、掌握度和复习计划仍由结构化学习数据维护，不能只写进自然语言 memory.md。

参考实现：[记忆编译](https://github.com/liliMozi/openhanako/blob/main/lib/memory/compile.ts)、[置顶记忆](https://github.com/liliMozi/openhanako/blob/main/lib/memory/pinned-memory-store.ts)、[记忆设置](https://github.com/liliMozi/openhanako/blob/main/desktop/src/react/settings/tabs/agent/AgentMemory.tsx)。

##### 会话、资料与恢复

以下不是装饰功能，而是长期使用体验的基础：

- 会话标题优先搜索，必要时继续搜索正文；支持项目/学习空间分组、置顶、归档、恢复和永久删除。
- 输入草稿按首页或会话分别持久化，切换会话、刷新或短暂离线后不丢失。
- 流式回答支持断线续传与事件重放，刷新后能恢复已完成内容。
- 会话恢复前检查连续错误、上下文溢出和孤立工具结果，提供压缩、新会话或重试动作。
- 对话过长时使用结构化摘要压缩，保留目标、决策、文件、来源和未完成事项。
- 文件、资料、生成物和媒体使用稳定 resource id / source id，不把本地绝对路径当作前端身份。
- 资料具有版本或 revision；编辑前创建检查点，外部变化与本地未保存修改冲突时明确提示。
- 预览器保存阅读位置、当前标题、选区和编辑位置；选中文字可引用到 Chat。

这些能力优先借鉴协议与恢复逻辑，不要求 Bobodan 改用 Electron 或 JSONL。Python + FastAPI + SQLite 的现有技术路线保持不变。

参考实现：[会话健康](https://github.com/liliMozi/openhanako/blob/main/core/session-health.ts)、[断线续流](https://github.com/liliMozi/openhanako/blob/main/desktop/src/react/services/stream-resume.ts)、[资源引用](https://github.com/liliMozi/openhanako/blob/main/lib/resource-io/resource-refs.ts)、[输入草稿](https://github.com/liliMozi/openhanako/blob/main/desktop/src/react/stores/input-draft-persistence.ts)。

##### 权限、安全与自动化

- 借鉴 read-only / ask / auto / operate 的分层思想，Bobodan 面向用户简化为“只读”“每次询问”“允许当前学习空间”。
- 联网搜索、写回 Obsidian、删除资料、执行代码和修改长期记忆分别声明副作用，不用一个总开关包办。
- 敏感操作保留用户确认；自动审查不能扩大沙盒、可写目录或网络范围。
- 文件修改前检查点、备份保留期、恢复入口和脱敏安全审计进入发布门槛。
- 定时触发与 AI 执行分离：调度器负责“何时触发”，AI 只负责“生成什么内容”。
- 自动化优先转化为复习提醒、到期错题和阶段总结；默认不巡检任意本地目录。

参考实现：[会话权限](https://github.com/liliMozi/openhanako/blob/main/core/session-permission-mode.ts)、[路径权限](https://github.com/liliMozi/openhanako/blob/main/lib/sandbox/path-guard.ts)、[定时调度](https://github.com/liliMozi/openhanako/blob/main/lib/desk/cron-scheduler.ts)。

##### 技能、插件与工程结构

- Skill 可以组成“学习技能包”，按学习空间或教学人设启用、禁用、导入和导出。
- 教学人设包可以携带人格、头像和 Skills；记忆默认不随包导入，必须单独勾选和预览。
- 插件若后续实现，必须声明能力、网络域名、资源读写和配置 schema，并区分受限与完全访问。
- 后端继续使用现有 Python service 边界，但借鉴 Manager / facade、事件总线、稳定 DTO、schema version 和迁移机制。
- Provider 与模型使用稳定的 `provider + model id` 引用，不按裸模型名猜测；聊天、轻量任务、深度分析、embedding 和视觉模型可内部路由。
- 借鉴其测试纪律：过程 UI、会话恢复、Provider 兼容、权限、安全、插件 grant 和移动布局都要有针对性测试；不要只测 happy path。

OpenHanako 当前使用 Electron + React + Zustand + Hono，并拥有大量前端与契约测试。Bobodan 不复制技术栈，只把其成熟边界映射到 FastAPI + React 架构。

一句话：

> Bobodan 是看起来像高级纸质学习笔记本的 Agent Operating System，不是黑色终端风 Agent 控制台。

#### 2.2.3 LLM Wiki 可靠性参考

`nashsu/llm_wiki` 与 Bobodan 都把原始资料视为事实来源，并在原文之上维护可持续更新的 AI Wiki。Bobodan 只吸收其 Wiki 编译与可靠性机制，不改变 chat-first、learning-first 的产品定位。

优先借鉴：

- 将资料分析与文件生成拆成两个阶段；Bobodan 映射为 `wiki_focus → wiki_plan → wiki_result`，用户确认前不写文件。
- 在写入边界校验 Schema、目录、页面类型、frontmatter、来源引用和输出语言；失败内容进入 staging，不污染正式 Wiki。
- 增量更新时确定性合并 `sources`、标签和关系，锁定关键元数据，只让模型处理正文，并为异常缩减设置拒绝与回退规则。
- 使用可恢复的持久化任务队列处理批量资料、长 PDF、Wiki 计划和后续联网研究。
- 建立来源依赖与影响预览；资料变化或归档时先展示受影响页面，再由用户确认更新计划。
- 将孤立页、断链、缺失页等结构检查与矛盾、过时内容等 AI 语义检查分开，所有修复仍需确认。

明确不照搬：

- 上传资料后自动生成 Wiki；Bobodan 上传和同步只建立原文索引。
- 以 Wiki 编辑器、复杂图谱或知识库管理后台作为产品主入口。
- 为参考项目改写现有 Python + FastAPI + React 技术路线，或直接复制其 Tauri / Rust 架构。
- 直接复制 GPL-3.0 代码；只参考公开机制、数据边界和交互思想，若未来确需复用代码必须先完成许可证评估。

该项目已暴露过大型 Wiki 聚合文件截断、来源字段损坏、批量队列恢复和文件夹导入反馈不足等问题。Bobodan 必须让结构文件由程序维护、限制模型写入范围，并把失败恢复和规模化测试作为 P5E.2 门槛。

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

Web MVP 当时不一次开放六个一级导航，第一版主导航收敛为四项（历史记录；当前一级导航 6 项——对话 / 练习 / 复习 / 知识地图 / 笔记 / 资料库；校验：2026-10-28，web/frontend/src/components/shell/nav.ts:5-10）。

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

Bobodan 的长期知识分为三层，不能混为同一类记忆：

1. 原始资料：用户上传或同步的事实来源，AI 只读。
2. AI 整理 Wiki：从指定资料编译出的概念、实体和分析，明确标注 AI 整理并由用户确认写入。
3. 个人学习知识库：用户长期使用后形成的掌握度、错题、学习轨迹、个人总结、稳定偏好和已确认长期知识。

Memory 与个人学习知识库共同沉淀：

- 学习画像。
- 用户偏好。
- 长期人设 / 关系。
- 讲解方式偏好。
- Obsidian 写回偏好。
- 用户不喜欢的表达方式。
- 已掌握、学习中和需要复习的知识点。
- 用户确认的个人总结、观点、问题与跨资料发现。

确定性的做题、掌握度、阅读和复习事件可以自动记录；用户观点、长期结论、画像推断和个人总结只能先进入候选区，确认后才能成为长期知识。敏感画像、健康判断和人格推断默认不自动保存。

## 3. 全项目复盘结论

### 3.1 总体判断

Bobodan 已经完成“学习 Agent 引擎”“Web 产品化基础”“本地学习闭环 Web MVP”“便携文件夹资料库”“Web UI 系统体验与设置中心”“可信联网资料扩展”“个人学习知识库”和“知识地图”主体流程。旧 Wiki 整理能力保留在高级维护 / 历史整理边界，不再作为资料导入、Chat 检索或日常阅读的必经层。普通用户可以在浏览器中切换多个本地资料库，完成资料学习、个性化设置、用户确认式网页研究，以及可查看、确认、编辑和删除的长期个人知识沉淀。

现有技术路线不需要推倒重来。Python + FastAPI + SQLite / Qdrant + React Web UI 仍然适合本地优先的个人学习助手。P5C 已整理 Web 产品合约，P5D 已完成 Library → Chat → Practice → Review，P5E.1 已把测试工作区升级为通用文件夹资料库，P5E.3 已补齐用户偏好与设置中心，P5F 已补齐可信联网候选、证据快照和网页来源练习，P5F.1 已补齐确定性学习事件、候选确认和已确认个人知识，P5E.6 已实施知识地图产品重置。2026-07-26 审查整改进一步退役了旧 memory、JSON RAG、JSON / Neo4j graph 和 Wiki compiler 的正常运行路径。当前批次与发布阻塞项只看 [`ROADMAP.md`](ROADMAP.md) §1–§4（A0–A3 已于 2026-10 收口）。

一句话结论：

> **（2026-08 时的判断，后续进展见 ROADMAP.md）** 本地资料、可信联网证据与个人学习知识库已经形成闭环；知识地图已落地，下一步先核对并补齐学习闭环、导入与检索的真实缺口，再进入 Windows 桌面发布。

### 3.2 当前成熟度

| 模块 | 当前判断 | 说明 |
|---|---|---|
| Agent Runtime | 可用且测试充分 | ReAct、流式输出、工具调用、session、provider 已稳定运行 |
| RAG v2 | 较成熟 | SQLite / FTS5 / Qdrant / hybrid / directory / grep 已具备完整检索骨架；中文检索使用规范化文本与 CJK 2-gram，检索管线按 workspace / 配置缓存；扫描页和图片文字尚不会被识别，需要提取完整性报告避免静默漏读 |
| Quiz / Learning | Web 闭环可用 | 支持范围出题、错题误区变式、精确题目会话、题内问 AI、练习恢复、批改、SM-2 复习和 Review 聚合 |
| Memory | P5F.1 完成 | 全局 / 资料库双层 SQLite、确定性学习事件、候选确认、显式记忆卡、旧记忆迁移、Markdown 导出和请求级个性化已落地；旧 Markdown 仅供只读预览 / 导入，不再由正常运行时读写或注入 Prompt |
| Service Layer | 产品化基础完成 | CLI / Web 共用 runtime、config 与 service；统一成功 / 错误信封和结构化错误码已落地 |
| FastAPI | P5F.1 完成 | 已有稳定错误结构、流式事件、资料库隔离、Wiki / 联网证据、个人知识 CRUD、候选确认、阅读进度、旧记忆迁移和 Chat 记忆确认 API |
| Web UI | P5E.6 完成 | Chat、Library、Practice、Review、设置中心、个人知识管理、历史整理、成本控制和知识地图界面已落地；主页面使用路由级懒加载和应用级错误边界，桌面发布壳尚未实现 |
| 测试 | 全栈回归已建立 | Python、前端 lint、TypeScript 构建与 Vitest 均有回归命令；本轮最终数量以提交前验证结果为准，不在指南中固化易过期计数 |

### 3.3 P5C / P5D / P5E 已解决的问题与剩余边界

已解决：

1. CLI / Web 共用 runtime composition，统一 provider、workspace、skills、memory、trace 和 LLM service config。
2. `/api/chat/runs` 固定使用 POST + `fetch` / `ReadableStream` 消费 SSE，事件收敛为稳定 Web 协议。
3. Web 只接收白名单状态与 artifact，不暴露原始 tool output、specialist 日志、secret 或本地绝对路径。
4. Chat session 已支持 list / detail / rename / delete，并只恢复用户可见消息。
5. Library 已支持托管上传、文档列表与详情；Markdown、PDF、DOCX、PPTX 能进入现有同步流程。
6. Question 支持结构化 `Attribution + SourceRef`，旧 SQLite 数据可迁移，出题来源由 RAG chunk 确定性保留。
7. Practice 已支持 session detail、attempt、progress、active list 和 abandon；Review 已聚合到期概念、错题和薄弱点。
8. Web Agent 使用学习 / RAG / memory 工具白名单；文件写入、任意 HTTP、MCP 与 specialist 不进入 Web MVP 运行时。

P5D 已补齐：

- 四步首次配置、学习资料范围选择、选文带到对话、请求级资料范围约束和渐进式过程披露。
- Chat → Practice → Review 的完整学习闭环，以及不离开当前题目的轻量问 AI 抽屉。
- 生成题按本轮返回的题目 ID 精确创建练习，避免旧题混入当前会话。

P5E 已补齐：

- 从 Chat、资料页或已有 Wiki 主题发起生成 / 更新计划，支持当前范围、指定资料与课程范围。
- 计划阶段只保存新增、更新、合并、冲突和跳过草稿；用户确认前不写 Wiki。
- 确认后生成概念页 / 实体页、双向相关概念链接和原文定位，并重新同步 Wiki 索引。
- 写入前创建检查点，支持用户撤销；写入中途失败会自动恢复，不留下部分更新。
- 无指定范围的检索先使用 Wiki 理解结构，再以原始学习资料作为事实证据，并明确标记 AI 整理内容。

P5E.3 已补齐：

- 设置中心支持搜索、URL 深链接、桌面弹窗与移动全屏；用户偏好使用 revision 和原子 JSON 持久化。
- 新会话继承默认 Provider，已有会话保存自己的 Provider；失效模型明确标记，流式期间禁止切换并可停止生成。
- Composer 支持回答深度、`@资料 / @会话`、结构化引用 chip、Slash / Skills 过滤和正文流状态反馈。
- 用户可在确认卡中修改回答深度、教学方式、反馈强度和记忆开关；Provider、密钥、权限和安全边界不能通过对话修改。
- 全局连接异常使用轻量恢复条，正常状态不常驻；设置状态页只显示可理解状态和修复动作，不暴露内部日志。

P5F 已补齐：

- 本地证据不足时模型只能提出联网确认，不获得任意联网工具；用户确认、一次性联网或 `/web search` 才会发出外部请求。
- 搜索先展示最多 6 个候选且默认不勾选，用户选择 1–4 个来源后才读取正文；搜索摘要不进入回答证据。
- Tavily 与 Exa 支持手动选择和自动降级；直接读取失败时可使用明确标注的 Jina Reader 后备。
- 网页证据按资料库保存为不可变快照，并与 Chat、Question、Practice、Review 共用 `Attribution + SourceRef`。

P5F.1 已补齐：

- 做题、练习完成、复习、阅读和 Chat 整理以确定性学习事件保存，不再自动写入旧 daily Markdown。
- 用户观点、学习策略和课程结论只进入待确认候选；明确“请记住”使用 Chat 确认卡，秘密信息拒绝保存，敏感内容显示二次警告。
- 只有已确认知识和确定性掌握度摘要进入 Chat、Practice 和 Review；界面显示可展开的“个性化依据”。
- 设置中心“记忆与数据”可管理已确认知识、候选、学习记录与旧记忆迁移，并支持置顶、编辑、删除和 Markdown 导出。

当前仍待解决：

- PDF、DOCX 和 PPTX 只能读取已有文本层；扫描页、图片文字和零 chunk 资料已支持提取状态报告与阅读器显式提示（`W3-READER-01`），PDF 四级降级链（`W2-G5`）按真实样本需求暂缓。
- 发布许可证、第三方声明和隐私说明已存在；SBOM、安装包校验、字体分发条款和最终依赖许可证仍需在桌面发布前统一验收。
- FastAPI 静态托管和 `python agent.py web` 单进程 Web 已实现；PyInstaller sidecar、Electron 安装包、升级和卸载契约尚未实现。
- MCP / specialist 不进入首发 Workbench；只有请求级 ToolContext 和发布安全边界稳定后才重新评估。

### 3.3.1 2026-07-26 审查整改边界

本轮整改遵循“只保留一个正常运行真相源，旧数据只做显式迁移”的原则：

| 领域 | 当前边界 |
|---|---|
| Memory | 正常运行只使用 `personal_knowledge` SQLite 和请求级 `personalization_context`；旧 `.bobodan/memory/*.md`、daily 文件只由迁移预览读取，不再写入，也不再静态注入 Agent Prompt |
| RAG | `knowledge.db` 是唯一检索入口；`rag_index*.json` 不读取、不更新、不作为 fallback。缺少 SQLite 索引时明确返回 `unavailable` |
| Knowledge Map | `concept_graph.db` 只保存用户审查后的概念、关系和证据；旧 `graph_store.json` 不参与回答，设置页仅惰性检测并提供迁移预览 |
| Legacy graph migration | Concept / 语义关系进入候选审查；Memory 永不进入概念图谱，可作为个人知识导入候选；可能重复只提示不自动丢弃；成功校验后才归档旧 JSON 并记录 SHA-256 与迁移时间 |
| Wiki | 旧 `WikiCompiler` 和 `wiki_ingest` 入口退役；保留 workflow / orchestration 作为高级维护、历史整理、lint 和状态查看，不把 Wiki 页面当作 RAG 证据。完整边界（四问）见 [`ROADMAP.md`](ROADMAP.md) §5「D-WIKI」（2026-11-11 拍板） |
| Provider | Provider 暴露完整同步 / 流式契约，并使用 `ProviderTimeout`、`ProviderConnectionError`、`ProviderConfigError` 等类型化错误；factory 使用注册表装配 |
| Service | Service 共用 `service/_result.py` 返回 `ok/code/error` 结构，Web 错误适配按 code 映射状态码，不再依赖错误文案字符串 |
| Learning | 复习调度升级为带 `ease_factor`、`interval_days` 的保守 SM-2；错题重练把原题与用户错误答案交给生成器，产出针对同一误区的不同问法 |
| Frontend | 页面路由使用 `React.lazy` / `Suspense` 分块；Chat 流归约、命令路由、错误展示和部分状态职责从巨型组件中提取为可测试单元 |

旧数据不会被 reset 或同步流程静默删除。旧索引和图谱文件可以保留为迁移来源，但正常 Chat、检索、知识地图和个性化运行时不得继续消费它们。

### 3.4 优化原则

- 以“用户完成一次学习闭环”为进度单位，不以页面或模块数量为进度单位。
- 服务器端存储是学习状态真相源；浏览器只保存草稿、当前页面和 session 指针。
- 来源必须是结构化数据，不能让前端从自然语言回答里猜引用。
- 主流程只保留 Chat、Practice、Review、Library；Today 作为 Chat 的起始状态，Roadmap 后补（一级导航另有知识地图与笔记，共 6 项；校验：2026-10-28，web/frontend/src/components/shell/nav.ts:5-10）。
- MCP、specialist、trace、模型切换继续保留，但不阻塞 Web 学习 MVP。
- 新增代码优先扩展现有 service，不创建重复的前端业务层或第二套学习逻辑。

## 4. 发布验收要求

> P5C–P5G 的历史阶段记录（约 740 行）已于 2026-11-11 移到 [`archive/PROJECT_GUIDE_PHASES_P5.md`](archive/PROJECT_GUIDE_PHASES_P5.md)。本章只保留**仍然生效**的发布验收要求；排期与门禁只看 [`ROADMAP.md`](ROADMAP.md) §4「发布阻塞项」。

### 4.1 Windows 桌面版（原 P5G.2）

1. 采用 OpenHanako 式 `Electron + React + Python FastAPI sidecar`，不重写现有 Python service、RAG、Wiki 和学习逻辑。
2. PyInstaller 使用 `onedir` 构建 `bobodan-server.exe`；Electron 负责单实例、窗口、文件夹选择、外部链接、sidecar 生命周期和崩溃提示。
3. Electron 等待 `/api/health` 成功后进入主界面，退出应用时终止 sidecar；端口冲突和启动失败必须有可操作恢复入口。
4. 启用 `contextIsolation`，禁用 renderer Node.js 权限，只通过白名单 preload IPC 暴露桌面能力。
5. Provider 密钥真相源是 `~/.bobodan/provider.json`（P5G.4 建立，web / CLI / Electron 共享）；Electron 可选用 `safeStorage` 把密钥升级为系统加密后作为进程环境注入 sidecar，不强制。密钥不得出现在 HTTP 响应、URL、日志、资料库或安装目录。
6. electron-builder 生成 Windows x64 NSIS 安装包 `Bobodan-Setup-x64.exe`，同时发布 `SHA256SUMS.txt`、SBOM 和第三方许可清单。
7. GitHub Actions 在干净 Windows runner 上构建并执行安装包启动测试。首版不内置 OCR、Embedding、本地大模型、离线模型包或自动更新。

### 4.2 总体验收（原 P5G 总体验收）

- 混合文本 / 扫描 PDF、含表格或图片的 DOCX、含图片或无文字页的 PPTX 都能产生准确、可理解的提取报告。
- 零 chunk 文档仍显示在 Library，并从 RAG、Practice 和 Wiki 安全排除。
- 无 Ollama、Embedding、Python 和 Node.js 的干净 Windows x64 环境可以安装并启动 Bobodan。
- FastAPI 静态托管、SPA 深链接、SSE Chat、Practice、Review 和 Wiki 在生产模式通过。
- Electron 覆盖端口冲突、sidecar 失败或崩溃、重复启动、正常退出和用户数据目录隔离。
- API Key 不写入资料库、日志、URL、HTTP 响应或安装目录。
- CI 通过 Python、Vitest、TypeScript、生产构建、Playwright、PyInstaller、Electron smoke test、许可证审计、SBOM 和 SHA256 检查。

### 4.3 发布补充要求（原 2026-08-01 体验审查补充）

以下五项在 2026-08-01 体验审查（[`archive/experience_review_2026-08-01.md`](archive/experience_review_2026-08-01.md)）中被确认为计划缺口：P5G 章节原有条目停留在功能名级别，缺少桌面本地产品发布所需的落地细节。**验收要求留在本节**（按 `docs/README.md` 的权威划分，发布门槛以本文为准）；**排期与门禁在 [`ROADMAP.md`](ROADMAP.md) W5**。两者不是互相让渡的关系——不要写"以对方为准"。不能脱离该路线单独恢复执行。

1. **数据备份 / 恢复专项**（`W4-RESTORE-01` 已于 2026-11-20 落地验证，见 `service/backup_service.py` 与设置页「记忆与数据」）：覆盖资料库原件、SQLite 库（`knowledge.db`、`bobodan.db`、`concept_graph.db`、`research.db`）及可选全局数据（`personal-knowledge.db`、`usage.db`、`preferences.json`），采用 `sqlite3.Connection.backup()` 保证 WAL 一致性并附 SHA-256 清单，默认排除 `provider.json` 密钥与 `.env`，支持异地干净目录恢复、校验与失败自动回滚。
2. **复习提醒交付机制**：指定 Windows 系统通知或托盘常驻方案；Electron 不常驻时提醒无法送达，Review 闭环缺最后一环。
3. **应用升级路径**：定义安装器覆盖安装行为、数据目录版本检测、升级前备份提示；自动更新可继续延后，但升级动作本身必须规划。
4. **卸载清理与数据保留策略**：NSIS 卸载器的行为契约（保留用户资料库 vs 清理应用数据 vs 完整清除），写入 P5G.2 验收。
5. **桌面环境适配与性能预算**：DPI / 高分屏 / 多显示器验收项（纳入 P5G 总体验收），以及首启时间、安装包体积目标值。

### 4.4 首版明确不做

- 完整 Agent / MCP / Logs 管理后台。
- 频道、社交平台入口和多 Agent 群聊。
- 独立 Canvas 产品、复杂知识图谱和完整知识编辑器。
- 模拟考试、限时训练、复杂题型和完整能力模型。
- 多用户 SaaS、跨设备同步、移动端原生 App。
- 主题 / 封面画廊、插件市场、角色卡市场、班级协作、排行榜或社交分享。
- OCR 引擎、OCR 模型、Embedding 模型、本地大模型和离线模型安装包。
- macOS / Linux 安装包、代码签名和自动更新；这些在 Windows 无签名 Prerelease 稳定后再评估。

## 5. 练习系统产品决策

本节记录后续练习系统的产品决策。它是规划，不代表 Web 端已经实现。实现时按这里收口，不重新发散成传统题库后台。

> **2026-09-10 更新（E18 题库交付）**：本节下面的三条早期判断已被用户实测反馈推翻——「不做题库列表优先」「不收藏题」「不做完整错题页」。当前口径以 [`QUESTION_BANK_DESIGN.md`](QUESTION_BANK_DESIGN.md) 与 [`ROADMAP.md`](ROADMAP.md) 的 E18 交付记录为准：
>
> - 练习流程**仍然是一题一卡**，本轮练习体验不变；题库是 Practice 下的**一个视图**（`/practice/bank`），不新增一级导航，也不把题目混进聊天气泡。
> - 收藏只是**标记 + 一键重练**，**不进入复习队列**，也不引入分类 / 标签体系。
> - 「看全部错题」由题库的错题筛选承载（不再被 20 条截断）；独立的错题管理后台与复习调度仍归掌握度引擎，仍不做。

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

Web MVP 一级导航只开放 Chat、Practice、Review、Library；Today 复用 Chat 起始状态，Roadmap 后补（历史：当时 4 项；当前 6 项，见 §2.3；校验：2026-10-28，web/frontend/src/components/shell/nav.ts:5-10）。

页面边界：

- Today：低压问候、记忆提示和 2-3 个学习动作，与 Chat 共用主学习画布。
- 对话页：开放式学习问答。
- 练习页：结构化训练，一题一卡。
- 复习页：今日到期知识点、错题和薄弱点。
- 资料页：资料树、阅读内容、来源和相关概念。
- 路线页：学习目标、当前阶段和今日任务。

### 5.2 练习页形态

第一版采用 **一题一卡**，不做题库列表优先，也不把所有题目混在聊天气泡里。

> 2026-09-10：仍然是一题一卡；但已在同一页下补了 `/practice/bank` 题库视图（E18），列表只用于浏览 / 收藏 / 选择重练，不参与练习中的作答流程。

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

调度实现使用保守 SM-2：首次答对间隔 1 天、第二次 6 天，之后按 `interval_days × ease_factor` 递增；答错重置为 1 天并降低 ease（最低 1.3）。`mastered` 仍会在到期后回到复习队列，不再永久退出循环。

错题开始重练时，不直接重复原题，也不只按概念随机出题。系统把原题、正确答案和用户的错误答案交给生成器，要求生成考察同一误区但表述不同的变式题，并保留原题证据范围。

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

明确不做（2026-09-10 按 E18 交付结果修订）：

- ~~完整错题页~~ → **E18 的题库错题筛选已覆盖「看全部错题」**；仍不做独立的错题管理后台。
- 章节练习。
- 模拟考试。
- 限时训练。
- ~~收藏题~~ → **E18 已交付题目标记与一键重练**；仍不做「收藏驱动复习队列」和分类 / 标签体系。
- 周报 / 月报。
- 完整能力模型计算。
- 跨设备同步。
- 复杂题型。

### 5.21 下一阶段实现顺序

P5C-P5G 的历史顺序已归档到 [`archive/PROJECT_GUIDE_PHASES_P5.md`](archive/PROJECT_GUIDE_PHASES_P5.md)，避免在练习系统决策中维护第二份路线。后续实现只按 [`ROADMAP.md`](ROADMAP.md) 的当前批次推进；每项必须满足该路线图的完成定义，不能只交付静态占位页。

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
- 基于个人学习知识库的个性化讲解、出题和复习。
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
  personal learning knowledge / learning events / legacy read-only migration

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
- `memory/` 管用户长期上下文、个人学习知识、候选确认和旧数据只读迁移，不替代原始资料库或知识地图。
- Provider 失败必须保留类型信息；可重试超时、连接失败和配置错误不能在 service / Web 边界退化成同一种字符串异常。
- Service 对外统一返回结构化结果信封；router 负责把稳定错误码转换为 HTTP，不从自然语言错误消息猜状态。
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
- 包含个人知识数据库、trace、迁移来源 / 元数据，以及 Web 上传资料的托管副本目录 `sources/`。旧 permanent / daily Markdown 可能继续存在，但只作为显式迁移来源。
- 不应随便删除。

个人学习知识库：

- SQLite 是 `LearningEvent`、`KnowledgeCandidate` 和 `PersonalKnowledgeItem` 的 truth source。
- 用户级全局数据只保存称呼、低风险偏好和长期目标；掌握度、错题、课程进度、学习笔记和资料相关结论必须带 `library_id`。
- 未确认候选不得注入为稳定事实；敏感画像、健康判断和人格推断默认不自动保存。
- 确认后的高价值内容可以导出到 Markdown / Obsidian，但导出文件不与数据库双向自动同步。
- 用户删除或清空后，请求级个性化上下文、Chat 检索、Practice 个性化与 Review 推荐必须在下一次请求前刷新；禁止保留进程启动时生成的静态 memory prompt。

知识地图与旧图谱：

- `concept_graph.db` 是已审查概念、关系、证据和候选状态的 truth source。
- 候选概念不得作为 Agent 的知识依据；只允许返回候选数量 / 状态摘要，用户审查确认后才进入正式图谱。
- `graph_store.json`、旧 Neo4j 数据和旧图谱工具不参与正常运行；旧 JSON 只在“设置 → 记忆与数据”中惰性检测、预览和显式迁移。
- 迁移发现的 Memory 节点无条件排除出概念图谱；可导入个人知识的项目必须由用户选择，可能重复只提示，不自动跳过。

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
- 历史 Wiki 页面是高级维护 / 只读整理产物，不是 Chat RAG 的必要中间层。
- `.knowledge/` 是运行时索引。

## 9. 新功能判断

新增功能前先问：

1. 它是否让对话入口更好用？
2. 它是否直接改善学习闭环？
3. 它是否能把用户资料转化为更可信的回答、练习或复习？
4. 它是否会迫使普通用户理解底层技术名词？

如果一个功能只服务工程可玩性，而不服务前三点，就应该降级、隐藏或暂缓。

## 10. 常用专题文档

日常只需要读本文；完整文档地图见 [`docs/README.md`](README.md)——它是唯一索引，新增、改名或废弃文档先改它（校验：2026-10-28，docs/README.md:5）。最常读的三份：

- `docs/ROADMAP.md`：**统一路线图**——现在做什么、接下来做什么、已拍板决策、明确不做（唯一排期依据）。
- `docs/DESIGN.md`：Web / TUI / 官网视觉硬约束。任何界面设计开工前必须先读。
- `docs/Bobodan参考项目调研报告.md`：DeepTutor / OpenMAIC / qiaomu 借鉴机制精讲与源码索引（ROADMAP 条目的论据）。

## 11. 最终结论

Bobodan 后续应该避免做成“知识库后台 + 聊天框”，也不要走向“万能 Agent 工具箱”。

它应该成为：

> 一个像 ChatGPT / Gemini 一样自然的 AI 对话主页，但默认懂用户的本地资料，并能把对话、阅读和练习逐渐沉淀为可管理的个人学习知识库，让它越用越理解用户已经掌握什么、容易在哪里出错，以及怎样教学最有效。

---

## 12. 常用命令、架构目录与关键契约

为避免文档过长导致多 Agent 上下文漂移，原 §12（常用命令与 CLI）、§13（架构真相·目录树）与 §14（关键运行时契约）已于 2026-11-20 独立整理到轻量的 [**`docs/ARCHITECTURE_AND_CONTRACTS.md`**](ARCHITECTURE_AND_CONTRACTS.md) 中维护，请直接查阅该文档。
