# 前端优化方案（进入应用打包前）

> 版本：2026-10-17 · 状态：**待实施** · 依据：六项已确认决策 + 参考仓库逆向规范 + 本轮实测数据
> 参考仓库：`F:\claude projects\open-claude-ui`（pin `ddf3aea`）
> 硬约束：不改行为契约（现有 292 条前端测试、15 条 mock e2e、7 条 live 全绿）；每阶段一个本地提交；**不推送**。

---

## 0. 已确认的六项决策

| # | 决策点 | 结论 |
|---|---|---|
| Q1 | 目标层级 | **系统级重构 + 打磨**（不是只做视觉打磨） |
| Q2 | 视觉语言 | **工程规范 + 视觉语言都吸收**，以「不影响 Bobodan 品牌」为前提：吸收**技法**、不换**色板与字体** |
| Q3 | 动效技术 | **纯 CSS + 现有 rAF 体系**，不引入 framer-motion / motion |
| Q4 | 重构范围 | **CSS 分层 + 巨型页面拆分 + ui 原子组件**三层治理 |
| Q5 | 字体与包体 | **子集化 + 按需加载** |
| Q6 | 验收 | **五层验收**（结构 / 视觉 / 交互 / 性能 / 回归） |

## 1. 现状体检（本轮实测，可复跑）

### 1.1 源码体量

| 指标 | 实测值 | 复跑方式 |
|---|---|---|
| 前端文件 / 总行数 | **138 文件 / 25,613 行** | `Get-ChildItem src -Recurse -File` |
| 页面数 | 13（含 5 个测试文件） | `src/pages/` |
| 组件数 | 40+ | `src/components/` |
| 样式主文件 | **`styles.css` 2,086 行 / 217KB** | `Get-Content src/styles.css | Measure-Object -Line` |
| 字体 face 样式 | `noto-serif-sc.css` 521KB（100 个 unicode-range 分片） | 同上 |

**体量热点（单文件 ≥ 28KB）**：

| 文件 | 体积 | 结论 |
|---|---|---|
| `pages/LibraryPage.tsx` | **84KB** | 必须拆（W-F2 第一优先） |
| `lib/api.ts` | 63KB | 按域拆分（library / chat / practice / graph） |
| `pages/ChatPage.tsx` | 59KB | 拆（composer / messages / artifacts） |
| `components/AppShell.tsx` | 39KB | 拆（sidebar / topbar / context rail） |
| `components/SettingsDialog.tsx` | 32KB | 按设置分组拆 |
| `components/DocumentReader.tsx` | 30KB | 拆（reader / anchors / editor） |
| `pages/QuestionBankPage.tsx` / `PracticePage.tsx` | 各 28KB | 二期 |

### 1.2 构建产物（2026-10-17 `npm run build`）

| 产物 | 原始 | gzip | 预算（本方案目标） |
|---|---|---|---|
| `index-*.js`（主包） | 298.03 kB | **91.73 kB** | ≤ 110 kB gz |
| `index-*.css`（主样式） | 656.59 kB | **197.77 kB** | ≤ 120 kB gz（字体 face 拆出延迟加载） |
| `lib-*.js`（懒加载） | 153.70 kB | 45.71 kB | 维持 |
| `common-*.js` | 80.77 kB | 27.40 kB | 维持 |
| `LibraryPage-*.js` / `ChatPage-*.js` | 59.5 / 52.4 kB | 17.6 / 16.3 kB | 维持 |

结论：**代码分割已经做了** ✓（页面级懒加载），主要浪费在 **CSS 单文件 198KB gz**（字体 face 混在主样式里）和**字体/图片资源体积**。

### 1.3 资源体积（打包前最大风险）

| 资源 | 体积 | 说明 |
|---|---|---|
| `public/assets/fonts/kami-reading`（仓耳今楷 W04/W05） | **36.1 MB**（单文件 18.5 MB） | 随包分发；阅读器字体 |
| `public/assets/fonts/noto-serif-sc` | 5.7 MB / 100 片 | 已按 unicode-range 分片 ✓ 浏览器按需加载 |
| 品牌 PNG（头像 + 4 张表情） | **≈ 2.8 MB**（最大单张 728 KB） | 需转 WebP/AVIF + 响应式尺寸 |
| 字体合计 | **42.2 MB** | Electron 安装包直接背负 |

### 1.4 现有契约测试预算（`src/lib/designTokens.test.ts`）

| 契约 | 当前预算 | 状态 |
|---|---|---|
| 字号低于下限的声明数 | **0** | ✅ 已归零 |
| 裸缓动（裸 ease / cubic-bezier） | 15 | 棘轮，只减不增 |
| 脱轨圆角（不在刻度上） | 60 | 棘轮，只减不增 |
| 裸毫秒值 | 4 | 棘轮，只减不增 |

### 1.5 测试基线（本方案每阶段都必须保持全绿）

后端 **1,845 passed** ｜ 前端 **46 文件 / 292 passed** ｜ mock e2e **15 passed** ｜ live **7 passed**（需先起服务）

---

## 2. 目标与非目标

**目标（三条）**

1. **结构可维护**：样式分层、巨型文件拆分到可读粒度、原子组件收口 —— 为打包后的长期迭代打底。
2. **体验更稳更细**：把参考仓库的交互物理与状态规范落到我们自己的页面上（发丝边、表面阶梯、遮罩、弹簧曲线、IME 守卫）。
3. **包体可控**：字体与图片降到 Electron 可接受范围，主 CSS/JS 有明确预算。

**非目标（明确不做）**

- 不换品牌视觉（陶土色 / Claude 语汇 / CDS 色板一律不引入）。
- 不引入动效库（framer-motion / motion）。
- 不做 Storybook / 独立设计系统包。
- 不把现有手写 CSS 迁移成 Tailwind 工具类（继续「令牌 + 语义类」路线）。
- 不做 TUI 与移动端（本轮只服务 Windows 桌面打包）。
- 不动后端检索/证据链行为（只做 §5.1 的死代码删除）。

---

## 3. 参考仓库吸收清单

参考仓库的价值不在 `src/`（只有入口），而在 `docs/`：**CDS 全量规范 234KB + 令牌体系 42KB + 动效物理学 17KB + 生产级参考实现 12KB**。

| 吸收（技法） | 具体内容 | 映射到我们的令牌 |
|---|---|---|
| 表面阶梯 | Surface 0–3 四层微对比 | 现有三档纸面色 + 第 4 层用「抬升 + 发丝边」表达（不新增色值） |
| 发丝边 / 外环 | 1px 半透明描边替代硬边框；`color-mix` 外环 | 新增 `--hairline` / `--ring`，2dppx 下 0.5px |
| 圆角矩阵 | 2/4/6/8/10/12/16/18/20/999 共 9 档 | 现有 4 档保留，**新增** `--radius-xs / --radius-panel / --radius-bubble / --radius-pill` |
| 高度阶梯 | 24/28/32/36/40/44 + 行高 44 + 顶栏 68 | 新增 `--h-control-xs…--h-control-xl`，现有 ≥40 不变 |
| 动效物理 | 4 套弹簧（600/30、320/28、380/18、1200/80·mass .1） | 转成 `linear()` 曲线；**不引入 +19% 过冲的 bouncy 预设**（我们规定过冲 ≤2%） |
| Alpha 遮罩 | 7 档非线性滚动淡出 | `mask-image` + `animation-timeline: scroll()`（带降级） |
| CJK IME 守卫 | 合成中不触发 Enter/快捷键 | 新增到 Composer（真实缺陷候选） |
| 指针死区 | 4px 移动死区 | 知识图谱拖拽 / 菜单手势 |
| 组件四态规范 | 静置 / hover / active / focus-visible / disabled | 已有 §16，本轮补齐「组件 × 四态」矩阵与契约测试 |

**不吸收**：Claude 陶土色板与品牌资产、音频合成提示音、shader 光效/推理氛围、Cowork 多代理拓扑、整页毛玻璃。

参考出处：

- `docs/v1/01-设计哲学与设计令牌体系.md` §1.2 表面阶梯 / §1.3 圆角与高度矩阵 / §1.5 字体 / §1.6 动效令牌
- `docs/v1/02-基础原子组件与交互控件.md`（组件四态与尺寸）
- `docs/v1/03-会话核心流与指令交互引擎.md`（Composer / 流式状态 / IME）
- `docs/v1/04-动效物理学、着色器与环境光影.md` §4.1 弹簧常数 / §4.3 遮罩
- `docs/v2/05-生产级参考实现代码.md`（可直接对照的 React/CSS 写法）

---

## 4. 五个工作流

### W-F1 CSS 分层（先做：风险最低、收益最大）

**问题证据**：`styles.css` 2,086 行 / 217KB 单文件；字体 face 521KB 与业务样式混在同一入口；构建主 CSS **197.77KB gz**。

**做法**

1. 拆为 `src/styles/` 五层并用 `@layer` 固定顺序：`tokens.css`（:root 全部令牌）→ `base.css`（reset/排版/滚动条）→ `components.css`（通用组件）→ `pages/*.css`（每页一个文件）→ `overrides.css`（少量收口）。
2. `styles.css` 只留 `@layer` 声明 + `@import`（目标 ≤ 120 行）。
3. **字体 face 拆出**：`noto-serif-sc.css` 与楷体 `@font-face` 移出主入口，改为按需注入（见 W-F5）。
4. 契约测试加一条：入口 `styles.css` 行数 ≤ 120（棘轮），页面 css 不得出现裸色值（棘轮从 0 起）。

**交付**：分层后的 css + 入口瘦身 + 2 条新契约测试。

**验收**：`npm run build` 成功；主 CSS gzip ≤ 120KB；vitest 292 全绿；关键页截图无变化（除字体加载顺序）。

**风险 / 回滚**：层顺序错误会导致覆盖失效 → 用 `@layer` 显式声明优先级，并在拆分前后各截一轮图对比。单 commit，可整体回滚。

### W-F2 巨型页面拆分

**问题证据**：`LibraryPage.tsx` 84KB、`ChatPage.tsx` 59KB、`AppShell.tsx` 39KB、`SettingsDialog.tsx` 32KB、`api.ts` 63KB。

**做法（按风险从低到高）**

1. `AppShell` → `shell/Sidebar.tsx` + `shell/Topbar.tsx` + `shell/ContextRail.tsx` + `useShellState.ts`。
2. `ChatPage` → 保留壳（≤ 300 行）+ `useChatSend.ts` + `ChatComposer.tsx` + `MessageList.tsx` + `ChatArtifacts.tsx`。
3. `LibraryPage`（最难，最后做）→ `pages/library/LibraryPage.tsx` 壳 + `useLibraryData.ts` + `useLibraryActions.ts` + `LibraryToolbar.tsx` + `LibraryTreePanel.tsx` + `LibraryDetailPanel.tsx` + `LibraryDialogs.tsx`。
4. `api.ts` 按域拆：`api/library.ts` / `api/chat.ts` / `api/practice.ts` / `api/graph.ts` / `api/settings.ts`，`index.ts` 再导出（调用方零改动）。
5. `SettingsDialog` 按分组拆 6 个 section 组件。

**规则**：目标单文件 ≤ 600 行（≈22KB）；拆出的 hooks 只搬「逻辑」不搬「行为」，**不改任何 props/事件名**；每拆一个文件跑一次相关测试。

**验收**：所有文件 ≤ 600 行；292 条测试一条不改全绿；mock e2e 15 全绿。

### W-F3 视觉语言融合（技法层，不换品牌）

**问题证据**：现有边框都是硬 rgba 描边；表面只有三档；组件规格表缺高度/圆角列；无 alpha 遮罩。

**做法**

1. **表面阶梯**：定义 `--surface-0..3` 别名 → 0`--paper-sunken`（停靠栏）/ 1`--paper`（画布）/ 2`--paper-soft`（卡片、浮层）/ 3=`paper-soft` + `--hairline` + `--shadow-float`（弹窗、菜单）。不改现有色值。
2. **发丝边**：`--hairline: 1px`、`--ring: color-mix(in srgb, var(--ink) 12%, transparent)`；`@media (min-resolution: 2dppx) { --hairline: 0.5px }`；浮层一律 `box-shadow: 0 0 0 var(--hairline) var(--ring)`。
3. **圆角/高度矩阵**：新增四个令牌（2px / 10px / 18px / 999px）与高度阶梯 `--h-control-*`；在 DESIGN.md 组件规格表里逐组件落位（不批量替换旧值，新代码优先用新令牌）。
4. **Alpha 遮罩**：长列表（会话栏、资料树、正文滚动区）加`mask-image: linear-gradient(...)` + `animation-timeline: scroll()`；不支持时降级为无遮罩。
5. **颜色面积预算**：沿用 DESIGN.md §4 现有预算表，新增一条「每屏渐变 ≤ 1 处，且同色相明度差 ≤ 8%」。

**验收**：DESIGN.md 组件规格表 100% 列齐（表面/边框/圆角/内距/字号/高度/四态）；关键页 Before/After 截图对比；新的令牌契约测试通过；裸色值棘轮不增加。

### W-F4 动效与交互物理

**问题证据**：现有 3 条 `linear()` 弹簧；无 IME 守卫；无指针死区；§11 记录 18 处裸缓动。

**做法**

1. **弹簧曲线表**（映射参考仓库常数 → CSS `linear()`，过冲 ≤2%）

| 令牌 | 物理来源 | 用在哪 | 配哪档时长 |
|---|---|---|---|
| `--spring-press` | 600 / 30 / mass 1.0（ζ 0.61） | 按钮、开关、checkbox | `--dur-fast` |
| `--spring-pop` | 320 / 28 / mass 1.0（ζ 0.78） | 卡片、popover、行展开 | `--dur-base` |
| `--spring-panel` | 1200 / 80 / mass 0.1（ζ 3.65，零过冲） | 抽屉、面板吸附、布局动画 | `--dur-slow` |
| `--spring-accent` | 380 / 18（ζ 0.46）**降过冲后** | 选中态、复制成功等强调反馈 | `--dur-base` |

2. **CJK IME 守卫**：Composer 与所有输入框在 `compositionstart/end` 之间**忽略 Enter/Esc/方向键快捷键**；补一条回归测试（合成中按 Enter 不得发送）。
3. **指针死区**：图谱拖拽与手势菜单实现 4px 死区（按下后位移 <4px 视为点击）。
4. **减少动效**：新增动画一律走 `prefersReducedMotion()`（`lib/motion.ts`）；CSS 侧保留 `@media (prefers-reduced-motion)` 兜底。
5. **加载微光**：骨架屏 shimmer ≤ 1.2s 循环，仅用于首屏与长列表，禁止用于正文。

**验收**：弹簧 token 契约测试（只允许 token 曲线）；IME 回归测试先红后绿；裸缓动棘轮下调。

### W-F5 字体与包体

**问题证据**：字体 42.2MB（仓耳今楷 36.1MB）、品牌 PNG 2.8MB、主 CSS 198KB gz。

**做法**

1. **楷体子集化**：`TsangerJinKai02-W04/W05.ttf` → woff2，字符集 = GB2312（6763 字）+ 常用标点 + 拉丁；预计每套 2–3MB，合计 ≤ 6MB（-30MB）。
2. **按需加载**：楷体 `@font-face` 与 `data-reading-font` 切换只在实际使用阅读字体时注入（`document.fonts.load` 或动态 `<link rel=stylesheet>`）；正文首屏走 Noto Serif 分片。
3. **Noto 分片保留**：100 个 unicode-range 分片是正确做法，不改；但把它的 `@font-face` 移出主 CSS（延迟加载）。
4. **品牌图**：头像与 4 张表情 → WebP（质量 82）+ 2 档尺寸（256/1024），目标 ≤ 600KB。
5. **首屏预算**：主 JS ≤ 110KB gz、关键 CSS ≤ 120KB gz、首屏字体 ≤ 1MB、图片 ≤ 600KB。

**验收**：`npm run build` 后 dist 资源统计；首屏 Network 瀑布（本地 file:// 模拟 Electron）无 >1MB 阻塞资源；阅读器首次进入额外加载 ≤ 6MB；字体回退链在缺字体时不破版。

**风险**：子集删字导致生僻字回退到 Noto（可接受，因为保留回退链）；需抽样对比 GB2312 边界字。

---

## 5. 两个此前待决问题的结论

### 5.1 `practice` / `learning_update` SSE 帧 → **删除**

**证据（全仓库核对）**

- `web/backend/events.py:92` 只在 artifact 类型 ∈ {`citation`, `practice`, `learning_update`} 时发这两个帧；但**全仓库没有任何生产者会产出这两种 artifact 类型**（grep `type": "practice"` / `learning_update` 命中为 0）。
- 练习卡走的是另一条路：`practice_ready` 在 `events.py:96-97` 被包装成 `chat_artifact`，前端 `ChatPage.tsx:986` 正常处理 —— 练习闭环**不依赖**这两个帧。
- `citation` 有真实生产者（`tools/rag_search.py:97`、`tools/web_research.py:78`），前端也在消费 → **必须保留**。
- 唯一客户端是本仓库 Web 前端（将来 Electron 打包同源）→ 无外部消费者。

**改动清单**

| 文件 | 改动 |
|---|---|
| `web/backend/events.py` | 判断集合改为 `{"citation"}`；补注释说明为什么只留 citation |
| `web/frontend/src/lib/chatStreamEvents.ts` | 从 `CHAT_STREAM_EVENT_KINDS` 删除两个名字 |
| `web/frontend/src/lib/api.ts` | 从 `ChatStreamEvent` union 删除两个成员（类型级对账会强制同步） |
| `web/frontend/src/hooks/useChatStream.ts` | `IGNORED_STREAM_EVENTS` 清空（保留机制与注释） |
| `hooks/useChatStream.test.ts` / `lib/chatFold.test.ts` | 删除对应样本，改为用未处理事件验证「状态不变」 |
| 新增后端测试 | `to_web_events` 对 `practice_ready` 必须映射成 `chat_artifact` |

**为什么不选择「消费」**：没有生产者 = 没有内容可消费；若将来要「掌握度实时更新」，正确做法是**新增一个明确定义的 artifact 类型 + 定义它的 UI**，而不是复活空壳。

**验收**：`grep -r 'practice\|learning_update' web/frontend/src web/backend` 只剩「练习相关业务词」；F3 对账测试绿；后端 1,845 + 前端 292 全绿。**工作量约 0.5 天，风险低。**

### 5.2 换述/语义人工评测集 → **要写，分三层、共 40–60 条**

| 层 | 内容 | 数量 | 存放 | 何时跑 |
|---|---|---|---|---|
| L1 关键词回归 | 合成语料 + `--generate-cases` 自动生成 | 20–30（自动） | 仓库 `tests/eval/` | **CI**（不需向量） |
| L2 换述基准（合成语料） | 人工写「换一种说法」的问题 | 15–20 | 仓库 `tests/eval/semantic_cases.jsonl` | 本地（无 embedding 自动 skip） |
| L3 真实库人工集 | 换述 25–35 + 关键词 15–25（自动） | **40–60** | `.knowledge/eval/cases.jsonl`（gitignore，真实内容不进仓库） | 本地（**先停服务**，单进程 Qdrant 限制） |

**为什么是这个数量**

- 要回答的是**配对比较**问题（同一批查询，hybrid vs fts_only）；每条 case 约占 2–3% 粒度，25–35 条换述足以检出 **≥15% 的绝对 hit@5 差异**。
- 检索评测惯例是 **25–50 个主题**（TREC 主题集规模研究：[Topic Set Size Redux](https://dl.acm.org/doi/pdf/10.1145/1571941.1572138)）。
- 真实库 47 份资料 → 30 条换述 ≈ 0.6 条/资料，覆盖够用；后续可扩到 60–90（1–2 条/资料）。
- 关键词集**不手写**：`cases_from_workspace` 已能确定性生成（上一轮已交付），人力全花在换述上。

**决策规则（2026-10-17 实测后修正）**

> 原规则写的是「换述集 hit@5 提升 ≥15pp」。**实测发现这个判据在数学上不可达**：FTS 的换述基线已经是 87.5%，绝对提升上限只有 12.5pp。改为相对判据：
>
> 保留向量腿需**同时**满足：
> 1. 关键词组 hit@5 **不下降**（任何下降即回滚）；
> 2. 换述组**找回条数 ≥ 弄丢条数 + 2**；
> 3. 换述组 MRR 相对提升 **≥10%**。
> 否则：降权，或把向量腿从默认路径摘掉（继续只跑 FTS + 降级提示）。

**✅ 2026-10-17 已执行（真实库，24 条换述 + 5 条关键词对照）**：

| 组 | fts_only hit@5 | hybrid hit@5 | fts_only MRR | hybrid MRR |
|---|---|---|---|---|
| 换述 | 0.875（21/24） | **0.958（23/24）** | 0.550 | **0.660（+20%）** |
| 关键词 | 1.000（5/5） | 1.000（5/5） | 0.900 | **1.000** |

逐题：向量腿**找回 3 条**、**弄丢 1 条**（`sample.md` 那条待观察）、零双向漏检 → 三条判据全部满足 → **保留向量腿（hybrid 为默认）** ✓。用例文件在 `note/vault/.bobodan/eval/cases.jsonl`（gitignore ✓），方法与基线见 `docs/RAG_EVAL.md`。

**执行方式**

1. 格式扩展：「kind: keyword | paraphrase」「source: generated | human」字段（向后兼容）。
2. 同一批用例跑两次配置：① `embedding_backend = local`（占位 provider → fts_only）② 真实配置（hybrid）。
3. 报告输出 hit@5 / MRR 按 kind 分组，并给出差值。
4. 停服跑（单进程 Qdrant），跑完重启服务。

**成本**：30 条换述 ≈ 1.5–2 小时人工 + 30 分钟跑测；**无开发成本**（评测器与生成器已交付）。产物：`docs/RAG_EVAL.md`（用法 + 基线数字 + 决策记录）。

---

## 6. 实施顺序与里程碑

| 阶段 | 内容 | 交付 | 预估 | 提交粒度 |
|---|---|---|---|---|
| **M0** | 基线快照 | 本文档 + 门禁数字 | 已完成 | 1 |
| **M1** | W-F1 CSS 分层 | ✅ **已完成（2026-10-17，提交 15ebc16 之后的 M1 提交）**：入口 6 行 + tokens/app/fonts 三层；字体异步 chunk；**主 CSS 197.77 → 31.64 kB gz（-84%）**；新增 cssLayers 契约 4 条；裸毫秒棘轮归零（预算 4 → 0） | 1–2 天 | 1 |
| **M2** | W-F2 页面拆分 | ✅ **达标（2026-10-17）**：AppShell 790→**599**；api.ts 1,407→**19**（9 子模块 ≤600）；SettingsDialog 289；**ChatPage 1,031→579**、**LibraryPage 1,526→544**（store-lift：单一 ctx 边界 + 分块视图抽取）。全部 ≤600 ✓，行为零变化 ✓ | 2–3 天 + 手工 | 22 |
| **M3** | W-F3 视觉融合 | ✅ **完成（2026-10-17，feat/frontend-m3）**：①令牌层（surface/hairline/ring/圆角/高度 + 契约）；②浮层发丝边落地 ✓；③表面阶梯落位（11 个关键表面）；④输入区统一 + 滚动遮罩 + 渐变预算；⑤组件圆角令牌化 + **关键页实拍验收**（Chat / Library / Settings AI / Settings 界面四图）。全部行为零变化，门禁全绿 | 2–3 天 | 每技法 1 |
| **M4** | W-F4 动效/IME | ✅ **完成（2026-10-17，feat/frontend-m4）**：弹簧令牌 + 按压/浮层入场/通知动效 ✓、CJK IME 合成守卫（`lib/ime.ts`，先红后绿 2 条回归）✓、图谱拖拽 4px 指针死区（`lib/pointer.ts` + 3 条单测）✓、减少动效 CSS 兜底 ✓、骨架屏微光规则与 `--dur-shimmer: 1200ms` ✓、**裸缓动棘轮 15 → 0** ✓ | 1–2 天 | 每项 1 |
| **M5** | W-F5 字体/包体 | 子集化 + 按需加载 + 图片优化 | 1–2 天 | 每资源 1 |
| **M6** | 打包前验收 | 五层验收报告 + 打包清单 | 1 天 | 1 |

**总计**：约 **8–13 个工作日**（按半天为一个可提交单元）。每阶段结束必须过五层验收，否则不进下一阶段。

---


### 6.1 M2 验收结论（2026-10-17，按**两档验收**收口 → 当日已全部达标）

用户选择「两档验收」：能机械、低风险拆完的记为**已达标**；逻辑层交织、手工成本超过剩余时间窗的记为**已知债**并给出后续方案。依据：两次脚本化尝试（扁平抽 hook / container-hook-view）都因「deps 声明 ≈ 搬出收益」与「effect 块边界不可靠」失败，均已整体回退并记账（见 CHANGELOG 2026-10-17 两条）。

| 档 | 文件 | 前 → 后 | 说明 |
|---|---|---|---|
| ✅ 达标 | `components/AppShell.tsx` | 790 → **599** | 抽出 `shell/LearningContext`（103）/ `shell/ContextPanel`（69）/ `shell/nav`（17）/ `shell/types`（65），类型经 AppShell re-export，调用方零改动 |
| ✅ 达标 | `lib/api.ts` 门面 | 1,407 → **19** | `api/http`（53）/ `api/types`（136）/ `api/transport`（395）/ `api/endpoints/{library 227, practice 225, workspace 200, wiki 133, chat 63}` —— **全部 ≤600** |
| ✅ 达标 | `components/SettingsDialog.tsx` | 289 → 289 | 原本已在 600 以内 |
| 🟡 已知债 | `pages/ChatPage.tsx` | 1,185 → **1,031** | 已抽 `pages/chat/chatPrimitives`（137，纯原语/工具）；剩余为「状态 + effect + 处理器 + JSX」交织层 |
| 🟡 已知债 | `pages/LibraryPage.tsx` | 1,461 → 1,461 | 未动；与 ChatPage 同类结构 |

**已知债的后续方案（手工协议，不脚本切分）**：

> **更新（2026-10-17）**：手工协议仍是兜底 ✓，但**推荐路线已改为「store 化 + actions 无闭包」**（借鉴 openhanako）—— 见 [«FRONTEND_OPTIMIZATION_V2.md»](./FRONTEND_OPTIMIZATION_V2.md) §1：把状态搬进 zustand slice、处理器搬成模块级 action，可彻底消掉「依赖清单」这笔过路费 ✓。

1. **先视图层**：把 JSX 区（composer 约 106 行、transcript 约 42 行、welcome 约 21 行、artifactSurface 约 62 行）抽成组件 —— JSX 边界清楚，tsc 可校验，属性清单约 40 项（这是抽取成本的来源，必须接受）。
2. **再处理器族**：wiki 族（约 140 行）/ web 族（约 74）/ 交互族（约 90）/ 练习与设置族（约 92）各自抽 hook —— 每族依赖 8–12 项，用 `ReturnType<typeof useChatState>` 推导类型。
3. **每步只做一块**：搬 → tsc → 跑该页测试 → 再搬下一块；不跨块合并提交。
4. ChatPage 预计 3–4 轮、LibraryPage 3–4 轮（每轮一个可回滚提交）。

> **更新（2026-10-17 晚）**：两档验收的「已知债」已通过 **store-lift** 全部清零 ✓ —— ChatPage **579**、LibraryPage **544**（均 ≤600 ✓）；方法与过程见 [「FRONTEND_OPTIMIZATION_V2.md」](./FRONTEND_OPTIMIZATION_V2.md) §1 与 CHANGELOG 的 1–5 步记录 ✓。以下内容保留为历史过程记录。

**门禁证据（2026-10-17 实跑）**：后端 **1,853 passed** ｜ 前端 **47 文件 / 296 passed** ｜ tsc / lint / build **0** ｜ mock e2e **15** ｜ **live 7**（真实后端）。

---

## 7. 五层验收（每阶段都要跑）

### 7.1 结构

- `styles.css` 入口 ≤ 120 行；单文件 ≤ 600 行；`src/ui/` 原子组件 ≥ 10 个且都有四态实现。
- 复跑：`Get-ChildItem src -Recurse -Include *.tsx,*.ts,*.css | ForEach-Object { (Get-Content $_ | Measure-Object -Line).Lines }` 取最大值。

### 7.2 视觉

- 令牌契约：表面阶梯 / 圆角刻度 / 高度阶梯 / 发丝边 / 淡化遮罩都要有测试（扩展 `designTokens.test.ts`）。
- 关键页 Before/After 截图（Chat / Library / Practice / Settings / Reader），人工对比 + 保存到 `docs/screenshots/`（或本轮先放临时目录）。
- 对比度：正文/次要文字 ≥ 4.5:1，不得回归。

### 7.3 交互

- IME 合成中 Enter 不发送（新回归）；键盘可达（Tab 顺序、Esc 关闭、焦点环）；减少动效开关生效；滚动单写者回归不破。

### 7.4 性能（打包前红线）

| 指标 | 预算 | 测量 |
|---|---|---|
| 主 JS | ≤ 110 kB gz | `npm run build` 输出 |
| 关键 CSS（不含字体 face） | ≤ 120 kB gz | **31.64 kB gz ✅（M1 后；字体另为异步 chunk 166.01 kB gz）** | `npm run build` 输出 |
| 首屏字体 | ≤ 1 MB | dist 统计 + 网络瀑布 |
| 首屏图片 | ≤ 600 kB | dist 统计 |
| 阅读器额外字体 | ≤ 6 MB | dist 统计 |

### 7.5 回归

`.venv\Scripts\python.exe -m pytest -q`（1,845）｜ `npx vitest run`（292）｜ `npx playwright test e2e/interaction.spec.ts`（15）｜ `BOBODAN_E2E_LIVE=1 npx playwright test e2e/live.spec.ts --project=desktop`（7，需先起服务）｜ `npx tsc --noEmit` ｜ `npm run lint` ｜ `npm run build`。

---

## 8. 风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| CSS 拆分后层顺序/覆盖失效 | 视觉回归 | `@layer` 显式排序；拆分前后截图对比；单 commit 可整体回滚 |
| 页面拆分破坏订阅/滚动/聚焦 | 功能回归 | F3 订阅对账、F7 滚动行为测试是安全网；每步跑 vitest + mock e2e |
| 字体子集丢字 | 生僻字回退 | 保留 Noto Serif 回退链；抽样 GB2312 边界字；保留原 ttf 于构建输入目录（不进 dist） |
| 新令牌与旧值混用 | 视觉不一致 | 新代码优先新令牌；旧值不批量替换，逐步收敛；契约测试记录数量 |
| 性能预算挤压功能 | 功能被砍 | 预算按「不回归」起步，先降体量再谈加功能；每阶段复测 |

回滚策略：每个里程碑一个独立 commit（或一个小系列），出问题 `git revert` 单个提交即可，不影响其它阶段。

---

## 9. 延后 / 不做

- **掌握度实时更新的 UI**：若将来需要，新增明确 artifact 类型（如 `mastery_update`）+ 定义 UI，再改服务端；不复用空壳事件。
- **framer-motion / motion**：除非出现纯 CSS 无法表达的交互（当前没有）。
- **完整组件库 / Storybook**：不做。
- **Tailwind 工具类迁移**：不做；继续「令牌 + 语义类」。
- **TUI / 移动端**：本轮不做。
- **服务端检索/证据链改动**：除 §5.1 死代码删除外不动。

---

## 10. 参考

- 参考仓库：`open-claude-ui`（`ddf3aea`）—— `docs/v1/01-设计哲学与设计令牌体系.md`、`02-基础原子组件与交互控件.md`、`03-会话核心流与指令交互引擎.md`、`04-动效物理学、着色器与环境光影.md`、`docs/v2/05-生产级参考实现代码.md`
- 主题集规模：[Topic Set Size Redux (ACM)](https://dl.acm.org/doi/pdf/10.1145/1571941.1572138)
- 浏览器能力：`color-mix()` / `mask-image` / `animation-timeline` 见 MDN
- 本仓库依据：`docs/DESIGN.md`（本轮同步重写）、`docs/ROADMAP.md` W5、`CHANGELOG.md` 2026-10-15/17 条目
