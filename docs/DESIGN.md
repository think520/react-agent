# Bobodan Design Guide（v2 · 2026-10-17）

> 定位：Bobodan 的**可执行**设计规范 —— 能被实现、能被测试、能被审查，而不只是被阅读。
> 品牌锚点不变：**暖纸底 + 墨蓝阅读秩序 + 植物绿自然气息 + 橘棕温度 + 花瓣粉私人情绪；中文排版有风骨。**
> 与 v1 的关系：结构与品牌决策保留，内容升级为规格化（新增表面阶梯、发丝边、高度阶梯、弹簧物理、IME 守卫、性能预算、打包清单）。
> 执行方式：本文的数值都是 token；`web/frontend/src/lib/designTokens.test.ts` 把关键约定变成会失败的测试（见 §16.3）。

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

## 3.1 Study / Workbench 视觉分区

- **Study**：Chat / Practice / Review / Library —— 一级导航，视觉权重最高。
- **Workbench**：知识地图、概念审查、Wiki 维护 —— 二级入口，低权重，不压过 Study。
- **Settings**：设置在资料库信息区，不占一级导航。

---

## 3.2 信息密度与响应式优先级

- 桌面（≥1280px）：三栏（侧栏 252px / 主内容 720px / 上下文 304px）。
- 桌面窄（960–1279px）：收起上下文栏，主内容优先。
- 移动端（本轮不做，但布局不得破坏）：Chat / Practice / Review / Library 优先。

---

## 3.3 页面气质规则

### Today

Today 是学习伙伴的起点，不是 dashboard；Web MVP 里它就是 Chat 的起始状态。结构：一句低压问候 + 一条记忆/上下文 + 2–3 个行动建议。

**不要**把知识库数量、MCP 连接、Cron、Logs 摆在首页；系统状态要翻译成学习建议。

### Chat

Chat 用对话主骨架，但视觉像阅读器和笔记本：中央对话、资料入口、学习动作入口、右侧学习上下文；回答区域要像文章，不像日志流。

**Composer 三层结构**（不许把所有控制塞进一排）：① 输入框内：附件 / Slash / 资料范围 / 回答深度 / 模型 / 发送或停止；② 输入框上方：检索、Wiki、练习生成等当前状态；③ 全局连接条：只在断开/重连时出现。

**个人笔记**：沉浸式 Markdown 编辑（`/notes`）—— 正文为主角，首行「# 标题」自动提取为标题，支持「编辑 / 预览」切换，`Ctrl+Enter` 保存、`Esc` 关闭，关联资料折叠到底部按需展开；不做表单式「标题框 + 正文框 + 复选框堆叠」。

#### 设置中心

设置入口在左侧资料库信息区，不占 Study 一级导航；桌面用 960–1120px 居中大弹窗（最大高度约 84vh），移动端全屏；背景保留当前学习页面并轻度压暗，不跳转企业后台式独立控制台。

骨架固定为「搜索与分类导航 + 分组内容」：

- **Bobodan**：助手昵称、教学方式、回答深度、反馈强度、品牌头像预览。
- **我与学习**：称呼、个人简介、长期学习目标。
- **界面与阅读**：今楷 / 宋体、字号、内容宽度、纸纹、会话密度、减少动效。
- **AI 与模型**：Provider 状态、默认 Provider、模型名称、明确触发的测试连接。
- **记忆与数据**：记忆开关、待确认数量、个人知识管理入口、当前资料库、本地数据边界。
- **Skills**：只展示 Web 安全白名单内的名称、说明、来源、能力、启用状态。
- **状态与关于**：后端、Provider、资料索引、记忆、Skills、版本等用户可理解状态。

开关与单选即时保存，失败恢复旧值；用户资料与人设表单用明确保存按钮。设置页**不得**编辑 API Key / `.env` / 文件权限 / 联网权限 / 系统安全规则，也不得显示绝对 Skill 路径、Trace、原始日志。

对话修改设置必须先显示前后值确认卡（只允许回答深度、教学方式、反馈强度、记忆开关）；确认前不修改，拒绝后不留隐式副作用。

### Practice

一题一卡，像纸面测验：轻边界、清楚题干、充足留白、温和反馈、来源标签清楚。**不要**做成密集刷题后台。

### Review

像一份轻量学习清单：到期知识点、错题来源、薄弱点、建议练习数量。**不要**做成复杂日历或大数据面板。

### Library

资料树 + 阅读/来源面板为主，局部关系为辅：左侧资料树，中间阅读或摘要，右侧来源/双链/局部图谱。**不要**把大图谱当主舞台。

### Reader

Library 内的专注阅读视图：专注、highlight、摘录、稍后读、复习回流；视觉保持纸面阅读气质。

### Roadmap

像学习计划和课程地图：目标 → 当前阶段 → 今日任务 → 后续。**不要**混入 Agent 任务、Cron 或 Logs。

### Canvas

Chat 内的临时展开面板（学习白纸），不是 Figma / Notion / IDE。

### Memory

在主流程里自然出现，管理入口在设置中心「记忆与数据」；表达要像整理过的索引卡，而不是数据库表。已确认知识可查看/编辑/删除/置顶/按作用域筛选/Markdown 导出；候选只能先进入待确认。

**记忆红线**：密码、Token、API Key 一律拒绝保存；敏感内容在卡片内再次提示；候选、被拒绝内容与内部工具输出**不得**进入 Prompt。

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

**渐变预算（M3）**：每屏背景渐变 ≤ 1 处，且同色相明度差 ≤ 8%；遮罩渐变（`mask-image`）与纸纹不计入。整份样式背景渐变上限由 `designTokens.test.ts` 棘轮看住（当前 2 处，只减不增）。

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

以下代码块必须与 `styles.css` 的 `:root` **逐条一致**（契约测试比对，空格不敏感）：

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
  --body-font-size: 17px;
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
| 正文 | 16–18px（`--body-font-size: 17px`） |
| UI 标签 | 13–14px |
| 辅助说明 | 12–13px |

**硬下限（由契约测试执行）**：辅助说明 ≥ 12px、UI 标签 ≥ 13px、正文 16–18px。当前低于 12px 的声明数 **= 0** ✅。

规则：字重多用 500/600，字距保持 0（不用负字距），正文行高 1.7–1.9，阅读宽度 680–760px。

### 5.4 字体加载、分片与子集化 🟡 计划中（M5）

Bobodan 是 local-first 产品：**字体必须随包分发**，运行时禁止依赖 jsDelivr / Google Fonts 等公共 CDN；加载失败必须自然回退到本地系统字体。

| 资源 | 现状 | 目标（M5） |
|---|---|---|
| Noto Serif SC | 100 个 unicode-range 分片，5.7MB，浏览器按需加载 ✅ | 保留分片；把 face 声明移出主 CSS，改为延迟加载 |
| 仓耳今楷 W04/W05 | 2 × 18.5MB TTF = 36.1MB ✗ | **子集化**（GB2312 6763 字 + 常用标点 + 拉丁）转 woff2，每套 2–3MB，合计 ≤ 6MB；**进入阅读器时才加载** |
| Luo | ~327KB | 保留（只做品牌与短标签，禁止做长文唯一字体） |

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

### 6.5 高度阶梯 🟡 计划中（M3）

| token | 值 | 用在哪 |
|---|---|---|
| `--h-control-xs` | 24px | 行内小按钮、标签关闭 |
| `--h-control-sm` | 28px | 紧凑下拉、工具条按钮 |
| `--h-control-md` | 32px | 标准按钮 |
| `--h-control-lg` | 40px | 主按钮、输入框（现有 ≥40 的下限） |
| `--h-control-xl` | 44px | 列表行、触控目标 |
| `--h-topbar` | 68px | 顶栏 |

**规则**：任何可点元素的有效高度 ≥ 40px（列表行 ≥ 44px）；视觉高度可以小于 40，但热区必须补足。

### 6.6 阅读行宽

正文容器宽 `--content-width`（720px），长文单行 32–40 个汉字；超过 40 字要加宽行高或分栏。

---

## 7. 形状与光影

### 7.1 圆角矩阵

| 档 | token | 值 | 用在哪 | 状态 |
|---|---|---|---|---|
| XS | `--radius-xs` | 2px | 角标、聚焦环内衬 | 🟡 |
| SM | `--radius-sm` | 6px | chip、kbd、小标签 | ✅ |
| MD | `--radius-md` | 8px | **标准按钮、输入框、下拉项** | ✅ |
| Panel | `--radius-panel` | 10px | 子面板、附件条目 | 🟡 |
| LG | `--radius-lg` | 12px | 卡片、代码块、浮层 | ✅ |
| XL | `--radius-xl` | 16px | 弹窗、抽屉、设置卡片 | ✅ |
| Bubble | `--radius-bubble` | 18px | 用户消息气泡 | 🟡 |
| Pill | `--radius-pill` | 999px | 分段控件、状态呼吸点 | 🟡 |

**同心圆角公式**（🟡）：`--radius-card: calc(var(--radius-md) + var(--space-1))` —— 内层元素用外层半径减去内距，保持视觉同心。

### 7.2 表面与高度

| token | 用在哪 | 层级 |
|---|---|---|
| `--shadow-soft` | 内容轻度抬升 | 1 |
| `--shadow-lift` | hover / 选中 | 1 |
| `--shadow-float` | 浮层、菜单 | 2 |
| `--shadow-dialog` | 弹窗、抽屉 | 3 |

**配额**：内容区每屏抬升 ≤ 1 处；浮层必须同时有发丝边，不能只靠阴影。

### 7.3 边框与发丝边

三档 `--border-subtle` / `--border` / `--border-strong` + 计划中的 `--hairline` / `--ring`（见 §4.5）。

### 7.4 遮罩与羽化 🟡 计划中（M3）

长滚动容器（会话栏、资料树、正文滚动区）在滚动方向做**非线性羽化遮罩**：

```css
mask-image: linear-gradient(to bottom, transparent 0, #000 12px, #000 calc(100% - 12px), transparent 100%);
```

优先用 `animation-timeline: scroll()` 让遮罩随滚动渐显；不支持的浏览器静态降级。遮罩只做视觉，不拦截事件。

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

一级导航：Chat / Practice / Review / Library；当前项用墨蓝体系，不用 sage 当选中态；Workbench 入口低权重。

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

### 11.3 弹簧物理（4 套常数 → CSS `linear()`）🟡 计划中（M4）

参考 CDS 的生产常数，映射到我们的 CSS 曲线（**过冲一律 ≤2%**，不采用 +19% 的 bouncy 预设）：

| token | 物理来源（stiffness / damping / mass） | 用在哪 | 配哪档时长 | 过冲 |
|---|---|---|---|---|
| `--spring-micro` ✅ | 600 / 30 / 1.0（ζ 0.61） | 按钮、开关、checkbox | `--dur-fast` | ≤2% |
| `--spring-base` ✅ | 320 / 28 / 1.0（ζ 0.78） | 选中态、行展开、卡片抬升 | `--dur-base` | ≤2% |
| `--spring-macro` ✅ | 380 / 18 / 1.0（ζ 0.46，过冲已压到 ≤2%） | 抽屉、面板入场、列表增删 | `--dur-slow` | ≤2% |
| `--spring-snap` 🟡 | 1200 / 80 / 0.1（ζ 3.65，零过冲） | 拖拽松手吸附、面板停靠 | `--dur-fast` | 0% |

**用法**：`transition: transform var(--dur-fast) var(--spring-micro)`；缩放只允许 0.96–1.02。

### 11.4 手势、指针与滚动 🟡 计划中（M4）

- **指针死区 4px**：按下后位移 <4px 视为点击，不进入拖拽（知识图谱、可拖拽面板）。
- **拖拽吸附**：松手用 `--spring-snap` 吸附到目标位；不许有持续跟随的惯性漂移。
- **滚动单写者** ✅ 已落地：所有自动滚动集中在 `useStickyBottomScroll` 的 `step()`，一帧最多写一次 `scrollTop`；手势期间零写入；只有「用户发消息」才 `pinToBottom()`。

### 11.5 输入法（IME）与键盘

- 合成期间不触发任何快捷键（见 §9.2）；
- Enter 发送、Shift+Enter 换行、Esc 关闭浮层/中断输入法；
- 所有浮层必须支持 Esc 与焦点返回触发元素。

### 11.6 减少动态效果

应用内开关与 OS `prefers-reduced-motion` 同义：关闭装饰性动画与自动滚动，只保留短淡入与必要颜色反馈；JS 动画实时读取开关（`lib/motion.ts`），不做挂载时快照。

### 11.7 禁止项

弹跳、强缩放、粒子、频闪、自动播放的大段动画、`transition: all`、从 `scale(0)` 出现、整页视差。

---

## 12. 内容语气

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
| 用户消息气泡 | `--blue-wash` | 无 | `--radius-bubble` | `--space-3` `--space-4` | 正文 | — | §16.1 |

### 16.3 契约测试（`web/frontend/src/lib/designTokens.test.ts`）

下面每一条都是会失败的测试，不是口号：

| # | 契约 | 状态 |
|---|---|---|
| 1 | §4.6 token 表与 `styles.css` `:root` 同名同值；OWNED 命名空间的 token 必须全部入表 | ✅ |
| 2 | 低于 12px 的 `font-size` 必须为 0 | ✅（预算 0） |
| 3 | 裸缓动（裸 `ease` / 裸 `cubic-bezier`）数量 ≤ 预算，只减不增 | ✅（预算 15） |
| 4 | 不在圆角刻度上的 `border-radius` 数量 ≤ 预算，只减不增 | ✅（预算 60） |
| 5 | 裸毫秒值数量 ≤ 预算，只减不增 | ✅（预算 4） |
| 6 | 字体栈以通用族收尾；UI/阅读/文章字体显式点名 CJK；长文正文不用品牌字体；无公共 CDN；`@font-face` 只用本地 URL | ✅ |
| 7 | 存在一条把 button/input/textarea/select 一起设为 `font: inherit` 的规则 | ✅ |
| 8 | 表面阶梯（`--surface-0..3`）必须是既有纸面色的**别名**，不得引入新色值 | ✅（M3，`designTokens.test.ts`） |
| 9 | `--hairline` / `--ring` 必须入 `:root` 与 §4.6 表；2dppx 下 `--hairline` 减半 | ✅（M3） |
| 10 | 高度阶梯（`--h-control-*`）与圆角补充令牌（`--radius-xs/control/panel/pill`）入表；§7 圆角棘轮不受影响 | ✅（M3） |

**棘轮规则**：预算只允许下调；每完成一批收敛就调低预算，直到归零。

---

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

> 2026-10-17 M6 核对过一遍，打勾项见下方；完整报告在 `docs/M6_ACCEPTANCE.md`。

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
- [ ] 深色系统主题下不出现白底闪烁（主题策略见 §9.12）。
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

## 附录 B：参考与许可

**设计参考**：

- `open-claude-ui`（pin `ddf3aea`）：`docs/v1/01-设计哲学与设计令牌体系.md`、`02-基础原子组件与交互控件.md`、`03-会话核心流与指令交互引擎.md`、`04-动效物理学、着色器与环境光影.md`、`docs/v2/05-生产级参考实现代码.md`（只借技法，不借品牌资产与色板）。
- 检索评测规模：[Topic Set Size Redux (ACM)](https://dl.acm.org/doi/pdf/10.1145/1571941.1572138)（用于 §5.2 评测集规模的依据，见 `docs/FRONTEND_OPTIMIZATION.md`）。

**字体许可**：

- 中文字体参考 Luo 落文（作者 tw93，https://github.com/tw93/Luo）：正式产品使用前检查 LICENSE；Luo 基于 LXGW WenKai Screen 构建，向 LXGW、落霞孤鹜与 Fontworks Klee One 致谢。
- Noto Serif SC：SIL Open Font License，按 unicode-range 分片随项目分发。
- 仓耳今楷（Kami 同款）：公开分发桌面安装包前**必须**再次核对作者分发条款并保留所需署名。

**实现约定**：本文档的所有 token 以 `web/frontend/src/styles.css` 的 `:root` 为准；文档与代码不一致时，先修文档，再跑契约测试确认。

## 附录 C：v1 的去向

v1（约 1310 行）完整保留在 git 历史：`git show e1f4db4:docs/DESIGN.md`。

v2 保留了 v1 的**全部产品规则、品牌决策与反模式**；压缩掉的只有示例性文字、实现细节，以及「首次引导」一节的细节描述（如需恢复，可在上述提交中检索对应小节并入）。
