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
| 安静桌面工作区 | [OpenHanako](https://github.com/liliMozi/openhanako) | 三栏工作区、角色化欢迎页、工作空间与记忆状态、右侧书桌/便笺、纸面 Token；不吸收办公 Agent 的频道和社交入口 |
| LLM Wiki | [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) | 原始资料只读、Schema 约束、两阶段 Wiki 生成、安全增量合并、任务队列、来源依赖和结构 / 语义检查；不吸收自动摄入与知识库后台定位 |

#### 2.2.1 OpenHanako 借鉴边界

OpenHanako 与 Bobodan 都受到 Kami 纸面美学影响，适合作为 Web 工作区结构参考，但产品目标不同：OpenHanako 是通用私人 Agent，Bobodan 必须保持学习助手定位。

第一优先级，进入 P5D：

| 借鉴点 | Bobodan 的实现方式 |
|---|---|
| 三栏工作区 | 左侧会话 / 学习空间，中间 Chat 主画布，右侧可折叠学习上下文；窄屏只保留主画布，左右栏改为抽屉 |
| 角色化欢迎页 | Today 复用 Chat 空状态，显示 Bobodan 小猫、“今天想学什么？”、当前学习空间、记忆状态和 2-3 个真实学习动作 |
| 工作空间绑定 | 一个学习空间绑定课程或项目、资料范围、聊天、笔记、练习记录和学习记忆，不把文件夹概念直接暴露给普通用户 |
| 右侧书桌 / 便笺 | 转化为“资料 / 学习笔记”上下文面板；根据任务切换来源、相关知识点、当前题目和解析，不固定显示后台信息 |
| Composer | 支持附件、资料范围、引用选中文字和短学习动作；模型、工具和推理等级保持低视觉权重 |
| 纸面设计系统 | 使用本地字体、暖纸 Token、轻纹理、小圆角、细分隔和短时动效；以 `docs/DESIGN.md` 为唯一色彩与排版标准 |

第二优先级，在 P5F.1 / P5G 或学习闭环稳定后补：

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

现有技术路线不需要推倒重来。Python + FastAPI + SQLite / Qdrant + React Web UI 仍然适合本地优先的个人学习助手。P5C 已整理 Web 产品合约，P5D 已完成 Library → Chat → Practice → Review，P5E.1 已把测试工作区升级为通用文件夹资料库，P5E.3 已补齐用户偏好与设置中心，P5F 已补齐可信联网候选、证据快照和网页来源练习，P5F.1 已补齐确定性学习事件、候选确认和已确认个人知识，P5E.6 已实施知识地图产品重置。2026-07-26 审查整改进一步退役了旧 memory、JSON RAG、JSON / Neo4j graph 和 Wiki compiler 的正常运行路径。下一步进入 P5G 发布收尾。

一句话结论：

> 本地资料、可信联网证据与个人学习知识库已经形成闭环；知识地图已落地，下一步解决文档漏读可见性和 Windows 桌面发布。

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

仍待 P5G 解决：

- PDF、DOCX 和 PPTX 只能读取已有文本层；扫描页、图片文字和零 chunk 资料需要可见的提取报告，不能继续静默消失。
- 项目尚无发布许可证、第三方声明、隐私说明、SBOM 和安装包校验，需要先完成发布合规并移除 PyMuPDF 许可风险。
- 开发期仍是 Vite + FastAPI 两个进程；FastAPI 静态托管、`bobodan web`、PyInstaller sidecar 和 Electron 安装包尚未实现。
- MCP / specialist 不进入首发 Workbench；只有请求级 ToolContext 和发布安全边界稳定后才重新评估。

### 3.3.1 2026-07-26 审查整改边界

本轮整改遵循“只保留一个正常运行真相源，旧数据只做显式迁移”的原则：

| 领域 | 当前边界 |
|---|---|
| Memory | 正常运行只使用 `personal_knowledge` SQLite 和请求级 `personalization_context`；旧 `.bobodan/memory/*.md`、daily 文件只由迁移预览读取，不再写入，也不再静态注入 Agent Prompt |
| RAG | `knowledge.db` 是唯一检索入口；`rag_index*.json` 不读取、不更新、不作为 fallback。缺少 SQLite 索引时明确返回 `unavailable` |
| Knowledge Map | `concept_graph.db` 只保存用户审查后的概念、关系和证据；旧 `graph_store.json` 不参与回答，设置页仅惰性检测并提供迁移预览 |
| Legacy graph migration | Concept / 语义关系进入候选审查；Memory 永不进入概念图谱，可作为个人知识导入候选；可能重复只提示不自动丢弃；成功校验后才归档旧 JSON 并记录 SHA-256 与迁移时间 |
| Wiki | 旧 `WikiCompiler` 和 `wiki_ingest` 入口退役；保留 workflow / orchestration 作为高级维护、历史整理、lint 和状态查看，不把 Wiki 页面当作 RAG 必需证据 |
| Provider | Provider 暴露完整同步 / 流式契约，并使用 `ProviderTimeout`、`ProviderConnectionError`、`ProviderConfigError` 等类型化错误；factory 使用注册表装配 |
| Service | Service 共用 `service/_result.py` 返回 `ok/code/error` 结构，Web 错误适配按 code 映射状态码，不再依赖错误文案字符串 |
| Learning | 复习调度升级为带 `ease_factor`、`interval_days` 的保守 SM-2；错题重练把原题与用户错误答案交给生成器，产出针对同一误区的不同问法 |
| Frontend | 页面路由使用 `React.lazy` / `Suspense` 分块；Chat 流归约、命令路由、错误展示和部分状态职责从巨型组件中提取为可测试单元 |

旧数据不会被 reset 或同步流程静默删除。旧索引和图谱文件可以保留为迁移来源，但正常 Chat、检索、知识地图和个性化运行时不得继续消费它们。

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
- Chat composer 输入 `/` 可选择 Web 安全命令与 `course-learning / exam-prep / study-loop` 三个学习 Skills；CLI 管理能力继续隐藏。

#### P5D.1 前端地基

- 建立 `web/frontend`、路由、Vite proxy 和 API client。
- 落地 `DESIGN.md` tokens、字体和核心组件。
- 建立响应式三栏骨架：左侧会话 / 学习空间，中间 Chat 主画布，右侧可折叠学习上下文；移动端使用抽屉，不压缩主对话列。
- Today 作为 Chat 无活动会话时的起始状态，不单独搭第二套首页。
- Today 使用 Bobodan 正式头像或学习场景图，显示当前学习空间与记忆状态；只提供“开始提问、导入资料、开始练习”等真实可执行动作。
- 增加四步首次配置：用户与目标、AI 连接、首个学习空间、记忆与联网边界；模型职责默认自动配置。
- 第一批真实入口只开放 Chat、Practice、Review、Library；没有数据的入口显示“导入资料 / 开始对话”等可执行空状态，不放假按钮。

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
4. 确认写入：`/wiki generate` 与 `/wiki update` 在用户确认后才执行。
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
- Chat 支持 `/wiki plan`、`/wiki update` 和 `/wiki generate`；Library 支持从学习资料或已有 Wiki 页面发起。
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

验收结果：Python `1102 passed`；Vitest `5 passed`；TypeScript 与生产构建通过；Playwright 桌面、窄屏和移动端 `57 passed`。下一步进入 P5F.1。

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

### P5G：文档完整性、Windows 桌面发布与支撑页面

P5G 不先堆叠新页面。执行顺序固定为：

```text
P5E.5 Wiki 易用性、手写编辑与 AI 成本控制（完成）
→ P5E.6 知识地图产品重置（完成）
→ P5G.0 文档提取完整性与发布合规
→ P5G.1 单进程本地 Web
→ P5G.2 Windows Electron 桌面版
→ P5G.3 支撑页面与体验收尾
```

与 P5G 并行存在一条整机优化工作流（Agent 运行时、前端体验、资料协作），详见 `docs/AGENT_OPTIMIZATION_PLAN.md`：其中 AG-0 / FE-1 / LB-1.1 为纯增量改动，可与 P5G 并行；会话格式变更（AG-1）等 P5G 验收后才启动。该工作流不改变本节 P5G 的执行顺序与验收条件。

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

1. FastAPI 在生产模式托管 React `dist`，并为 `/chat/*`、`/library`、`/practice/*` 等 SPA 深链接回退到 `index.html`。
2. 增加 `bobodan web`，默认绑定 `127.0.0.1`、选择可用端口并自动打开浏览器；开发模式继续使用 Vite + FastAPI。
3. 全局配置写入 `%APPDATA%\Bobodan`，日志和缓存写入 `%LOCALAPPDATA%\Bobodan`；用户资料库继续保存在用户选择的文件夹中。
4. SQLite FTS5 是零模型默认检索。Ollama、Embedding 和远程服务保持可选，不自动下载或随应用分发模型权重。
5. 生产启动必须提供明确的健康检查、端口冲突、后端崩溃和配置缺失恢复信息。

#### P5G.2：Windows Electron 桌面版

1. 采用 OpenHanako 式 `Electron + React + Python FastAPI sidecar`，不重写现有 Python service、RAG、Wiki 和学习逻辑。
2. PyInstaller 使用 `onedir` 构建 `bobodan-server.exe`；Electron 负责单实例、窗口、文件夹选择、外部链接、sidecar 生命周期和崩溃提示。
3. Electron 等待 `/api/health` 成功后进入主界面，退出应用时终止 sidecar；端口冲突和启动失败必须有可操作恢复入口。
4. 启用 `contextIsolation`，禁用 renderer Node.js 权限，只通过白名单 preload IPC 暴露桌面能力。
5. Provider 密钥由 Electron `safeStorage` 保存，启动 sidecar 时作为进程环境注入；密钥不得出现在 HTTP 响应、URL、日志、资料库或安装目录。
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

以下五项在 2026-08-01 体验审查（`docs/experience_review_2026-08-01.md`）中被确认为计划缺口：P5G 章节原有条目停留在功能名级别，缺少桌面本地产品发布所需的落地细节；均不属于"本轮明确不做"范围，进入 P5G 执行时一并落地。

1. **数据备份 / 恢复专项**：明确备份对象清单（资料库、`personal-knowledge.db`、`usage.db`、`research.db`、`preferences.json`）、备份格式与 SQLite WAL 一致性方法、手动 / 自动触发、校验与恢复 UI、失败恢复验证。这是本地优先产品用户信任的根基。
2. **复习提醒交付机制**：指定 Windows 系统通知或托盘常驻方案；Electron 不常驻时提醒无法送达，Review 闭环缺最后一环。
3. **应用升级路径**：定义安装器覆盖安装行为、数据目录版本检测、升级前备份提示；自动更新可继续延后，但升级动作本身必须规划。
4. **卸载清理与数据保留策略**：NSIS 卸载器的行为契约（保留用户资料库 vs 清理应用数据 vs 完整清除），写入 P5G.2 验收。
5. **桌面环境适配与性能预算**：DPI / 高分屏 / 多显示器验收项（纳入 P5G 总体验收），以及首启时间、安装包体积目标值。

### 本轮明确不做

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
P5C 产品化基础（完成）
→ P5D 本地学习闭环 Web MVP（完成）
→ P5E 用户主动触发的 LLM Wiki（完成）
→ P5E.1 文件夹资料库与持久化 Wiki 工作流（完成）
→ P5E.2 Wiki 可靠性增强（完成）
→ P5E.3 Web UI 系统体验与设置中心（完成）
→ P5F 可信资料扩展（完成）
→ P5F.1 个人学习知识库（完成）
→ P5E.4 全库 Wiki 编排与覆盖系统（完成）
→ P5E.5 Wiki 易用性、手写编辑与 AI 成本控制（完成）
→ P5E.6 知识地图产品重置（完成）
→ P5G.0 文档提取完整性与发布合规
→ P5G.1 单进程本地 Web
→ P5G.2 Windows Electron 桌面版
→ P5G.3 支撑页面与体验收尾
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

日常只需要读本文。需要深入时再看：

- `docs/DESIGN.md`：Web / TUI / 官网视觉硬约束。任何界面设计开工前必须先读。
- `docs/AGENT_OPTIMIZATION_PLAN.md`：整机优化计划书（Agent 运行时 / 前端体验 / 资料协作），与 P5G 并行的工作流，排期与验收门禁以该文档为准。
- `docs/rag_design.md`：RAG v2 详细设计。
- `docs/knowledge_map_design.md` 与 `docs/knowledge_map_reliability_editing_design_2026-07-27.md`：知识地图产品与可靠性设计。
- `docs/MCP.md`：MCP 客户端使用。
- `docs/tools/skills.md`：Skills 系统说明。

## 11. 最终结论

Bobodan 后续应该避免做成“知识库后台 + 聊天框”，也不要走向“万能 Agent 工具箱”。

它应该成为：

> 一个像 ChatGPT / Gemini 一样自然的 AI 对话主页，但默认懂用户的本地资料，并能把对话、阅读和练习逐渐沉淀为可管理的个人学习知识库，让它越用越理解用户已经掌握什么、容易在哪里出错，以及怎样教学最有效。
