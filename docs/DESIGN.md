# Bobodan Design Guide（v2.1 · 2026-10-28）

> 定位：Bobodan 的**可执行**设计规范 —— 能被实现、能被测试、能被审查，而不只是被阅读。
> 品牌锚点不变：**暖纸底 + 墨蓝阅读秩序 + 植物绿自然气息 + 橘棕温度 + 花瓣粉私人情绪；中文排版有风骨。**
> 与 v1 的关系：结构与品牌决策保留，内容升级为规格化（新增表面阶梯、发丝边、高度阶梯、弹簧物理、IME 守卫、性能预算、打包清单）。
> 执行方式：本文的数值都是 token；`web/frontend/src/lib/designTokens.test.ts` 把关键约定变成会失败的测试（见 §16.3）。
> **v2.1（2026-10-28）**：按 `tokens.css` 与样式实测校正了四处文档漂移——§6.5 高度阶梯（实为三档且零引用）、§7.1 圆角矩阵（panel 值错、`--radius-bubble` 不存在）、§11.3 弹簧表（改回实际的 press/pop/panel/accent）、§16.2 用户消息气泡行（按 `app.css:692` 实际样式）；新增 §11.8 外部动效库边界。

**实施状态标记**（本文所有新增规则都带这个标记，不许含糊）：

- ✅ **已落地**：代码里已存在并有测试。
- 🟡 **计划中**：本方案 M3/M4/M5 实施；实施时同步加入 `:root` 与 §16.3 契约。

---

## 0. 如何使用本文档

| 角色 | 读法 |
|---|---|
| 设计 | §1–§3 定调 → §4–§7 取数值 → §13 清单自检 → §14 配额设上限 |
| 实现 | 只从 token 取值，不写裸数值；新组件先查 §16 规格表；动效只用 §11 的 token 曲线 |
| 审查 | §7 的五层验收 + §19 打包前清单；发现文档与代码不一致时，以契约测试为准 |

**唯一原则**：文档写下的数字必须能在代码里找到同名的 token；找不到就说明文档在说谎。

---

## 1. 设计定位

Bobodan 是一个本地优先、Chat-first 的个人学习助手。界面的第一任务是让「读、问、练、复习」这条闭环顺畅，第二任务是让用户愿意长时间待在里面。

### 关键词

安静、纸面、编辑部感、可长时间阅读、克制、本地、可预期。

### 不追求

不做高密度数据看板，不做炫技动效，不做 AI 产品常见的赛博蓝紫，不做「一眼酷但读不下去」的界面。

---

## 2. 品牌气质

像一间安静的书房：暖米色纸张、墨蓝的秩序、植物的绿意、木头与陶土的温度，偶尔一点花瓣粉的私人情绪。

- **主色是墨蓝**（阅读秩序），不是绿色。
- **绿色是自然与状态**，只做辅助。
- **橘棕是温度**，只做点缀。
- **文字是深咖啡**，不是纯黑。

---

## 3. 参考宇宙

### 产品骨架

ChatGPT / Claude 桌面端的会话结构：中央对话、资料入口、学习动作、右侧上下文。

### 阅读气质

Kami 的纸面排版、Readwise Reader 的专注阅读与摘录。

### 技法参考（新增 ✅ 已采集）

`open-claude-ui`（对 Claude 桌面端的逆向设计规范）只提供**技法**，不提供品牌：

- 表面阶梯（Surface 0–3）、发丝边与外环、圆角/高度矩阵；
- 4 套弹簧物理常数、CJK 输入法合成守卫、指针死区、滚动遮罩；
- 组件四态矩阵与「可执行规格」的写法。

本项目**不采用**它的陶土色板、音频提示、光效或品牌语汇。

### 明确不追求（视觉）

暗黑终端风、冷白科技风、极客工具风、企业后台风、金融高密度风、整页主题色。

---

## 3.1 一级导航与全局层

Bobodan 的学习界面是一条固定骨架：左侧一级导航 + 中间工作区 + 右侧学习上下文。一级导航 ✅ **六项**，桌面与移动端共用同一份清单与顺序（`web/frontend/src/components/shell/nav.ts:4-11`）：

| # | 页面 | 路由 | 页头 kicker |
|---|---|---|---|
| 1 | 对话 | `/chat`、`/chat/:sessionId` | 学习对话 |
| 2 | 练习 | `/practice`、`/practice/bank`、`/practice/:practiceSessionId` | 主动练习 |
| 3 | 复习 | `/review` | 今日复习 |
| 4 | 知识地图 | `/knowledge-map` | 知识地图 |
| 5 | 笔记 | `/notes` | 我的笔记 |
| 6 | 资料库 | `/library`、`/library/read/:id` | 本地资料 |

- 六个入口平级、视觉权重相同。**「Study 一级 / Workbench 二级」的二分已退役 ✅（2026-10-28 校正）**：代码里既没有 Study/Workbench 容器，也没有二级分组，知识地图与笔记都是独立一级页面。
- 设置不占一级导航：入口固定在左侧资料库信息区底部（资料库名 + Provider + 齿轮），点击后以 `?settings=<section>` 弹窗打开（`AppShell.tsx:553-557`）。
- 页头标题来自 `pageMeta`（`nav.ts:13-20`）。2026-10-28 补齐缺失的 `notes` 键并加断言测试，六个一级页面的 kicker 与副标题不再回落成 Chat 文案。
- 全局层（跨页面常驻，不参与导航计数）：
  - **设置中心**：960–1120px 居中弹窗、最大高度约 84vh，移动端全屏；骨架为「搜索与分类导航 + 分组内容」，10 个分节（见 §3.3 全局层）。
  - **右侧学习上下文** ✅：桌面三栏的第三栏，窄屏收起（`components/shell/ContextPanel.tsx:2`）。
  - **首次配置**：资料库选择 + Provider；**快捷键** Ctrl N 新对话；**连接/错误提示**：只在断开或重连时出现。
- 一级导航之上不设 dashboard：Today 不是第七个入口，它的语义是「对话的空态起点」✅（`components/chat/ChatWelcome.tsx:20-38`）。

---

## 3.2 信息密度与响应式优先级

- 桌面（≥1280px）：三栏（侧栏 252px / 主内容 720px / 上下文 304px）。
- 桌面窄（960–1279px）：收起上下文栏，主内容优先。
- 移动端（本轮不做，但布局不得破坏）：六个一级页面（对话 / 练习 / 复习 / 知识地图 / 笔记 / 资料库）都不得破版。

---

## 3.3 页面气质规则

### 对话（Chat，`/chat`）

Chat 用对话主骨架，但视觉像阅读器和笔记本：中央对话、资料入口、学习动作入口、右侧学习上下文；回答区域要像文章，不像日志流。

**空态就是学习起点 ✅**：品牌图 + 一句「今天想学点什么？」+ 当前资料库与记忆提示 + Composer + 4 个行动建议（梳理学习重点 / 先讲直觉再补证明 / 导入资料 / 开始练习），不用统计卡片堆出 dashboard（`ChatWelcome.tsx:20-38`）。Today 不再单列页面。

**Composer 三层结构**（不许把所有控制塞进一排）：① 输入框内：附件 / Slash / 资料范围 / 回答深度 / 模型 / 发送或停止；② 输入框上方：检索、Wiki、练习生成等当前状态；③ 全局连接条：只在断开/重连时出现。

**对话内的二级能力**（都是 Chat 内的卡片与流程，不是页面，不占一级导航）：出题与开练（PracticeReadyCard）、Wiki 的 focus/计划/结果卡（由 `/wiki plan`、`/wiki update` 触发）、联网研究三卡（同意 / 证据 / 候选）、学习上下文卡、记忆写入确认卡、设置修改确认卡、通用提问卡。原则：卡片只做「确认、纠正、继续」，不做成二级页面。

### 练习（Practice，`/practice`）

一题一卡，像纸面测验：轻边界、清楚题干、充足留白、温和反馈、来源标签清楚。**不要**做成密集刷题后台。

**题库是 Practice 的二级视图 ✅**（`/practice/bank`，不是第七个导航）：页内视图切换「开始练习 / 题库」（`QuestionBankPage.tsx:423-426`），按最近一次作答状态归类，带筛选、搜索、分页、练习集、导出 Markdown / 备份与恢复 JSON、单题「讲解 / 重练」；Practice 页头也有「题库」入口。

### 复习（Review，`/review`）

像一份轻量学习清单：到期知识点、错题、薄弱点三类合并成一条队列（`ReviewPage.tsx:14,71-73`），每条给出「为什么现在复习」；带「在题库中查看全部」回流入口。**不要**做成复杂日历或大数据面板。

### 知识地图（`/knowledge-map`）

三视图：地图 / 目录 / 来源，共享同一套筛选；节点详情用右侧侧栏滑入，未审查候选单独成面板（`KnowledgeMapPage.tsx:1-10,24-25`）。只收用户已审查的概念与关系，未审查候选只显示状态摘要、不参与回答。**不要把大图谱当主舞台**——这条旧规则现在归知识地图页，不再约束资料库。

### 笔记（`/notes`）

沉浸式 Markdown 编辑，正文为主角 ✅（`NotesPage.tsx:63,296-313`）：首行「# 标题」自动提取为标题；「编辑 / 预览」切换；`Ctrl+Enter` 保存、`Esc` 关闭；「关联资料」折叠在底部按需勾选；草稿按「资料库 + 笔记」自动保留（上限 5000 字）；列表支持置顶、搜索、删除，并带记忆管理入口。笔记可关联资料，阅读原文时能看到相关笔记；**笔记永不进入概念图谱**。不做表单式「标题框 + 正文框 + 复选框堆叠」。

### 资料库（Library，`/library`）

资料树 + 阅读/来源面板为主，局部关系为辅：左侧资料树，中间阅读或列表，右侧来源/双链/局部图谱（右栏即全局学习上下文）。导入、索引状态、整理建议都在这一页；「整理成 Wiki / 更新 Wiki」只把范围带进 Chat 生成计划，不在资料页直接写文件。资料编辑用资料编辑器（不是笔记编辑器）。

**阅读器（Reader，`/library/read/:id`）是 Library 内的专注阅读视图 ✅**：顶栏上一篇/下一篇与标签条、按 `?chunk=` 定位到小节并高亮；划线 ✅ 已落地（选区存为引文锚点，原文里定位不到偏移就如实存 null）；Markdown/TXT 等可编辑类型可切到编辑。**「摘录 / 稍后读 / 复习回流」🟡 未见实现**（阅读器代码里没有对应入口），要么补实现，要么从本节删掉，别再写成现状。视觉保持纸面阅读气质；正文字号必须跟随设置里的「正文字号」偏好（L2 计算样式契约看住，见 §16.3）。

### 全局层：设置中心

设置入口在左侧资料库信息区，不占一级导航；桌面 960–1120px 居中大弹窗（最大高度约 84vh），移动端全屏；背景保留当前学习页面并轻度压暗，不跳转企业后台式独立控制台。

骨架固定为「搜索与分类导航 + 分组内容」，**按代码顺序共 10 节** ✅（`SettingsDialog.tsx:29-40`，旧 7 节清单缺后三节）：我与学习、Bobodan、界面与阅读、AI 与模型、**检索与 RAG**、记忆与数据、Skills、**安全与隐私**、状态与关于、**实验**。旧地址 `?settings=user` / `ai` 分别归一到 me / models。

开关与单选即时保存，失败恢复旧值；用户资料与人设表单用明确保存按钮。设置页**不得**编辑 API Key / `.env` / 文件权限 / 联网权限 / 系统安全规则，也不得显示绝对 Skill 路径、Trace、原始日志。对话修改设置必须先显示前后值确认卡（只允许回答深度、教学方式、反馈强度、记忆开关）；确认前不修改，拒绝后不留隐式副作用。

### 已退役与未实现（不得再写成本节现状）

- **Today** ✅：并入对话起点，不设独立页面。
- **Roadmap** 🟡：前端没有页面也没有路由；`docs/ROADMAP.md` 是路线文档，不是产品页面。
- **Canvas** 🟡：没有「学习白纸」面板；`GraphCanvas.tsx` 是知识地图的画布组件，不是 Canvas 页。
- **Memory** ✅：不是页面；管理入口在设置「记忆与数据」与笔记页的记忆管理弹窗。
- **Workbench / Study 二分** ✅：已退役（原 §3.1 的核心假设，代码无对应容器）。
- **「个人笔记」曾写在 Chat 节内**：已迁到笔记页，Chat 节不再描述笔记编辑。

---

## 4. 色彩系统

### 4.1 基础色

| 角色 | token | 值 | 用法 |
|---|---|---|---|
| 内容画布 | `--paper` | `#f5f4ed` | 页面主背景 |
| 抬升表面 | `--paper-soft` | `#faf9f5` | 卡片、菜单、选中行 |
| 停靠表面 | `--paper-sunken` | `#f0eee6` | 侧栏、右栏、内嵌块 |
| 主文字 | `--ink` | `#2e2b27` | 正文 |
| 次要文字 | `--muted` | `#5b544a` | 说明文字 |
| 辅助文字 | `--faint` | `#71685c` | 时间、计数（仍 ≥4.9:1） |

### 4.2 色相与用色规则

| 色相 | token | 用途 | 红线 |
|---|---|---|---|
| 墨蓝 | `--blue` / `--blue-soft` / `--blue-wash` | 阅读主色、主按钮、当前导航、链接 | 只能是它当主角，绿色不许抢 |
| 植物绿 | `--sage` / `--sage-wash` / `--sage-deep` | 自然辅助、正向状态、引用边 | 不做主选中态 |
| 橘棕 | `--clay` / `--clay-wash` | 温度点缀、强调、练习反馈 | 每屏面积 ≤ 5% |
| 花瓣粉 | `--petal-wash` | 私人情绪、个人知识 | 只做 wash，不做实色大面积 |
| 状态红 | `--danger` | 错误、失败 | 不用于装饰 |

**透明度组合**：需要半透明时用 rgb 三元组（`--accent-rgb` / `--ink-rgb` / `--sage-rgb` / `--clay-rgb`），不要新造 rgba 字面量。

### 4.3 颜色面积预算

**渐变预算（M3）**：每屏背景渐变 ≤ 1 处，且同色相明度差 ≤ 8%；遮罩渐变（`mask-image`）与纸纹不计入。整份样式背景渐变由 `designTokens.test.ts` 棘轮看住：断言 `background…linear-gradient(` 出现次数 **≤ 3**（2026-10-28 实测 3 处，M4 骨架屏微光 +1），只减不增。「每屏 ≤ 1 处」是设计目标，不是可自动测量的量。

| 区域 | 预算 |
|---|---|
| 背景 / 表面 | ≥ 85% 屏幕面积 |
| 墨蓝系 | ≤ 10% |
| 绿色系 | ≤ 4% |
| 橘棕系 | ≤ 5% |
| 花瓣粉 | ≤ 1%（仅 wash） |

### 4.4 表面阶梯（Surface 0–3）✅ 已实施（M3，2026-10-17）

参考 CDS 的四层微对比，但**不新增色值**，用现有三档纸面色 + 抬升组合表达：

| 层 | 组合 | 用在哪 |
|---|---|---|
| Surface 0 | `--paper-sunken` | 停靠栏：侧栏、右栏、内嵌块 |
| Surface 1 | `--paper` | 页面主画布 |
| Surface 2 | `--paper-soft` + `--border-subtle` 发丝边 | 卡片、列表容器、消息容器 |
| Surface 3 | `--paper-soft` + `--hairline` 外环 + `--shadow-float` | 输入框、浮层、菜单、弹窗 |

**规则**：相邻两层必须能区分（明度差 ≥ 2/255，或靠发丝边区分）；同一屏最多 4 层，超过就是「卡片套卡片」。

**表面落位清单（M3 ✓）**：Surface 0 = `.sidebar` / `.context-panel` / `.settings-nav` / `.library-tree-pane` / `.document-rail`；Surface 1 = `.page-scroll` / `.settings-main`；Surface 2 = `.settings-section`（+ `--border-subtle` 发丝边）；Surface 3 = `.ui-modal-panel` / `.slash-palette` / `.mention-palette` / `.library-more-menu > div` / `.notice`（+ `--ring` 外环 + 阴影档位）；**输入区**（`.composer` / `.settings-field input` / `.settings-search` / `.document-search`）同样走 Surface 3 + ring，焦点色用 `color-mix(in srgb, var(--accent) 35%, transparent)`，不再写裸 rgba。契约测试：`designTokens.test.ts` 的「M3 表面阶梯落位」。

### 4.5 发丝边与外环 ✅ 已实施（M3，2026-10-17）

硬边框在暖纸底上会显得脏。规则：

- 容器边界优先用 **发丝边**：`--hairline: 1px`，2dppx 下取 `0.5px`。
- 浮层外环用 `--ring: color-mix(in srgb, var(--ink) 12%, transparent)`，写 `box-shadow: 0 0 0 var(--hairline) var(--ring)`。
- 只有输入框与强强调元素使用 `--border-strong`；正文分隔用 `--border-subtle`。
- 禁止用纯黑或纯 HTML 默认边框色。

> 说明：`--hairline` / `--ring` 已加入 `:root` 与 §4.6 表（M3 ✓），契约测试见 §16.3 第 8–10 条。2dppx 下 `--hairline` 减半为 `0.5px`（`@media (min-resolution: 2dppx)`）。

**浮层落地清单（M3 ✓）**：`.ui-modal-panel`（所有弹窗）、`.slash-palette` / `.mention-palette`（输入区浮层）、`.library-more-menu > div`（更多菜单）、`.notice`（通知卡片）—— 全部改为 `box-shadow: 0 0 0 var(--hairline) var(--ring), <既有阴影档位>`，不再使用 `border: 1px solid rgba(...)`。契约测试在 `designTokens.test.ts` 的「M3 浮层发丝边/外环」用例里。

### CSS Tokens

以下代码块必须与 `styles/tokens.css` 的 `:root` **逐条一致**（契约测试比对，空格不敏感；M1 之后 `styles.css` 只做 `@import`，令牌在 `tokens.css`）：

```css
  --paper: #f5f4ed;
  --paper-soft: #faf9f5;
  --paper-sunken: #f0eee6;
  --parchment: var(--paper-sunken);
  --ink: #2e2b27;
  --muted: #5b544a;
  --faint: #71685c;
  --blue: #1b365d;
  --blue-soft: #2f4f78;
  --blue-wash: #e8edf3;
  --sage: #7a9b76;
  --sage-wash: #e7ede3;
  --clay: #b86f4b;
  --clay-wash: #f3e1d5;
  --petal-wash: #f6e6e2;
  --danger: #934d43;
  --sage-deep: #4f6e4c;
  --ink-soft: #5c554b;
  --accent: #1b365d;
  --accent-rgb: 27, 54, 93;
  --ink-rgb: 46, 43, 39;
  --sage-rgb: 122, 155, 118;
  --clay-rgb: 184, 111, 75;
  --border-subtle: rgba(46, 43, 39, 0.06);
  --border: rgba(46, 43, 39, 0.12);
  --border-strong: rgba(46, 43, 39, 0.2);
  --shadow-soft: 0 4px 12px rgba(46, 43, 39, 0.04);
  --shadow-lift: 0 2px 8px rgba(46, 43, 39, 0.07);
  --shadow-float: 0 16px 40px rgba(46, 43, 39, 0.1);
  --shadow-dialog: 0 24px 70px rgba(46, 43, 39, 0.18);
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;
  --sidebar: 252px;
  --context: 304px;
  --font-brand: "Luo", "Noto Serif SC", serif;
  --font-ui: system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
  --font-reading: "Noto Serif SC", "Source Han Serif SC", "Songti SC", "STSong", "SimSun", serif;
  --font-article: "TsangerJinKai02", "Noto Serif SC", "Source Han Serif SC", "Songti SC", serif;
  --font-mono: ui-monospace, "Cascadia Code", monospace;
  --body-font-size: 16px;
  --content-width: 720px;
  --ease-out: cubic-bezier(.22, 1, .36, 1);
  --ease-in-out: cubic-bezier(.77, 0, .175, 1);

  --dur-fast: 120ms;
  --dur-base: 160ms;
  --dur-slow: 220ms;
  --spring-micro: linear(0, 0.52 14%, 0.94 36%, 1);
  --spring-base: linear(0, 0.26 11%, 0.72 31%, 1.01 54%, 1);
  --spring-macro: linear(0, 0.16 8%, 0.5 24%, 0.85 44%, 1.01 68%, 1);
  --spring-press: linear(0, 0.150 6%, 0.445 13%, 0.730 19%, 0.934 25%, 1.020 31%, 1.020 38%, 1.020 44%, 1.020 50%, 1.020 56%, 1.013 63%, 1.000 69%, 0.995 75%, 0.994 81%, 0.996 88%, 0.998 94%, 1.000 100%);
  --spring-pop: linear(0, 0.141 6%, 0.402 13%, 0.644 19%, 0.821 25%, 0.931 31%, 0.989 38%, 1.013 44%, 1.019 50%, 1.017 56%, 1.012 63%, 1.007 69%, 1.004 75%, 1.002 81%, 1.001 88%, 1.000 94%, 1.000 100%);
  --spring-panel: linear(0, 0.088 6%, 0.192 13%, 0.288 19%, 0.376 25%, 0.456 31%, 0.530 38%, 0.597 44%, 0.659 50%, 0.716 56%, 0.768 63%, 0.815 69%, 0.859 75%, 0.899 81%, 0.936 88%, 0.969 94%, 1.000 100%);
  --spring-accent: linear(0, 0.249 6%, 0.697 13%, 1.020 19%, 1.020 25%, 1.020 31%, 1.020 38%, 1.012 44%, 0.970 50%, 0.963 56%, 0.976 63%, 0.993 69%, 1.004 75%, 1.008 81%, 1.006 88%, 1.003 94%, 1.000 100%);
  --surface-0: var(--paper-sunken);
  --surface-1: var(--paper);
  --surface-2: var(--paper-soft);
  --surface-3: var(--paper-soft);
  --hairline: 1px;
  --ring: color-mix(in srgb, var(--ink) 12%, transparent);
  --radius-xs: 2px;
  --radius-control: 10px;
  --radius-panel: 18px;
  --radius-pill: 999px;
  --h-control-sm: 28px;
  --h-control: 36px;
  --h-control-lg: 44px;
```

### 4.7 Tailwind / shadcn 语义 token

保留 v1 的语义映射（background/foreground/card/popover/primary/secondary/muted/accent/destructive/border/input/ring），实现方式是把它们指向 §4.6 的 token；不引入 shadcn 的默认色板。

---

### 4.8 角色令牌与 FUP 命名空间映射 ✅ 裁决完成（2026-10-28）

`docs/FRONTEND_UPGRADE_PLAN.md` §3.2–3.4 引入了一套**并行的 token 语言**（`--spacing-*` / `--text-*` / `--type-*` / `--leading-*`），而 `docs/README.md` §1 规定「冲突以 DESIGN 为准并把结论回写」，FUP §8 又把「token 新命名空间」排在 M2 第一步。不先裁决，M2 一开工就会长出第二套设计系统——这正是 FUP §6.3 自己明令禁止的事。

**实测前置（2026-10-28）**：`--spacing-*` / `--text-*` / `--type-*` / `--leading-*` 在 `web/frontend/src` 全量 grep **0 处引用**（含 `tokens.css` / `app.css` / `*.tsx`）。现在裁决成本最低，M2 落地后就晚了。

**三条裁决原则**

1. **只允许吸收，不允许并存**：被采纳的 FUP 名必须与 `tokens.css`、§4.6 表、`designTokens.test.ts` 的 `OWNED` 同一次提交改完，否则它不是被吸收，而是第二套系统。
2. **同一语义只许一个名字，且契约能判**：判据不是名字新不新。`--text-primary/secondary/tertiary` 可以作**单向别名**（值锁死到既有色）；与现机制重复（`--text-placeholder` ≈ `--faint`、`--surface-raised` ≈ `--surface-2/3`）或**有名无值**（`--leading-*`、`--spacing-5/7/9/10/11`）一律驳回。
3. **FUP 的 token 章节本身不完整，不能整包采纳**：FUP:154 自己写「实施时必须先列完整映射表，不能边写边猜」，但 §3.2 只给 6/12 档间距且 `--spacing-12`（声明 48px）与 2×index 规律（应为 24px）**算术矛盾**；§3.4 的 9 个排版角色只有 6 个有 `--type-*` 名（title / reading / control 缺名）。

**A. 角色色（11）**

| FUP 新名 | DESIGN 现名 | 语义差异 | 裁决 |
|---|---|---|---|
| `--text-primary` | `--ink` #2e2b27 | 同值（12.77:1） | 别名：`--text-primary: var(--ink)` |
| `--text-secondary` | `--muted` #5b544a | 同值（6.77:1） | 别名 |
| `--text-tertiary` | `--faint` #71685c | 同值（4.96:1）；FUP §3.2 表没列它 | 别名 |
| `--text-placeholder` | 无角色名；现 4 处 `::placeholder { color: var(--faint) }`（`app.css:608,798,1253,1685`） | 提议 #6b6256 与 `--faint` 只差 1.09:1，纯增第三级近似色 | **吸收名字、驳回新值**：`--text-placeholder: var(--faint)` |
| `--text-disabled` | 无；禁用靠 opacity（`app.css:553` 0.55、:815 0.55，另有 0.45 @:499 与 1 @:343 漂移） | #8a8175 = 3.48:1，只有 WCAG 1.4.3 禁用态豁免才成立；与 opacity 机制并存 = 两套禁用语言 | **驳回**：保留 opacity，先把 0.45 / 1 收回 0.55 |
| `--action-primary-bg` | 无（§16.2 主按钮直接写 `--blue`） | 值同 #1b365d，但未 token 化 → 暗色主题无法成对覆盖（§18 要求成对） | **需新增** |
| `--action-primary-fg` | 无 | 新信息：`--paper-soft` on `--blue` = 11.51:1 | **需新增** |
| `--action-primary-hover` | 无 token；§16.1 说 hover 用 `--blue-wash`（变浅 1.07:1），但代码 `.btn-sm:hover` 用 `--blue-soft`（变深 7.59:1，`app.css:498`） | **文档与代码已不一致** | **需新增 + 回写 §16.1**：主按钮 hover = `--blue-soft`（跟代码），次要/幽灵按钮 = `--blue-wash` |
| `--action-primary-pressed` | 无（VSP 底稿曾提 #14294a，未入 §4.6） | #142b4b vs #14294a 差 1.02:1，肉眼不可分但契约会打架 | **需新增**取 #142b4b，删除 VSP 的 #14294a 提法 |
| `--focus-ring` | 无统一 token：§16.1 `outline: 2px solid var(--blue-soft)`、§4.4 输入焦点 `color-mix(accent 35%)`、FUP blue 55% | 今天已有三种焦点表达 | **需新增并统一回写 §16.1 与 §4.4**；值沿用 §4.4 的 35% |
| `--surface-raised` | `--surface-0..3`（§4.4；契约 #8 要求是既有纸色别名） | FUP 列了名但**全文无值**；若指浮起卡片就是 `--surface-2/3` | **驳回**：用 `--surface-2/3`，不新增第 5 级 |

**B. 排版（6 名 / 9 角色）**

| FUP 名 | DESIGN 现名 | 语义差异 | 裁决 |
|---|---|---|---|
| `--type-display` | 无（§5.3 页面标题 28–36px） | 32 落在区间内，但 DESIGN 是「区间 + 硬下限」，FUP 是单值 | **需新增**（32px），区间仍由 §5.3 管 |
| `--type-heading` | 无（区块标题 22–28） | 24 ✓ | **需新增** |
| title（§3.4 角色，无 token 名） | 无（区块标题 ≥22） | 20px < 下限 22 | **不映射，需新定义**：抬到 22 或改 §5.3 下限并回写 |
| `--type-body` | `--body-font-size`（用户可调，默认 16px）+ §5.3 正文 16–18 | 值如今同为 16px，但一个是「用户可调的内联覆盖」、一个是「固定值」；FUP §3.2 自己写「用户偏好不能被固定值覆盖」，硬值一旦落地就会吃掉偏好 | **需新增，但值必须是 `var(--body-font-size)`**，16px 只能当下限 |
| `--type-ui` | 无（UI 标签 13–14） | 14 ✓ | **需新增** |
| `--type-caption` | 无（辅助说明 12–13） | 13 ✓ | **需新增** |
| `--type-micro` | 无（硬下限 12，当前 <12px 声明 0） | 12 = 下限，不得再降 | **需新增** |
| reading（§3.4 角色，无 token 名） | `--body-font-size` | 阅读字号必须由偏好驱动；再设 `--type-reading` 就是两个来源争权 | **驳回新增**：reading = `var(--body-font-size)` |
| control（§3.4 角色，无 token 名） | 无（§16.2 按钮 13px/650） | 13 ✓，但它是按钮/标签页唯一权威字号，被漏名 | **需新增** `--type-control: 13px` |

**C. 间距（FUP 12 档 vs DESIGN `--space-1..7` = 4/8/12/16/24/32/48）**

| FUP 名 | DESIGN 现名 | 语义差异 | 裁决 |
|---|---|---|---|
| `--spacing-1`（2px） | 无 | 2px 是 §6.4 明确排除的（例外 ≤2px 只允许图标光学对齐裸写） | **不映射** |
| `--spacing-2`（4px） | `--space-1` | 值同，**序号错位**（新 2 = 旧 1），迁移期最易写错 | 别名 |
| `--spacing-4`（8px） | `--space-2` | 值同 | 别名 |
| `--spacing-6`（12px） | `--space-3` | 值同 | 别名 |
| `--spacing-8`（16px） | `--space-4` | 值同 | 别名 |
| `--spacing-12`（48px） | `--space-7` | 仅此档对得上，但 FUP 代码块 1:2/2:4/3:6/4:8/6:12/8:16 是 2×index 规律 → 12 应为 24px，**算术矛盾** | **需新增，但必须先出完整 12 档表**；48 保留 |
| `--spacing-3`（6px） | 无 | 无档 | **需新增**（先证明有真实用法，否则驳回） |
| `--spacing-5/7/9/10/11` | 无 | **FUP 全文无值** | **不映射，需新定义** |
| 「`--space-N: var(--spacing-M)`」改造 | `--space-1..7` | 会**打破契约 #1**：测试逐字比对文档值与 `:root` 值，文档写 `4px`、代码写 `var(--spacing-2)` 即 fail | 别名保留，但必须同批：①§4.6 写成 `var()` 形式 ②测试加 `var()` 展开 ③`OWNED` 增补 |

**D. 行高**

| FUP 名 | DESIGN 现名 | 语义差异 | 裁决 |
|---|---|---|---|
| `--leading-tight/ui/body/reading` | 无 token（只有「正文行高 1.7–1.9」） | FUP **只给名字不给值**；VSP 底稿有 1.3/1.5/1.7/1.85（1.85 ∈ 1.7–1.9 ✓） | **需新增**，值以 VSP 四档为候选，**写死前不得入表**（空名 = 第二套占位） |

**E. 无新名字段（沿用，但要回写一处）**

| FUP 段 | 现状 | 裁决 |
|---|---|---|
| 基础色 5 个举例 | 同名（§4.1/§4.6） | 沿用 |
| `--radius-*` + 补充角色 | 同名 + `--radius-xs/control/panel/pill`（4 档预留、实测 0 使用，§7.1） | 沿用；但 FUP「不追求把例外清成零」与 §16.3 #4「直到归零」相抵 → §16.3 改「不再新增，预算冻结」（2026-10-28 已把预算收到实测值 58） |
| `--ease-*` / `--dur-*` / `--spring-*` | 同名（7 个 spring；§11.3 表列 4 个物理弹簧） | 沿用；§11.3 表名已按实际改为 press/pop/panel/accent |
| `--body-font-size` / `--content-width` / `data-theme` / `data-motion` | 同名（§4.6 / §9.12 / §11.6） | 沿用，禁止出现固定值 shadow（尤其 `--type-body`） |

**4.8.1 契约：怎么禁止新组件同时引用两套命名**

正则层（零新依赖，沿用 `designTokens.test.ts` 风格，4 条）：

1. **前缀封闭**：源码里出现 `--spacing-` / `--text-` / `--type-` / `--leading-` 的名字必须在 §4.6 表里（复用现有 undocumented 检查）。
2. **别名单向**：允许 `--space-N: var(--spacing-M)`，反向必须为 0。
3. **同文件不混用**：同一文件不得同时出现两套间距名。
4. **同值别名棘轮**：`:root` 里解析值相同的 token 名数量 ≤ 基线（白名单 `--space-*` / `--surface-*` / `--parchment` / `--accent`）。

AST 层（更准，需把 postcss 显式列为 devDependency）：`walkDecls` 只读 `decl.value` 里的 `var()` 与裸值，天然跳过注释与字符串，并能做别名闭包判断「组件写 `--space-1` 实际落在新刻度上」。

**明确抓不到（必须承认）**：`var()` 解析链（组件写旧名实际落到新刻度 → 假阴性，需别名闭包）；跨文件层叠（同一页面两棵子树各用一套，得靠 computed style / e2e）；动态名（`var(--spacing-${n})`、`style={{}}` 拼接 → 建议直接禁止用模板拼 token 名）；同值同义重复（只能靠同值棘轮兜一部分）；暗色覆盖只验存在不验对比度 → 新角色必须并进 `themeContrast.test.ts`。

**4.8.2 落地清单（必须同一提交，顺序不可反）**

1. `docs/DESIGN.md`：§4.6 表追加角色 / 排版 / 行高 / 新间距；本文 §4.8；并回写 §16.1（hover 深浅、focus 环）、§4.4（focus 值）、§11.3（弹簧名）、§16.3 #4（圆角表述）。
2. `web/frontend/src/styles/tokens.css`：`:root` 与 `[data-theme="dark"]` 成对新增。
3. `web/frontend/src/lib/designTokens.test.ts`：`OWNED` 增补 + 新增 4 条契约 + `var()` 展开。
4. **顺序不可反**：先给测试加 `var()` 展开，再把 `--space-*` 改成别名；否则契约 #1 的逐字比较会全线失败（文档 `4px` vs 代码 `var(--spacing-2)`）——这是本方案唯一的高危步骤。

**风险**：`--type-body` 若写成 16px 硬值，会覆盖 `--body-font-size` 的用户偏好能力（当前前端唯一已实现的个性化开关）；本轮只定名字与字号，值一律走 `var(--body-font-size)`。

## 5. 排版

### 5.1 字体气质

编辑部感，不是 SaaS 仪表盘感：标题有阅读感，正文长时间舒适。

- 品牌名与少量固定展示标题：**Luo**，形成识别。
- 导航、按钮、输入框、标签、会话列表、设置项：**系统中文黑体栈**，保证字形完整与高频效率。
- AI 回答、资料正文、Wiki、阅读器：**Noto Serif SC**，安静的长文阅读区。
- 模型名、路径、代码、技术标识：**等宽**。
- 不依赖浏览器合成 Luo 粗体；需要粗体的 UI 用系统黑体，正文粗体由 Noto Serif SC 承担。

### 5.2 字体 token

| token | 栈 | 用途 |
|---|---|---|
| `--font-brand` | Luo → Noto Serif SC → serif | 品牌名、短标签 |
| `--font-ui` | system-ui → PingFang SC → Microsoft YaHei → sans-serif | 全部 UI |
| `--font-reading` | Noto Serif SC → Source Han Serif SC → Songti SC → SimSun → serif | AI 回答、正文 |
| `--font-article` | TsangerJinKai02 → Noto Serif SC → … → serif | 阅读器文章 |
| `--font-mono` | ui-monospace → Cascadia Code → monospace | 代码、路径 |

阅读字体可切换：`[data-reading-font="jin-kai"]` / `[data-reading-font="noto-serif"]`。

### 5.3 字号层级与硬下限

| 场景 | 字号 |
|---|---|
| 官网 H1 | 44–64px（移动 34–42px） |
| 页面标题 | 28–36px |
| 区块标题 | 22–28px |
| 正文 | 16–18px（默认 `--body-font-size: 16px`，随设置偏好 15/16/17/18） |
| UI 标签 | 13–14px |
| 辅助说明 | 12–13px |

**硬下限（由契约测试执行）**：辅助说明 ≥ 12px、UI 标签 ≥ 13px、正文 16–18px。当前低于 12px 的声明数 **= 0** ✅。

规则：字重多用 500/600，字距保持 0（不用负字距），正文行高 1.7–1.9，阅读宽度 680–760px。

### 5.4 字体加载、分片与子集化 ✅ 已落地（M5，2026-10-17）

Bobodan 是 local-first 产品：**字体必须随包分发**，运行时禁止依赖 jsDelivr / Google Fonts 等公共 CDN；加载失败必须自然回退到本地系统字体。

| 资源 | M5 前 | 现状（2026-10-28 实测） |
|---|---|---|
| Noto Serif SC | 100 个 unicode-range 分片写在主 CSS | 分片保留（约 5.7MB，按需加载）；face 声明移到独立 `fonts-*.css` 延迟加载 ✅ |
| 仓耳今楷 W04/W05 | 2 × 18.5MB TTF = 36.1MB ✗ | **GB2312 子集 woff2 3.83MB**（pyftsubset，7543 字，**−89%**）；进入阅读器时才加载 ✅ |
| Luo | ~327KB | 保留（只做品牌与短标签，禁止做长文唯一字体）✅ |

**许可**：Noto Serif SC 按 SIL OFL 分发；Luo 保留原许可说明；仓耳今楷参考 Kami 实现，公开分发桌面包前需再次核对作者条款与署名（见附录 B）。

### 5.5 中西混排与标点 🟡 计划中（M3）

- 中文与英文/数字之间**不手动加空格**，交给字体的字面间距与 `text-spacing-trim`（支持的浏览器）。
- 数字在表格与统计里用 `font-variant-numeric: tabular-nums`，避免跳动。
- 中文引号用「」，书名号用《》，英文引用用 “ ”，不在同一段混用两套引号。
- 句末标点只用一个；不写 `。。`、`，，`。

---

## 6. 空间与布局

### 6.1 页面节奏

页面 = 顶栏 + 主内容 + 可选停靠栏；区块之间用 `--space-5` / `--space-6` 分隔，同一屏不要超过 3 种间距。

### 6.2 栅格

三栏：侧栏 `--sidebar: 252px` / 主内容 `--content-width: 720px` / 上下文 `--context: 304px`；主内容居中，两侧留白由容器吸收。

### 6.3 响应式尺寸

| 断点 | 行为 |
|---|---|
| ≥ 1280px | 三栏完整 |
| 960–1279px | 收起上下文栏 |
| < 960px | 单栏 + 抽屉式侧栏（本轮不做移动端实现，但布局不得破） |

### 6.4 间距刻度

只用 `--space-1…7`（4/8/12/16/24/32/48），不写裸 px；例外只在图标与文字的光学对齐（≤2px）。

### 6.5 高度阶梯 ⚠️ 已入表未接入（2026-10-28 按代码校正）

`tokens.css` L119-121 实际只有三档；旧版本文列的 `--h-control-xs` / `-md` / `-xl` 与 `--h-topbar` **在 `tokens.css` 中不存在**，属规划残留：

| token | 值 | 当前状态 |
|---|---|---|
| `--h-control-sm` | 28px | 已定义，样式里 **0 处引用** |
| `--h-control` | 36px | 已定义，样式里 **0 处引用** |
| `--h-control-lg` | 44px | 已定义，样式里 **0 处引用** |

**怎么读这张表**：这三条是给组件层预留的公共阶梯，§16.3 契约 #10 只要求它们「入 `:root` 且入 §4.6 表」，目前没有任何组件在用。真实的可点高度下限仍写在组件规则里（§16.2：主按钮 ≥40px、输入框 ≥36px、列表行 ≥44px）。**新增组件真用上阶梯后再回来更新本表，不要让本文声称已在用。**

### 6.6 阅读行宽

正文容器宽 `--content-width`（720px），长文单行 32–40 个汉字；超过 40 字要加宽行高或分栏。

---

## 7. 形状与光影

### 7.1 圆角矩阵（2026-10-28 按代码实测校正）

值全部来自 `tokens.css` L50-53 / L113-116；「使用次数」是 `grep -ro "var(--radius-*)" web/frontend/src` 的实测结果：

| 档 | token | 值 | 实测使用次数 | 用在哪 | 状态 |
|---|---|---|---|---|---|
| XS | `--radius-xs` | 2px | 0 | 角标、聚焦环内衬（预留） | ⚠️ 入表未使用 |
| SM | `--radius-sm` | 6px | 29 | chip、kbd、小标签、选项行 | ✅ |
| MD | `--radius-md` | 8px | 39 | **标准按钮、输入框、下拉项** | ✅ 主用档 |
| LG | `--radius-lg` | 12px | 3 | 卡片、代码块、浮层、设置卡片 | ✅ |
| XL | `--radius-xl` | 16px | 3 | 弹窗、大号胶囊控件 | ✅ |
| Control | `--radius-control` | 10px | 0 | 密集控件（预留） | ⚠️ 入表未使用 |
| Panel | `--radius-panel` | 18px | 0 | 子面板（预留） | ⚠️ 入表未使用 |
| Pill | `--radius-pill` | 999px | 0 | 分段控件、状态呼吸点（预留） | ⚠️ 入表未使用 |

**规则**：

- 写样式前先看「使用次数」列——今天**只有 sm / md / lg / xl 在用**；其余四档是 §16.3 契约 #10 要求存在的预留档，真接入了再回来更新本文次数。
- 旧版本文列出的 `--radius-bubble`（18px 用户消息气泡）**不存在于 `tokens.css`**；用户消息气泡的真实样式是 `--radius-md --radius-md 2px`（右下角切角），见 §16.2。
- 同心圆角公式（内层半径 = 外层半径 − 内距）是原则，但 `--radius-card` 尚未落地成 token，需要时用 `calc()` 就地写。

### 7.2 表面与高度

| token | 用在哪 | 层级 |
|---|---|---|
| `--shadow-soft` | 内容轻度抬升 | 1 |
| `--shadow-lift` | hover / 选中 | 1 |
| `--shadow-float` | 浮层、菜单 | 2 |
| `--shadow-dialog` | 弹窗、抽屉 | 3 |

**配额**：内容区每屏抬升 ≤ 1 处；浮层必须同时有发丝边，不能只靠阴影。

### 7.3 边框与发丝边

三档 `--border-subtle` / `--border` / `--border-strong` + 已落地的 `--hairline`（1px，2dppx 下减半）与 `--ring`（`color-mix` 发丝外环）——见 §4.5，**M3 ✅ 已实施**；契约测试看住它们必须同时出现在 `:root` 与 §4.6 表里。

### 7.4 遮罩与羽化 ✅ 已落地（M3）

长滚动容器（会话栏、资料树、正文滚动区）在滚动方向做**非线性羽化遮罩**：

```css
mask-image: linear-gradient(to bottom, transparent 0, #000 12px, #000 calc(100% - 12px), transparent 100%);
```

优先用 `animation-timeline: scroll()` 让遮罩随滚动渐显；不支持的浏览器静态降级。遮罩只做视觉，不拦截事件。

**实现位置（2026-10-28 核对）**：`.settings-nav` 与 `.providers-list` 已用 `@supports (mask-image: …)` 包裹羽化遮罩，不支持时静态无遮罩；由 `designTokens.test.ts` 的「长列表滚动遮罩存在且可降级」看住。

---

## 8. 网站设计规则

### 首屏

首屏只回答三个问题：这是什么、能帮我学什么、现在从哪开始。一句主张 + 一个主行动，不堆特性列表。

### 内容结构

每段一个观点；小标题用陈述句；数字与结论放前面；不写「赋能 / 一站式 / 极致」这类空词。

### 图片

品牌插图只用于空态与引导；截图必须带真实界面；图片不得是装饰性光球或渐变块。

---

## 9. Web UI 设计规则

### 9.1 核心组件规范

所有可点元素必须四态齐全（见 §16.1）；所有容器只从 §4.6 取色；所有间距只从 §6.4 取档。

### 9.2 Composer 与状态层级

三层结构见 §3.3 Chat。补充规则：

- 自建主题化下拉（`DropdownSelect`），原生 `<select>` 的下拉面板无法跟随暖纸主题；
- 流式回答期间模型不可切换，发送按钮变停止图标；
- `@资料` / `@会话` 用 textarea + 结构化 chip，不引入富文本编辑器；
- 引用菜单支持搜索、Tab、方向键、Enter、Esc；引用可恢复、可移除、可跳转；
- **CJK 输入法守卫 🟡（M4）**：`compositionstart` 到 `compositionend` 之间忽略 Enter/Esc/方向键快捷键，命中输入法候选时不许发送。

### 9.3 消息与回答

回答区像文章：行高 1.85、段落间距 0.8em、标题用阅读字体；过程信息（工具、检索、状态）折叠在正文之下，不打断阅读。

**流式状态**：只显示「正在读取 / 检索 / 组织 / 生成」等中文状态，**不显示原始思维链**。

### 9.4 来源与可信度

来源 chip 必须标注类型：本地资料 / 本地扩展 / 网页来源 / AI 补充 / 待核实；**状态必须同时用文字 + 视觉**，不能只靠颜色。

### 9.5 导航

一级导航：对话 / 练习 / 复习 / 知识地图 / 笔记 / 资料库（六项，见 §3.1）；当前项用墨蓝体系，不用 sage 当选中态；不设低权重的 Workbench 入口（该概念已退役，2026-10-28 校正）。

### 9.6 按钮

| 类型 | 表面 | 边框 | 圆角 | 字号 | 高度 |
|---|---|---|---|---|---|
| 主按钮 | `--blue` | 同色 | `--radius-md` | 13px / 650 | ≥ 40px |
| 次要按钮 | 透明 → hover `--blue-wash` | `--border-strong` | `--radius-md` | 13px / 650 | ≥ 40px |
| 图标按钮 | 透明 → hover `--blue-wash` | hover 时 `--border-subtle` | `--radius-md` | — | 36–40px 方形 |

### 9.7 卡片

卡片 = `--paper-soft` + `--border` + `--radius-lg` + `--space-4` 内距；正文 ≥13.5px。嵌套表面每屏 ≤1 层。

### 9.8 输入框

`--paper-soft` 表面 + `--border-strong` + `--radius-md` + 高度 ≥36px（Composer ≥40px）；focus 用 `outline: 2px solid var(--blue-soft)`，不许 `outline: none`。

### 9.9 状态反馈

四类状态必须都有：加载（骨架/文字，不闪）、空（说明 + 下一步）、错误（原因 + 可行动作 + 不丢输入）、完成（明确的收尾语言）。

### 9.10 关键页面状态

| 页面 | 空态 | 错误态 |
|---|---|---|
| Chat | 引导语 + 建议问题 | 连接条 + 重试 |
| Library | 导入引导 | 索引损坏提示 + 重建入口 |
| Practice | 无题库时给生成入口 | 批改不可用 ≠ 答错 |
| Review | 今日无到期 → 鼓励语 | 队列读取失败 + 重试 |

### 9.11 Library 与 Wiki 编排

资料树是主入口；概念图谱只做局部辅助；Wiki 是高级维护，不做一级导航，也不做默认 RAG 中间层。

### 9.12 可访问性与主题策略

正文对比度 ≥4.5:1、焦点环可见、键盘可达、减少动效生效、色盲不依赖颜色单一表达；主题切换只翻 `[data-theme]` 下的 token，不用 React 状态改色。

### 9.13 页面验收清单

每个页面交付前必须能回答：空/加载/错误/完成四态是否都有？键盘能走完主流程吗？窄窗口不破版吗？用的是 token 而不是裸值吗？

---

## 10. TUI 设计规则

TUI 只服务开发与诊断，不做装饰。

### 10.1 配色

背景用纸色深一档、正文 `--ink`、强调墨蓝；状态三色（绿=成功 / 黄=警告 / 红=错误）只用于状态词，不做 256 色装饰。

### 10.2 布局

固定栅格；单屏信息块 ≤5 块；表头常驻；长输出分页而不是刷屏。

### 10.3 文案

短句 + 命令示例；错误必须给下一步命令；不打印原始思维链与 Trace。

---

## 11. 动效与交互物理

### 11.1 原则

动效只用于帮助理解状态，不用于炫技；只过渡 `opacity` / `transform` 等低成本属性；高频键盘菜单不加明显开关动画。

> **M4 物理弹簧（2026-10-17）**：`--spring-press/pop/panel/accent` 由参考仓库的 k/c/m 常数做**数值积分**生成 `linear()`（press 600/30/m1、pop 320/28/m1、panel 1200/80/m0.1、accent 380/18/m1），原始过冲 8.9% / 2% / 0% / 19.5%，统一**压到 ≤2%**（曲线停靠值上限 1.02）；契约测试在 `designTokens.test.ts` 的「M4 弹簧曲线契约」。
> **时长口径（2026-10-28 更正）**：曲线是按各自稳定窗口（408 / 559 / 91 / 667ms）积分的，但落地时统一被压缩进 `--dur-fast` / `--dur-base` / `--dur-slow`（120 / 160 / 220ms）。**界面上的实际时长是令牌时长，不是稳定窗口** —— 旧 CHANGELOG 里「稳定窗口」的说法只描述采样口径，不代表屏幕上的时长。

### 11.2 时长与曲线 token

| token | 值 | 用在哪 |
|---|---|---|
| `--dur-fast` | 120ms | 按压、微反馈 |
| `--dur-base` | 160ms | 状态变化、hover |
| `--dur-slow` | 220ms | 弹窗、浮层入场 |
| `--ease-out` | cubic-bezier(.22, 1, .36, 1) | 进入、出现 |
| `--ease-in-out` | cubic-bezier(.77, 0, .175, 1) | 持续移动 |
| `--dur-spin` / `--dur-ink` / `--dur-ink-soft` / `--dur-enter` | 900 / 1350 / 1250 / 500ms | 循环与入场动画的专用时长（与三档梯度语义不同，单独命名）；`--delay-ink-a/b` = ∓180ms 用于墨点错峰 |

规则：不写裸 ms、不写第三条贝塞尔、不用起步迟缓的 ease-in。

### 11.3 弹簧物理（4 套常数 → CSS `linear()`）✅ 已落地（M4，2026-10-17）

参考 CDS 的生产常数，映射到 CSS 曲线（**过冲一律 ≤2%**，不采用 +19% 的 bouncy 预设）。实际 `linear()` 在 `tokens.css` L86-89，契约测试见 `designTokens.test.ts` 的「M4 弹簧曲线契约」：

| token | 物理来源（stiffness / damping / mass） | 用在哪 | 配哪档时长 | 过冲（原始 → 压后） |
|---|---|---|---|---|
| `--spring-press` | 600 / 30 / 1.0 | 按钮、开关、checkbox 按压 | `--dur-fast` | 8.9% → ≤2% |
| `--spring-pop` | 320 / 28 / 1.0 | 选中态、行展开、卡片抬升 | `--dur-base` | 2% → ≤2% |
| `--spring-panel` | 1200 / 80 / 0.1 | 浮层/面板入场、面板停靠 | `--dur-slow` | 0% |
| `--spring-accent` | 380 / 18 / 1.0 | 强调态、一次性提示 | `--dur-slow` | 19.5% → ≤2% |

**用法**：`transition: transform var(--dur-fast) var(--spring-press)`；缩放只允许 0.96–1.02。

**两条容易踩的坑（旧版本文写错的地方）**：

1. `tokens.css` 里另有 `--spring-micro` / `--spring-base` / `--spring-macro`（L85 / L90 / L91）三条**早期手写近似曲线**，语义只是「快 / 中 / 慢」，没有物理常数来源。它们和上表四条不是同一套东西，新代码优先用上表四条。
2. `--spring-snap` **尚未落地**（`tokens.css` 无此 token）。拖拽松手吸附/面板停靠真要做时，按 1200 / 80 / 0.1 生成 `linear()` 再入表入契约，不要写裸 `cubic-bezier`。

### 11.4 手势、指针与滚动 🟡 计划中（M4）

- **指针死区 4px**：按下后位移 <4px 视为点击，不进入拖拽（知识图谱、可拖拽面板）。
- **拖拽吸附**（🟡 未实现）：松手用吸附曲线停到目标位（`--spring-snap` 尚未落地，见 §11.3）；不许有持续跟随的惯性漂移。
- **滚动单写者** ✅ 已落地：所有自动滚动集中在 `useStickyBottomScroll` 的 `step()`，一帧最多写一次 `scrollTop`；手势期间零写入；只有「用户发消息」才 `pinToBottom()`。

### 11.5 输入法（IME）与键盘

- 合成期间不触发任何快捷键（见 §9.2）；
- Enter 发送、Shift+Enter 换行、Esc 关闭浮层/中断输入法；
- 所有浮层必须支持 Esc 与焦点返回触发元素。

### 11.6 减少动态效果

应用内开关与 OS `prefers-reduced-motion` 同义：关闭装饰性动画与自动滚动，只保留短淡入与必要颜色反馈；JS 动画实时读取开关（`lib/motion.ts`），不做挂载时快照。

### 11.7 禁止项

弹跳、强缩放、粒子、频闪、自动播放的大段动画、`transition: all`、从 `scale(0)` 出现、整页视差。

### 11.8 外部动效库边界（Motion 受限使用，2026-10-21 拍板）

排期决策记录在 `ROADMAP.md` §3「已拍板决策」（2026-10-21「Motion 改为受限使用」）。本文的执行口径：

- **允许**：复杂弹窗/抽屉的进出场、消息出现、布局变化、有意义的拖拽反馈。
- **必须**：`LazyMotion` + `m` 组件、按需加载；不许把整包 Motion 打进首屏。
- **禁止**：全局 `<AnimatePresence>` 包装、全站铺动画、Motion 与 CSS 同时控制同一属性。
- **继续用 CSS token**：hover、焦点环、骨架屏、短状态过渡一律留在 CSS。

§11.1–§11.7 的时长口径、曲线与禁止项对两种实现同时有效——**引入 Motion 不等于放宽过冲≤2% 与禁止项**。


像一位耐心的同学，不是客服也不是导师：短句、具体、不居高临下；承认不确定；不承诺没做到的事。

- 用「我们」而不是「您」；不用感叹号堆情绪。
- 错误信息说人话：发生了什么 → 为什么 → 现在怎么办。
- 人设可配置，但**不得**覆盖来源标注、AI 补充、待核实状态。

示例：

- 「资料里没找到直接依据，我先按已有笔记给一个暂定答案，并标注『待核实』。」
- 「这一步失败了：资料索引还没建立。先运行一次同步，再问一次。」

---

## 13. 组件检查清单

每次新增或修改组件前逐条检查：

- [ ] 背景暖而不白；文字深咖啡而非纯黑。
- [ ] 主色是墨蓝；绿色只做辅助；橘棕只做点缀。
- [ ] 用的是 §4.6 的 token，没有裸色值/裸字号/裸间距。
- [ ] 表面层级正确（Surface 0–3），没有卡片套卡片。
- [ ] 有发丝边或明确边界，不是靠阴影撑结构。
- [ ] 四态齐全（静置/hover/active/focus-visible/disabled）。
- [ ] 高度 ≥40px（列表行 ≥44px），热区补足。
- [ ] 动效只用 token 曲线，过冲 ≤2%，减少动效可关闭。
- [ ] 中文输入法下快捷键不误触发。
- [ ] 空/加载/错误/完成四态明确且不跳版。
- [ ] 来源 chip 文字 + 视觉双标注。
- [ ] 键盘可达、焦点可见、对比度达标。
- [ ] 字体与图标可离线加载。

---

## 14. 反模式与配额

### 底线（绝对禁止）

- 暗黑终端风 / 冷白科技风 / 极客工具风 / 企业后台风 / 金融高密度风
- 用颜色作为来源、正确性或状态的唯一表达
- 装饰性光球、渐变球、bokeh 背景
- 运行时依赖公共字体 CDN
- 用滤镜反转或纯黑背景拼暗色模式
- Agents / MCP / Logs 占据首页主舞台
- 把 Practice 做成高密度题库后台、把 Review 做成数据看板
- 用人设语气掩盖来源或待核实状态
- 整页主题化（整页变绿/变棕/变粉）

### 配额（可以有，但有上限）

| 项 | 配额 |
|---|---|
| 嵌套表面 | 内容区每屏 ≤1 层 |
| 抬升 `--shadow-lift` | 内容区每屏 ≤1 处 |
| 玻璃效果 | 仅吸顶 topbar 与浮层，blur ≤16px |
| 胶囊/大圆角 | chip 与分段控件可用，≤ `--radius-pill`；不做页面级按钮语言 |
| 彩色面积 | 按 §4.3 |
| 渐变 | 同色相、明度差 ≤8%；禁止跨色相渐变；每屏 ≤1 处 🟡 |
| 纯图标控件 | 工具栏级允许；面板级必须带文字或 tooltip |
| 可爱化 | 只允许品牌插图与空态，不进入控件与文案 |
| 滚动遮罩 | 只用于长列表边缘，宽度 ≤16px，不拦截事件 🟡 |

---

## 15. 一句话标准

> 暖米色纸张上的一套安静学习工具，中文排版有风骨，墨蓝负责阅读秩序，橘棕负责温度，植物绿负责自然气息，少量花瓣粉负责私人情绪，信息像杂志一样被认真排版。

---

## 16. 组件规格与交互四态

### 16.1 交互四态（所有可点元素都必须有）

| 态 | 要求 |
|---|---|
| 静置 | 明确边界：`--border-strong`（次要）或实色底（主要） |
| hover | 底色变化（`--blue-wash` 或 `--paper-soft`）+ 抬升 `--shadow-lift` |
| active | 按压反馈：`transform: scale(0.96–0.98)` 或底色加深一档 |
| focus-visible | `outline: 2px solid var(--blue-soft)`，`outline-offset: 2px`；不得用 `outline: none` 覆盖 |
| disabled | `opacity: .55` + `cursor: not-allowed`；不得只变灰而不禁用 |

### 16.2 组件规格表

> §16.2 校准（M3 ✓）：表内关键组件的圆角已**全部令牌化**（`.composer` / `.settings-dialog` / `.notice` / 输入区浮层 / 两个搜索框 → `var(--radius-md)`；7px 的旧值对齐到刻度 8）。契约测试：`designTokens.test.ts` 的「M3 组件规格校准」。

| 组件 | 表面 | 边框 | 圆角 | 内距 | 字号 | 高度 | 四态 |
|---|---|---|---|---|---|---|---|
| 页面容器 | `--paper` | 无 | — | `--space-6` 40px `--space-7` | — | — | §16.1 |
| 停靠栏（侧栏/右栏） | `--paper-sunken` | `--border` 竖线 | — | `--space-4` 起 | 标签 ≥12px | — | §16.1 |
| 顶栏 | `--paper` + blur ≤16px | `--border-subtle` 下边 | — | 横向 `--space-4` | 标题 17px | 68px | §16.1 |
| 卡片 | `--paper-soft` | `--border` 或发丝边 | `--radius-lg` | `--space-4` | 正文 ≥13.5px | — | §16.1 |
| 列表行 | 停靠面透明行 | `--border-subtle` 分隔 | `--radius-md` | `--space-2` `--space-3` | ≥13px | ≥44px | §16.1 |
| 主按钮 | `--blue` | 同色 | `--radius-md` | 0 13px | 13px/650 | ≥40px | §16.1 |
| 次要按钮 | 透明 → hover `--blue-wash` | `--border-strong` | `--radius-md` | 0 13px | 13px/650 | ≥40px | §16.1 |
| 图标按钮 | 透明 → hover `--blue-wash` | hover `--border-subtle` | `--radius-md` | — | — | 36–40px | §16.1 |
| 输入框 | `--paper-soft` | `--border-strong` | `--radius-md` | 0 `--space-3` | ≥13px | ≥36px | §16.1 |
| chip / 标签 | `*-wash` 或 ink 5% | 无 | `--radius-sm` | 0 `--space-2` | ≥12px | ≥24px | §16.1 |
| 状态块 | `*-wash` | 左边框 3px 同色 | 0 `--radius-sm` `--radius-sm` 0 | `--space-3` `--space-4` | ≥13.5px | — | §16.1 |
| 浮层 | `--paper-soft` | `--hairline` 外环 | `--radius-lg` | `--space-2` | ≥12.5px | — | §16.1 |
| 弹窗/抽屉 | `--paper-soft` | `--border` 或发丝边 | `--radius-xl` | `--space-5` | — | — | §16.1 |
| 用户消息气泡 | `rgba(232,237,243,.68)` | `rgba(27,54,93,.12)` 1px | `--radius-md --radius-md 2px`（右下切角） | `--space-3` `--space-4` | 16px/500 | — | `app.css:692` |

### 16.3 契约测试（分两层：L1 文本 / L2 计算样式）

契约测试是**会失败的测试**，不是口号。但要分清它能证明什么（2026-10-28 补充）：

- **L1 文本契约**：vitest 读 CSS / 组件源码做字符串比对。它只能证明「文档与源码文本一致」，证明不了浏览器里生效的是哪个值。
- **L2 计算样式契约**：Playwright `getComputedStyle` 读真实渲染值。它才证明「用户看到的就是这个值」。

两层都要有：L1 便宜、能在提交前跑；L2 贵、但能抓住层叠覆盖（.reader-prose 的字号曾被硬编码 16px / 18px 覆盖，L1 一无所知）。

#### 16.3.1 核心契约（编号稳定，正文按这些编号引用）

| # | 契约 | 状态 |
|---|---|---|
| 1 | §4.6 token 表与 `styles/tokens.css` `:root` 同名同值；OWNED 命名空间的 token 必须全部入表 | ✅ |
| 2 | 低于 12px 的 `font-size` 必须为 0 | ✅（预算 0，实测 0） |
| 3 | 裸缓动（裸 `ease` / 裸 `cubic-bezier`）数量 ≤ 预算，只减不增 | ✅（**预算 0**，实测 0；2026-10-28 前预算是 15，注释写归零但常量没改，已修） |
| 4 | 不在圆角刻度上的 `border-radius` 数量 ≤ 预算，只减不增 | ✅（**预算 58 = 实测值**，2026-10-28 由 60 收到精确值；不再宣称「直到归零」——存量非刻度值是有意的历史遗留） |
| 5 | 裸毫秒值数量 ≤ 预算，只减不增 | ✅（预算 0，实测 0） |
| 6 | 字体栈以通用族收尾；UI/阅读/文章字体显式点名 CJK；长文正文不用品牌字体；无公共 CDN；`@font-face` 只用本地 URL | ✅ |
| 7 | 存在一条把 button/input/textarea/select 一起设为 `font: inherit` 的规则 | ✅ |
| 8 | 表面阶梯（`--surface-0..3`）必须是既有纸面色的**别名**，不得引入新色值 | ✅（M3） |
| 9 | `--hairline` / `--ring` 必须入 `:root` 与 §4.6 表；2dppx 下 `--hairline` 减半 | ✅（M3） |
| 10 | 高度阶梯（`--h-control-*`）与圆角补充令牌（`--radius-xs/control/panel/pill`）入表；§7 圆角棘轮不受影响 | ✅（M3） |

#### 16.3.2 L1 文本契约全量登记（52 条）

**`web/frontend/src/lib/designTokens.test.ts`（34 条，10 个 describe）**

| # | 契约 | 用例 | 预算 vs 实测 |
|---|---|---|---|
| 1 | 文档 token 表每条等于 `:root` 同名 token | L81 文档 token 表里的每一条都等于 :root 里的同名 token | — |
| 2 | OWNED 命名空间的 token 都写进文档 | L92 代码里属于规格命名空间的 token 都写进了文档 | — |
| 3 | 无 fallback 的 `var(--x)` 必须真的定义过 | L101 没有 fallback 的 var(--x) 必须在样式里真的定义过 | — |
| 4 | 低于 12px 的 `font-size` 数为 0 | L114 低于 12px 的 font-size 必须是 0（§5 硬下限） | 0 / 实测 0 |
| 5 | 裸 `ease` 数量 ≤ 预算 | L127 用裸 ease 关键字的过渡数量不超过预算 | **0 / 实测 0** |
| 6 | 非刻度圆角数量 ≤ 预算 | L138 不在 §7 刻度上的 border-radius 数量不超过预算 | **58 / 实测 58** |
| 7 | 过渡/动画裸毫秒值为 0 | L148 过渡/动画里的裸毫秒值必须是 0 | 0 / 实测 0 |
| 8 | 纸张阶梯顺序：停靠面 < 画布 < 抬升面 | L203 | — |
| 9 | 纸张阶梯每通道差 ≤ 8/255 | L208 | 8 / 实测 ≤8 |
| 10 | 停靠面更灰、不比画布更黄 | L220 | — |
| 11 | 每个字体栈以通用族收尾 | L235 | — |
| 12 | UI 与阅读字体显式点名 CJK | L250 | — |
| 13 | 长文正文不用品牌字体 | L259 | — |
| 14 | 字体本地打包、CSS 不引公共 CDN | L271 | — |
| 15 | 表单控件（含 select）继承页面字体 | L282 | — |
| 16 | 表面阶梯是既有纸色别名 | L298 | — |
| 17 | 发丝边与外环入 `:root` 且在 2dppx 下减半 | L309 | — |
| 18 | 高度阶梯与圆角补充令牌齐全、圆角棘轮不受影响 | L316 | — |
| 19 | §4.6 表同步列出所有 M3 令牌 | L330 | — |
| 20 | 关键浮层用 `--hairline` + `--ring` 外环 | L357 | — |
| 21 | 菜单与通知不再用硬 `rgba` 描边 | L377 | 0 / 实测 0 |
| 22 | 关键表面按阶梯使用 `--surface-N` | L399 | — |
| 23 | 四个表面层都真实使用（不是只定义） | L411 | — |
| 24 | composer 用 `surface-3` + 发丝边 + 外环，不用裸 `rgba` 描边 | L419 | — |
| 25 | 设置字段背景走 `surface-3`、焦点色走 token | L427 | — |
| 26 | 长列表滚动遮罩存在且可降级 | L434 | — |
| 27 | 每屏背景渐变 ≤ 3 处（遮罩不计） | L438 | 3 / 实测 3（app.css 纹理 + composer 渐隐 + 骨架屏微光） |
| 28 | 关键组件圆角走令牌，不写字面量 | L445 | — |
| 29 | 四个物理弹簧在 `:root` 且都是 `linear()` 曲线 | L467 | — |
| 30 | 曲线过冲 ≤ 2% | L474 | 2% / 实测 ≤2% |
| 31 | 弹簧曲线真实用在过渡/动画上 | L483 | — |
| 32 | 暗色主题覆盖全部关键语义令牌 | L495 | — |
| 33 | 暗色只翻颜色，不重定义字体/圆角/动效 | L501 | — |
| 34 | 高对比只强化文字与描边 | L507 | — |

**`web/frontend/src/lib/themeContrast.test.ts`（5 条）**：浅色正文/次要/辅助 ≥ 4.5:1（L60）；浅色+高对比不能把静音文字变没（L66）；暗色 ≥ 4.5:1（L74）；暗色+高对比 ≥ 7:1（L80）；高对比必须按主题成对定义（L85）。

**`web/frontend/src/lib/cssLayers.test.ts`（4 条）**：入口 `styles.css` ≤ 120 行且只做 `@import`（L19）；字体声明只在 `fonts.css`、全本地 URL（L29）；字体异步加载、不在 `main.tsx` 静态导入（L40）；令牌只定义一份——`tokens.css` 有 `:root`、`app.css` 没有（L47）。

**`web/frontend/src/lib/wiring.test.ts`（9 条，接线契约）**：图谱死区（L18）；会话切换必须 `setLoading(true)`（L28）；会话创建的 URL 标记（L36）；首帧主题在 CSS 之前（L42）；主题解析写回缓存（L51）；暗色纸张纹理覆盖限定浅色（L56）；减动效只零化时长令牌（L62）；缩进契约（L74）；不得出现第二条全局 `!important` 减动效重拳（L84）。

#### 16.3.3 L2 计算样式契约（Playwright `getComputedStyle`）

| # | 契约 | 用例 | 预算 vs 实测 |
|---|---|---|---|
| L2-1 | 阅读器正文字号必须跟随设置里的「正文字号」（15 / 18 都等于偏好值，且 `--body-font-size` 同步） | `web/frontend/e2e/reader-font-size.spec.ts`：阅读器正文跟随设置的正文字号（15 与 18 都等于偏好值） | 精确相等 |
| L2-2 | 主题 / 高对比下正文对比度按 §18 达 AA：**四个组合全测**（浅色/暗色 × 普通/高对比），因为真出过事的组合是「浅色 + 高对比」（muted 曾被压到 1.10:1），只测暗色等于漏掉它 | `web/frontend/e2e/design-computed.spec.ts`：每个组合都断言 `--ink` / `--muted` / `--faint` 对 `--paper` 的实测比值 | 普通：ink ≥ 12/10、muted、faint ≥ 4.5；高对比：muted、faint ≥ 7（比值写进失败信息） |
| L2-3 | 表面阶梯与发丝边在真实渲染里的计算值：`--surface-0..3` 逐层抬升、`--hairline` 外环真的落成 1px 环 | 同一 spec：`.sidebar` / `.settings-main` / `.settings-section` / `.ui-modal-panel` 的 `backgroundColor` 必须等于对应 `--surface-*`；浮层与 `.composer` 边框为 0 且 `box-shadow` 含 `0px 0px 0px 1px` | 精确相等 |
| L2-4 | UI 控件不得渲染小于 12px 的计算字号 | 同一 spec：**七页**（对话 / 练习 / 题库 / 复习 / 资料库 / 笔记 / 设置）遍历所有可见文字节点的 `fontSize`。**知识地图不在覆盖范围内**：节点与标签由 Sigma 画在 canvas 上，DOM 里没有文字节点，字号只能靠 GraphCanvas 的渲染参数保证 —— 不写成「全站已验」 | 违规条数 = 0 |
| L2-5 | 设置对话框在低高度窗口不被裁切：1280×600 全在视口内、保存按钮可见；1440×960 高度 ≤ 840px 且底部主操作贴底 | `web/frontend/e2e/settings-fit.spec.ts` | ≤ 601px / ≤ 840.5px / 底边差 ≤ 1.5px |

**用例共用一套 mock（2026-11-02）**：`web/frontend/e2e/fixtures/mockApi.ts` 提供偏好默认值（含 `theme` / `contrast`）、`settingsPayload(overrides)` 与 `mockApi(page, options)`。此前 `settingsPayload` 在 5 个 spec 里各写一份并已漂移（`settings-fit` 缺 `theme` / `contrast`），L2 主题契约在某些 spec 里静默失义。

**修正过期导入 mock 时挖出的真 bug（2026-11-02）**：`app.spec.ts` 的「首次上传建库并导入」一直只 mock 同步端点 `/api/kb/import`，而 E8 之后导入走 `POST /api/kb/imports` + 轮询；请求漏到真实后端，报「Unknown or unregistered Bobodan library」——**这条用例自 E8 起就是红的，只是没人跑**。补上 mock 后它立刻暴露 `web/frontend/src/hooks/useImportRun.ts` 的真缺陷：`disposedRef` 只在 effect 清理里置 `true`、从不在挂载时复位，开发期 StrictMode 的「挂载 → 清理 → 再挂载」把它永久锁死，于是**开发模式下每次导入都在第一个进度快照处被当成已卸载、返回 `null`**，界面报「导入没有返回结果。」，进度条也永远卡在 0/1。修法：effect 挂载时复位 `disposedRef`，并给「提前返回 null」补注释说明收尾归卸载负责。回归探针是 `src/hooks/useImportRun.test.ts` 里 `wrapper: StrictMode` 那条（回退修复会红，已验证）。
**L2-3 抓到的第一个真缺陷（2026-11-02）**：`.welcome-view .composer`（`app.css:782`，两个类）特异性高于 M3 的 `.composer`（`app.css:2250`，一个类），把「surface 3 + 发丝外环」的 `box-shadow` **整条覆盖**成 `0 10px 28px`，于是首页输入区根本没有发丝环 —— 而 L1 文本契约只检查「源码里有那条声明」，全程绿灯。修法：welcome 变体把外环并进自己的 `box-shadow`，不再整体覆盖。这正是 L2 存在的理由：**L1 证明写了，L2 证明生效**。

**L2-1 为什么必须存在**：`.reader-prose` 曾经有 5 处 `font-size` 互相覆盖（`app.css:985/1296/1360/1401/1635`），特异性最高的 `.reader-article .reader-prose { font-size: 18px }` 让设置里的字号完全不生效，而 L1 文本契约全程绿灯。2026-10-28 删掉 3 处硬编码（保留 `max-width: 800px` 的宽度意图），唯一到达正文字号的声明变成 `var(--body-font-size)`。L2-1 是这条 bug 的回归探针。

**棘轮规则（2026-10-28 修订）**：预算只允许下调，且必须**等于当次实测值**；不再写「直到归零」这种无法兑现的口号。想归零就先真归零，再把常量改成 0——否则注释与常量不一致，会给出假安全网。

## 17. 性能与包体预算（打包前红线）

| 指标 | 预算 | 现状（2026-10-17，M5 实测） | 测量方式 |
|---|---|---|---|
| 主 JS | ≤ 110 KB gz | **95.77 KB gz** ✅ | `npm run build` |
| 关键 CSS（不含字体 face） | ≤ 120 KB gz | **33.80 KB gz** ✅ | 同上 |
| 字体 CSS（延迟加载） | — | **166.00 KB gz**（独立 `fonts-*.css` chunk，首屏不阻塞）✅ | 同上 |
| 首屏字体 | ≤ 1 MB | Noto 按需分片，首屏只请求用到的 1–3 片 ✅ | dist 统计 + 瀑布 |
| 首屏图片 | ≤ 600 KB | **632 KB**（含 favicon 88KB + apple-touch 50KB；页面图 WebP）✅ | dist 统计 |
| 字体总量（随包） | ≤ 10 MB（**2026-10-17 由 8MB 调整**：完整 CJK 覆盖需要 Noto 100 分片 5.73MB + 楷体子集 3.83MB + Luo 0.31MB） | **9.86 MB** ✅ | dist 统计 |
| 阅读器额外字体 | ≤ 6 MB | **3.83 MB**（楷体 GB2312 子集，原 36.1MB，**−89%**）✅ | dist 统计 |

**M5 实测（2026-10-17）**：dist 总计 **12.07 MB / 152 文件**（构建产物无 sourcemap ✓）；楷体 TTF 36.15MB → woff2 子集 3.83MB；品牌图 PNG 4.7MB → WebP 470KB；主 CSS 已与字体 face 分离。

**规则**：性能预算与功能冲突时，先降体量再谈加功能；每次发版前重测并更新本表。

---

## 18. 可访问性与输入法

- 正文对比度 ≥4.5:1，次要文字 ≥4.5:1，禁用态除外。
- 焦点必须可见：`outline: 2px solid var(--blue-soft)` + offset 2px；不许全局 `outline: none`。
- 键盘：Tab 顺序符合视觉顺序；Esc 关闭浮层并把焦点还给触发元素；浮层内焦点不逃逸。
- 语义：按钮用 `<button>`、导航用 `<nav>`、状态变化用 `aria-live`。
- 动效：尊重 `prefers-reduced-motion` 与应用内开关。全局开关只有一处（`app.css` 的 `@media (prefers-reduced-motion)`），**不要再加第二条 `!important` 重拳**。
- 对比度：正文/次要/辅助文字 ≥ 4.5:1；**高对比必须按主题成对定义**（浅色压深、暗色提亮），由 `themeContrast.test.ts` 真算 WCAG 比值守住（2026-10-28 修订：初版只有深色系浅色文字，浅色下 muted 掉到 1.10:1）。M4 已加 CSS 兜底：`@media (prefers-reduced-motion: reduce)` 下动画/过渡全部关闭 ✓；骨架屏微光循环上限 `--dur-shimmer: 1200ms` ✓。
- 输入法：合成期间不触发快捷键；不允许在 `compositionend` 前提交表单。
- 颜色不是唯一信息载体（来源、状态、错误都必须有文字）。

---

## 19. 桌面打包前检查清单

> 2026-10-17 M6 核对过一遍，打勾项见下方；完整报告在 `docs/archive/frontend/M6_ACCEPTANCE.md`。

**资源与体积**

- [x] 字体子集化完成（楷体 ≤6MB），首屏只加载 Noto 分片。（2026-10-17 M5：楷体 3.83MB）
- [x] 品牌 PNG 已转 WebP/AVIF 并限制尺寸（≤600KB）。（M5：470KB）
- [x] 主 CSS 已拆出字体 face（≤120KB gz）。（M5：33.8 / 166 gz）
- [x] dist 内没有 `.map` / 源文件 / 测试 fixture。（M6：0 个 map）

**离线与本地**

- [x] 断网启动可进入主界面（无外部 CDN 请求）。（M6：@import/fetch 外链 0）
- [x] 字体加载失败时回退到系统字体且不破版。（`font-display: swap` + 回退栈）
- [ ] 数据目录、索引目录、日志目录都在用户目录内且可备份。（**后端/W5 阶段**，前端不涉及）

**窗口与显示**

- [x] 1280×800 / 1440×900 / 1920×1080 三档不破版；125%/150% 缩放下字号与发丝边正常。（M6：15 张实拍 + 等效 CSS 宽度核算）
- [x] 深色系统主题下不出现白底闪烁。（2026-10-28：`index.html:12-23` 首帧前置内联脚本，在 React 挂载前按 `localStorage` 里的 `bobodan:theme` 或系统偏好写 `dataset.theme` 与 `color-scheme`；主题策略见 §9.12）
- [ ] 首屏可交互时间达标（打包阶段实测并记录）。

**质量门禁**

- [ ] 后端 pytest / 前端 vitest / tsc / lint / build / mock e2e / live e2e 全绿。
- [ ] 五层验收（结构/视觉/交互/性能/回归）有记录。
- [ ] 版本号与 CHANGELOG 更新。

---

## 附录 A：v1 → v2 变更记录

| 变更 | 说明 |
|---|---|
| 新增 §0 | 明确「文档 → 实现 → 审查」三种读法 |
| 新增 §3 技法参考 | open-claude-ui 作为技法来源，明确不借品牌 |
| 新增 §4.4 / §4.5 | Surface 阶梯映射、发丝边与外环（🟡 M3） |
| 新增 §5.4 / §5.5 | 字体子集化与按需加载（🟡 M5）、中西混排规则（🟡 M3） |
| 新增 §6.5 | 高度阶梯（🟡 M3） |
| 扩充 §7.1 | 圆角从 4 档扩到 8 档（4 档已落地，4 档计划中） |
| 新增 §7.4 | 滚动遮罩羽化（🟡 M3） |
| 新增 §11.3–11.5 | 弹簧物理表、指针死区与拖拽吸附、IME 守卫 |
| 扩充 §16.2 | 组件规格表补高度列与气泡/浮层行 |
| 扩充 §16.3 | 契约测试从 4 条扩到 8 条 |
| 新增 §17–§19 | 性能预算、可访问性与输入法、打包前清单 |
| 状态标记 | 所有新增规则标注 ✅/🟡，杜绝「文档写了代码没有」 |

### v2.1（2026-10-28）文档去重时的实测校正

不是新设计，而是把 v2 里「写了但代码不是这样」的四处按实测改回来（依据：`tokens.css`、`app.css`、`grep -ro "var(--radius-*)"` 计数、`designTokens.test.ts`）：

| 变更 | 说明 |
|---|---|
| 校正 §6.5 | 高度阶梯从「五档 + `--h-topbar`」改为实际三档（`-sm` 28 / base 36 / `-lg` 44），并标注三档在样式里**零引用**；删除不存在的 `--h-control-xs/-md/-xl` 与 `--h-topbar` |
| 校正 §7.1 | `--radius-panel` 值 10px→18px（与 token 一致）；补「实测使用次数」列（sm 29 / md 39 / lg 3 / xl 3，xs/control/panel/pill 全 0）；删除从未存在的 `--radius-bubble` |
| 校正 §11.3 | 弹簧表从「micro/base/macro/snap 🟡 计划中」改为已落地的四条 press/pop/panel/accent（附原始过冲 8.9%/2%/0%/19.5% → ≤2%）；说明 micro/base/macro 是早期近似曲线、`--spring-snap` 未落地 |
| 校正 §16.2 | 用户消息气泡行按 `app.css:692` 实际样式改写（背景 `rgba(232,237,243,.68)`、`--radius-md --radius-md 2px` 右下切角），原来写的 `--blue-wash` + `--radius-bubble` 都不存在于实现 |
| 新增 §11.8 | 外部动效库边界（Motion 受限使用，对齐 ROADMAP §3 2026-10-21 决策） |

### v2.2（2026-10-28）第二轮评审：自相矛盾 / 与代码不符 / 结构性优化

这一轮按「自相矛盾 → 与代码不符 → 结构性优化」三层改，全部以当前工作树的实测为准：

| 变更 | 说明 |
|---|---|
| 校正 §4.3 | 渐变预算从「当前 2 处」改为「断言 ≤ 3（2026-10-28 实测 3 处：纸张纹理 / composer 渐隐 / 骨架屏微光）」；「每屏 ≤ 1 处」保留为设计目标而非硬数字 |
| 校正 §5.4 | 标题从 🟡 计划中改为 ✅ 已落地（M5）；表补「M5 前 / 现状」两列：楷体 36.1MB TTF → GB2312 子集 woff2 **3.83MB**（7543 字，−89%），Noto Serif SC 分片保留、@font-face 移入独立 `fonts-*.css` |
| 校正 §7.3 / §7.4 | `--hairline` 与 `--ring` 从「计划中」改为 M3 已落地并写明实现位置（`.settings-nav` / `.providers-list` + `@supports (mask-image: …)` 降级） |
| 校正 §19 | 「深色系统主题下不出现白底闪烁」勾选 ✅：`index.html:12-23` 首帧前置内联脚本先写 `dataset.theme` 与 `color-scheme`，再加载样式 |
| 校正 §4.8 | 2026-10-28 新增「角色令牌与 FUP 命名空间映射」：FUP 的角色色 / 排版 / 间距 / 行高四组 token 逐条裁决（吸收作别名、驳回重复、需新增的给出值），并定 4 条可执行契约与落地顺序（必须先给契约测试加 `var()` 展开，再改别名） |
| 重写 §3 | 一级导航从「Study 4 项 + Workbench 二级」改为实际**六项**（对话 / 练习 / 复习 / 知识地图 / 笔记 / 资料库）；删除 Roadmap / Canvas / Memory 三个不存在页面；补题库 / 知识地图 / 笔记三节；Today 明确标注是对话空态而非独立页面；设置中心移到「全局层」 |
| 校正 §9.5 | 导航行同步六项，删除「Workbench 入口低权重」 |
| 重写 §16.3 | 契约测试拆两层：**L1 文本契约**（52 条全量登记，含测试文件行号与「预算 vs 实测」）+ **L2 计算样式契约**（`getComputedStyle` 断言运行时值）；棘轮规则改为「预算必须等于当次实测值」，不再写「直到归零」这类会自我作废的口号 |
| 修活 bug | `.reader-prose` 曾有 5 处 `font-size` 互相覆盖（`app.css:985/1296/1360/1401/1635`），特异性最高的 `.reader-article .reader-prose { font-size: 18px }` 让「界面与阅读 → 正文字号」完全失效；删掉 3 处硬编码（保留 `max-width: 800px` 的宽度意图），唯一到达的声明变成 `var(--body-font-size)`，并加 L2-1 回归探针 `e2e/reader-font-size.spec.ts` |
| 校正 token 默认值 | `--body-font-size` 从 17px 改 16px 与后端 `service/preference_service.py:46` 一致（此前 17 是死值：运行时被 `AppShell.tsx:263` 的内联偏好覆盖），并注明它只是首帧兜底 |

## 附录 B：参考与许可

**设计参考**：

- `open-claude-ui`（pin `ddf3aea`）：`docs/v1/01-设计哲学与设计令牌体系.md`、`02-基础原子组件与交互控件.md`、`03-会话核心流与指令交互引擎.md`、`04-动效物理学、着色器与环境光影.md`、`docs/v2/05-生产级参考实现代码.md`（只借技法，不借品牌资产与色板）。
- 检索评测规模：[Topic Set Size Redux (ACM)](https://dl.acm.org/doi/pdf/10.1145/1571941.1572138)（用于 §5.2 评测集规模的依据，见 `docs/archive/frontend/FRONTEND_OPTIMIZATION.md`）。

**字体许可**：

- 中文字体参考 Luo 落文（作者 tw93，https://github.com/tw93/Luo）：正式产品使用前检查 LICENSE；Luo 基于 LXGW WenKai Screen 构建，向 LXGW、落霞孤鹜与 Fontworks Klee One 致谢。
- Noto Serif SC：SIL Open Font License，按 unicode-range 分片随项目分发。
- 仓耳今楷（Kami 同款）：公开分发桌面安装包前**必须**再次核对作者分发条款并保留所需署名。

**实现约定**：本文档的所有 token 以 `web/frontend/src/styles/tokens.css` 的 `:root` 为准（`styles.css` 只做 `@import` 分层，M1 起不再放令牌）；文档与代码不一致时，先修文档，再跑契约测试确认。

## 附录 C：v1 的去向

v1（约 1310 行）完整保留在 git 历史：`git show e1f4db4:docs/DESIGN.md`。

v2 保留了 v1 的**全部产品规则、品牌决策与反模式**；压缩掉的只有示例性文字、实现细节，以及「首次引导」一节的细节描述（如需恢复，可在上述提交中检索对应小节并入）。
