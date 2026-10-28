# Bobodan 视觉系统优化方案（参考 OpenHanako）

> 版本：2026-10-19 · 状态：**已归档（2026-10-28 移入 `archive/frontend/`），评估底稿，已被 [`../../FRONTEND_UPGRADE_PLAN.md`](../../FRONTEND_UPGRADE_PLAN.md) 取代为实施依据**
> 保留原因：记录本轮审计数据、与 OpenHanako 的冲突裁决和样式治理线索，便于追溯
> 阅读边界：本文的令牌重编号、动画收敛、页面构图和迁移顺序不能直接照做；正式实施只看 `FRONTEND_UPGRADE_PLAN.md`
> 目标项目：`web/frontend`；参照项目：`openhanako-reference/desktop/src`；硬边界：`web/frontend/src/lib/designTokens.test.ts`
> 本文所有行号以 2026-10-19 工作区实测为准：`app.css` 共 2,323 行，`tokens.css` 179 行，`designTokens.test.ts` 511 行。

---

## 0. 一句话判断

1. Bobodan 的根本问题不是"没有设计系统"，而是**棘轮看住的地方已经干净（<12px 字号=0、裸毫秒=0、`transition: all`=0），棘轮没看住的地方全部漂移**——字号上分布（596 处声明、20+ 种取值）、14 种行高、370+ 处裸间距、重复 keyframes、以及几十处写死的亮色主题字面量，全部是"按页面分批追加、无全局复核"的产物。
2. Hana 最值得借的一条是**用墨色明度分级代替"字号+字重"堆层级**——它直接打中 Bobodan 最大的漂移面（315 处 12px 里有一大半是在用字号缩小来表达"这是次要信息"）。
3. 最不该借的一条是 **0.62rem（≈9.9px）超小字档**——它直接撞碎当初从 226 条压到 0 的 12px 硬下限，且中文笔画在 10px 下的可读性损失没有任何收益能抵回来。

### 0.1 需要拍板的决策点（4 个）

| # | 决策点 | 本方案建议 | 详见 |
|---|---|---|---|
| D1 | 字号下限：维持 12px 还是承认 Hana 的 9.9px | **维持 12px** | §2 冲突 1 |
| D2 | 圆角：走 Hana 方角（2/3/4）还是保留 6/8/12/16 | **保留现刻度** | §2 冲突 2 |
| D3 | 纸色：换 Hana 暖黄纸（#F5EFE4）还是保留偏灰纸（#f5f4ed） | **保留偏灰** | §2 冲突 3 |
| D4 | 间距刻度：保留 `--space-1..7` 还是重编号为 px 同名（`--space-2/4/6/8/…/48`） | **重编号（带别名过渡期）** | §6 |

---

## 1. 现状诊断

### 1.1 数据背后的成因

**为什么 12px 有 315 处。** 12px 是契约测试的硬下限。所有想写成 10/11px 的次要文字被门禁挡回后，统一落在 12px——12px 于是成了"次要信息"的默认倾倒场。实测分布证实这一点：`.source-chip`、`.message-references button`、`.topbar-title span`、`.note-item-meta`、`.settings-*-row`、`.wiki-*` 元数据、`.library-setup-dialog label`——几乎全部是"元信息/标签/辅助说明"三类。这不是 315 个独立决策，是**同一个决策被执行了 315 次**："这段文字不重要，缩小它"。而 Hana 的答案是：不重要的文字不是更小，而是更浅（墨色五档）。Bobodan 手里其实已经有 `--muted`/`--faint`，但页面作者的第一反应仍是缩字号，因为**缩字号一行就生效，调色阶没有明确的档位指引**。

**为什么 line-height 有 14 种。** tokens.css 里根本没有行高令牌。1.5/1.55/1.6/1.65/1.7/1.75/1.8/1.85/1.9 这些相邻差 0.05 的取值，肉眼不可辨，是每位作者"凭感觉微调"的残留。没有令牌 = 没有可引用的名字 = 每次重写。这是纯粹的**令牌缺失**，不是执行问题。

**为什么 17 个 keyframes 里有两对重复。** `ui-modal-in` 在 app.css:83 和 2288 各定义一次；`notice-in` 在 1116 和 2291 各定义一次且**曲线不同**（1116 是 `translateY(6px)→none`，2291 是 `translateY(6px) scale(0.99)` 且只有 from 帧），后者静默覆盖前者。2287–2291 这段是 M3/M4 批次"追加到文件末尾"的痕迹：作者不知道 1,100 行之前已有同名定义，也没有任何机制提醒他。Hana 的 animations.css 用单一文件 + 头部注释 + 旧名对照表解决了这个问题——**注册表模式**，一个文件就是全部动画的清单。

**共同的成因**：样式按页面分批追加，复核环节只有棘轮测试，而棘轮只覆盖四个维度（<12px 字号、裸 ease、刻度外圆角、裸毫秒）。**漂移精确地发生在棘轮盲区里**：≥12px 的裸字号、行高、间距、颜色字面量、动画定义，全都无人看守。

### 1.2 新增实测发现（本次审计）

| # | 位置 | 问题 |
|---|---|---|
| F1 | app.css:2287–2291 | 重复 keyframes 块，`notice-in` 曲线分叉（见上） |
| F2 | app.css:1319 `.practice-summary` 一族 | `var(--blue, #36506c)`、`var(--clay, #b0714e)`、`var(--ink, #2c2a24)`、`var(--sage-deep, #5d7a4a)`、`var(--paper-soft, #faf8f4)` —— **fallback 值与真实令牌全部不一致**（真实值 #1b365d / #b86f4b / #2e2b27 / #4f6e4c / #faf9f5）。这是从另一个调色板整块复制来的，fallback 永远不会触发，但一旦令牌被删就会静默变成错误的颜色 |
| F3 | app.css:788 `.composer` | `background: rgba(250, 248, 242, 0.98)` —— 约等于 `--paper-soft` 但不是它；暗色主题只翻转 tokens.css 里的变量，**这个字面量在暗色下不会翻**。同类：:636 `.topbar` 的 `rgba(245,244,237,0.93)`、:785 `.composer-wrap` 渐变里的 `rgba(245,244,237,0)`、:686 `.user-message` 的 `color: #26364c` 和 `rgba(232,237,243,0.68)` |
| F4 | `.reader-prose` 定义三次 | app.css:983（`font-size: var(--body-font-size)`=17px）、:1294（`font-size: 16px; line-height: 1.9`）、:1390（再写一次 max-width）。**后定义的 16px 覆盖了 DESIGN.md 规定的 17px 正文**——文档与实现已经分叉，且无人察觉 |
| F5 | app.css:1149 `.library-tabs` | `border-radius: 7px`（刻度外）、`background: var(--parchment)`（legacy 别名）。同类 7px：:1031 `.notes-search`、:1319 `.library-setup-dialog input`、:1158 `.library-context-icon` |

### 1.3 最该先改的 5 个位置

| 优先级 | 位置 | 改法 | 收益 |
|---|---|---|---|
| 1 | app.css:2287–2291（重复 keyframes）+ 全部 17 个 `@keyframes` | 抽到 `src/styles/animations.css`，去重、统一命名（§7） | 消除一个**正在发生的静默覆盖 bug**（notice 入场曲线不是设计值）；动画从此有注册表 |
| 2 | app.css:1319 `.practice-summary` 一族 | 删掉全部错误 fallback，写 `var(--blue)` 裸引用 | 消除一整块异源色板（约 10 条声明）；让"无 fallback 的 var() 必须已定义"这条既有门禁真正管住它 |
| 3 | app.css:788/785/636 composer 三处 + :686 `.user-message` | 字面量换成 `--paper-soft` / `rgb(var(--accent-rgb) / …)` 等 | 修复暗色主题下最高频可见组件（输入框+顶栏+用户气泡）的底色泄漏 |
| 4 | `.reader-prose` 三处定义（983/1294/1390） | 合并为一条规则，字号回到 `var(--body-font-size)`，行高入令牌 | 恢复 DESIGN.md 的 17px 正文约定；阅读器排版重新有单一来源 |
| 5 | 7px 圆角四兄弟（1149/1031/1319/1158） | 全部贴到 `var(--radius-md)`（8px） | 棘轮预算 60 → 约 56；与 M3 已校准的 7 个关键组件对齐 |

---

## 2. 吸收清单

先裁决三处冲突，再逐条过吸收项。

### 冲突 1：字号下限 —— **维持 12px，不照搬 Hana 六档**

判断：**保留 `designTokens.test.ts` 的「低于 12px 的 font-size 必须为 0」门禁，值不变。**

理由：

1. **场景不同**。Hana 是 IDE 密度的桌面工具（侧栏、inspector、工具条密布），9.9px 用在角标计数、键位标这类"装饰性元信息"上。Bobodan 是阅读产品，`--body-font-size` 17px、正文衬线、行高 1.7–1.9——它的 12px 承担的是**来源标注、引用计数、复习到期时间**这类用户要真的去读的文字，不是装饰。
2. **中文笔画密度**。10px 下中文（尤其衬线体）的横画并线、口字塌成实心，这不是审美偏好是渲染事实。Hana 的 0.62rem 档配的字体是 Inter/系统黑体为主的西文语境。
3. **棘轮的方向性**。这条门禁从 226 压到 0 是单向棘轮，放宽它等于告诉所有后续贡献者"下限可以谈"。下限一旦可谈，12px 倾倒场问题会以 10px 的形式复活。
4. Hana 六档里真正有价值的不是最小档，而是**档位间的固定比率**。Bobodan 用自己的 8 档（§5）获得同样的秩序，不碰下限。

若未来真的要更小字（如图表刻度）：走 SVG `text` 或 canvas 渲染，不走 CSS font-size，门禁不动。

### 冲突 2：圆角刻度 —— **保留 6/8/12/16，不走方角**

判断：**不改刻度，把 60 条刻度外预算逐批压到 ≤10。**

理由：

1. **成本不对称**。走方角意味着：改 tokens.css 四个值 → DESIGN.md §4.6 契约表同步 → M3 组件校准契约（`.composer` 等 7 个组件必须 `var(--radius-md)`）全部重拍 → 60 条刻度外声明按新刻度重算（2/3/4 刻度下，现有的 6/8/12/16 全部变成"刻度外"，预算从 60 暴涨到几百）。买来的只是角形状差异，不是一致性增益——**一致性来自"都在刻度上"，不来自刻度是方是圆**。
2. **系统耦合**。Hana 的方角能成立，是因为它同时配了 0.5px 发丝边、几乎无阴影、纸纹贴图、9.9px 小字——一整套密实语言。Bobodan 是 17px 疏朗正文 + 暖灰纸 + 柔和阴影，方角会与阅读区的长文排版打架（长圆角卡片是阅读容器，不是工具面板）。
3. **真正的病灶不是圆角大小，是 7px 这类"刻度外 ±1"的漂移**（1149/1031/1319/1158 行）。这用现有棘轮往下压就能解决，不需要换刻度。

方角美学里**要借的是原则不是数值**：控件之间的圆角差异必须有语义（§8 给每个组件固定档位），不许同层元素出现两种圆角。

### 冲突 3：纸色 —— **保留偏灰纸，不换 Hana 暖黄**

判断：**`--paper` 维持 #f5f4ed 不变；饱和度门禁维持现状，不放宽。**

算账（HSL 饱和度，与 `designTokens.test.ts` 同算法）：

| 色 | 饱和度 | 相对画布 |
|---|---|---|
| Bobodan `--paper` #f5f4ed | 0.286 | — |
| Bobodan `--paper-sunken` #f0eee6 | 0.250 | ≤ 画布 ✓ |
| Hana `--bg` #F5EFE4 | **0.460** | — |
| Hana `--sidebar-bg` #EFE8DB | **0.384** | ≤ 画布 ✓（但绝对值已超 Bobodan 出事故时的 0.35） |
| Bobodan 2026-09-14 事故色 #efeade | 0.35 | > 当时画布 ✗（橄榄黄带事故） |

另外 Hana 的三档若直接搬进 Bobodan，会撞另一条门禁：`--paper-sunken` 与画布的逐通道差（6/7/**9**）和 `--paper-soft` 的（6/8/**10**）**超过每通道 ≤8/255 的上限**。要换纸色就得同时放宽两条测试，而这两条测试各自对应一次真实回归。

不换的根本理由：Bobodan 的整套语义色（墨蓝 #1b365d、sage、clay）是在偏灰纸上调的对比度；暗色主题（炭棕 #1c1b19）也是从灰纸推导的。换纸色 = 全链路重校，收益只是"更像 Hana"。**Hana 值得借的是"三档靠明度差区分"的结构，这个结构 Bobodan M3 已经有了**，色值不动。

### 逐条吸收裁决

| Hana 做法 | 裁决 | 落到哪 | 理由 / 收益 |
|---|---|---|---|
| 墨色五档（#2A2622→#B8B0A3）代替字号+字重表达层级 | **改造后采用** | tokens.css 新增 `--ink-ghost`；§5 排版规则"先调色阶、再调字号、最后调字重" | Bobodan 已有三档墨色（ink/muted/faint），补一档幽灵色用于占位符与禁用；不照搬五个色值（#2A2622 与 --ink #2e2b27 差异肉眼不可辨，照搬只会制造第二套近似色） |
| 唯一强调色且面积极小（印章青 #537D96） | **采用（维持现状+补契约）** | DESIGN.md §4.3 加一条"accent 色每屏面积 ≤10%"的既有规则不变；新增契约：accent 实色填充只允许出现在主按钮/当前导航/选中态 | Bobodan 的 `--accent` == `--blue` 已是单强调色，无需换色。要防的是 drift（clay/sage 抢戏），用契约看住 |
| 方角 + 0.5px 发丝边 + 几乎无阴影 | **发丝边与弱阴影采用（已落地），方角拒绝** | M3 的 `--hairline`/`--ring` 保留；本方案把"内容区每屏抬升 ≤1 处"升级为契约候选 | 方角拒绝理由见冲突 2；阴影克制的原则吸收 |
| 纸面三档靠明度差区分 | **原则采用（已落地），色值拒绝** | 无改动 | 冲突 3 |
| 动画集中单一文件、统一命名（animations.css + `hana-*` + 旧名对照注释） | **采用** | 新建 `src/styles/animations.css`，前缀 `bb-`，头部注释保留旧名对照（照抄 Hana 的注释格式） | 直接消灭 F1 类 bug；新动画必须先注册再使用 |
| 间距刻度密度（10 档 vs Bobodan 7 档） | **改造后采用** | tokens.css 间距刻度重编号为 px 同名：`--space-2/4/6/8/10/12/16/20/24/32/40/48`（12 档） | 实测裸值高频点 2/6/10/20px 正是现刻度缺档（2px×44、6px×68、10px×67、20px×13），补档后这些裸值都有家可归；不照搬 Hana 的 rem（Bobodan 全栈 px，见 §3） |
| 时长三档 + 缓动四条 | **时长不采用（现值等价），缓动补一条** | 新增 `--ease-in: cubic-bezier(.7, 0, .84, 0)` 专用于退场 | Bobodan 120/160/220ms ≈ Hana 100/150/250ms，换数值是纯 churn；但 Bobodan 缺一条退场缓动（现在退场也用 ease-out，方向不对） |

---

## 3. 拒绝清单

| Hana 做法 | 为什么不适合 Bobodan | 硬学的后果 |
|---|---|---|
| 0.62rem（≈9.9px）字档 | 冲突 1：阅读产品 + 中文渲染 + 硬棘轮 | 契约测试当场变红；放宽门禁则 226→0 的收敛成果作废 |
| 主题层方角 2/3/4px | 冲突 2：与 17px 疏朗排版和既有契约不兼容 | 60 条圆角预算失控暴涨；M3 组件契约全部重签 |
| 暖黄纸 #F5EFE4 三档 | 冲突 3：饱和度 0.46 超过事故阈值 0.35，逐通道差超 8/255 上限 | 两条契约测试必须放宽；侧栏重回橄榄黄带风险；语义色与暗色主题全链路重校 |
| 纸纹贴图系统（rice-paper.png 三层混合 + 亮度补偿伪元素） | Bobodan 的设计定位是平涂暖纸（DESIGN.md §4 无纹理）；纹理在 CJK 小字上增加背景噪声；多一个 160px 贴图资产与三层 blend-mode 渲染成本 | 正文可读性下降；暗色主题要额外补偿；打包体积 +1 资产；与"每屏渐变 ≤1"的配额哲学冲突 |
| rem 字号体系（`--fs-*: 0.xxrem`） | Bobodan 全栈 px（`--body-font-size: 17px`、596 处 px 声明）；Windows 桌面打包场景用户不改根字号，rem 的"随用户缩放"优势用不上，反而引入 0.62rem=9.92px 这类非整数渲染 | 字阶换算多一层心智成本；与现有 px 声明混用时出现 12.5px 这类半档的同类问题换个单位复活 |
| CSS Modules per feature | FRONTEND_OPTIMIZATION_V2 已裁决：继续"令牌 + 语义类"，不引入 CSS Modules | 推翻已完成的 M1 分层；类名契约测试（M3 表面阶梯落位按类名断言）全部失效 |
| `content` 属性动画（hana-typewriter-dots） | 用动画改 `content` 读不出、选中不了，可访问性差 | 流式状态指示的可访问性回归；Bobodan 现有墨点动画（process-ink）用 opacity/transform 已是正确路线 |

这份清单只有 7 条，因为 Hana 其余部分（令牌分层、主题 override 机制、组件四态）Bobodan 在 M1–M4 已经等价落地，不属于"拒绝"而属于"已有"。

---

## 4. 目标设计令牌

可直接替换 `tokens.css` 的令牌表。**改动摘要**：纸面/墨色/语义色/描边/圆角/阴影**不改值**；新增字号 8 档、行高 4 档、字重 3 档、墨色补 1 档、间距重编号并扩到 12 档、缓动补 1 条、弹簧收敛到 4 条、控件高度补齐 6 档。标注：🆕 新增 / ✏️ 改值 / 🔁 改名 / ⚖️ 契约相关（需同步 DESIGN.md §4.6 与测试 OWNED 表）。

### 4.1 亮色主题（`:root`）

| 令牌 | 值 | 用途 | 变化 |
|---|---|---|---|
| **纸面** | | | |
| `--paper` | `#f5f4ed` | 页面画布 | 不变 |
| `--paper-soft` | `#faf9f5` | 抬升面：卡片、菜单、选中行 | 不变 |
| `--paper-sunken` | `#f0eee6` | 停靠面：侧栏、右栏、内嵌块 | 不变 |
| `--parchment` | `var(--paper-sunken)` | legacy 别名 | ⚠️ 计划删除（见 §10 B6），删除前保留 |
| `--surface-0..3` | 现有别名 | 表面阶梯 | 不变（契约固定为别名） |
| **墨色** | | | |
| `--ink` | `#2e2b27` | 正文主文字 | 不变 |
| `--ink-soft` | `#5c554b` | 次级强调文字 | 不变 |
| `--muted` | `#5b544a` | 次要文字 | 不变 |
| `--faint` | `#71685c` | 辅助文字（≥4.9:1） | 不变 |
| `--ink-ghost` | `#9a9184` | 占位符、禁用文字（对比度 ≈2.8:1，**禁止承担正文**） | 🆕 |
| **语义色** | | | |
| `--blue` / `--blue-soft` / `--blue-wash` | 现值 | 阅读主色 | 不变 |
| `--accent` | `#1b365d` | 唯一强调色 | 不变 |
| `--accent-pressed` | `#14294a` | 主按钮/强调件按下态 | 🆕（对齐 Hana 的 accent→pressed 双档结构，色值按 --blue 加深推导） |
| `--sage` / `--sage-wash` / `--sage-deep` | 现值 | 正向状态 | 不变 |
| `--clay` / `--clay-wash` | 现值 | 温度点缀（每屏 ≤5%） | 不变 |
| `--petal-wash` | 现值 | 私人情绪 | 不变 |
| `--danger` | `#934d43` | 错误 | 不变 |
| `*-rgb` 三元组 | 现值 + `--accent-pressed-rgb: 20, 41, 74` | 半透明组合 | 🆕 一条 |
| **描边** | | | |
| `--border-subtle` / `--border` / `--border-strong` | 现值 | 三档 | 不变 |
| `--hairline` / `--ring` | 现值 | 发丝边与外环（2dppx 减半） | 不变 |
| **圆角** | | | |
| `--radius-sm/md/lg/xl` | 6/8/12/16px | 刻度（棘轮刻度不变） | 不变 |
| `--radius-xs` / `--radius-control` / `--radius-panel` / `--radius-pill` | 2/10/18/999px | 补充档 | 不变；⚖️ DESIGN.md §7.1 的 `--radius-bubble` 计划**取消**（文档与实现分叉，以 tokens.css 为准） |
| **阴影** | | | |
| `--shadow-soft/lift/float/dialog` | 现值 | 四级 | 不变 |
| **间距** | | | |
| `--space-2` | `2px` | 光学对齐、chip 内距 | 🆕（高频裸值 44 处的家） |
| `--space-4` | `4px` | 图标-文字间隙 | 🔁 原 `--space-1` |
| `--space-6` | `6px` | 紧凑控件内距 | 🆕（68 处） |
| `--space-8` | `8px` | 控件内距基准 | 🔁 原 `--space-2` |
| `--space-10` | `10px` | 列表行内距 | 🆕（67 处） |
| `--space-12` | `12px` | 组件内部分隔 | 🔁 原 `--space-3` |
| `--space-16` | `16px` | 卡片内距 | 🔁 原 `--space-4` |
| `--space-20` | `20px` | 区块内分隔 | 🆕（13 处） |
| `--space-24` | `24px` | 区块间分隔 | 🔁 原 `--space-5` |
| `--space-32` | `32px` | 段落/面板间距 | 🔁 原 `--space-6` |
| `--space-40` | `40px` | 页面上边距 | 🆕 |
| `--space-48` | `48px` | 页面级分隔 | 🔁 原 `--space-7` |
| `--sidebar` / `--context` / `--content-width` | 252/304/720px | 三栏 | 不变 |
| **字号** | | | |
| `--fs-micro` | `12px` | 元数据：时间戳、计数、角标、 eyebrow 标签 | 🆕 ⚖️ |
| `--fs-caption` | `13px` | 控件文字、次级标签、列表辅助行 | 🆕 ⚖️ |
| `--fs-ui` | `14px` | UI 正文：设置描述、对话框正文 | 🆕 ⚖️ |
| `--fs-body` | `16px` | 聊天正文、笔记正文 | 🆕 ⚖️ |
| `--fs-reading` | `17px` | 长文正文（= `--body-font-size`，别名） | 🆕 ⚖️ |
| `--fs-title` | `20px` | 区块/卡片标题 | 🆕 ⚖️ |
| `--fs-heading` | `24px` | 弹窗标题、页内大标题 | 🆕 ⚖️ |
| `--fs-display` | `32px` | 页面标题（`.page-heading h2`） | 🆕 ⚖️ |
| **行高** | | | |
| `--lh-tight` | `1.3` | 标题、单行控件 | 🆕 ⚖️ |
| `--lh-ui` | `1.5` | 控件内文字、紧凑列表 | 🆕 ⚖️ |
| `--lh-body` | `1.7` | UI 正文、聊天 | 🆕 ⚖️ |
| `--lh-reading` | `1.85` | 长文阅读 | 🆕 ⚖️ |
| **字重** | | | |
| `--fw-regular` / `--fw-medium` / `--fw-semibold` | 400 / 500 / 600 | 正文 / 强调 / 标题与标签 | 🆕 ⚖️（现有 650→600、700→600 收敛，见 §5） |
| **动效曲线** | | | |
| `--ease-out` | 现值 | 入场 | 不变 |
| `--ease-in` | `cubic-bezier(.7, 0, .84, 0)` | 退场、消失 | 🆕 ⚖️ |
| `--ease-in-out` | 现值 | 持续移动 | 不变 |
| `--spring-press/pop/panel/accent` | 现值 linear() | 按压/浮层/面板/强调 | 不变 |
| `--spring-micro` | `var(--spring-press)` | 过渡别名 | ✏️ 改为别名，B6 批后删除 ⚖️ |
| `--spring-base` / `--spring-macro` | — | **删除**（实测 0 处使用） | 🗑 ⚖️（OWNED 表同步删） |
| **时长** | | | |
| `--dur-fast/base/slow` | 120/160/220ms | 三档 | 不变 |
| `--dur-spin/ink/ink-soft/enter/shimmer`、`--delay-ink-a/b` | 现值 | 循环与入场专用 | 不变 |
| **控件高度** | | | |
| `--h-control-xs` | `24px` | chip、行内小按钮 | 🆕 ⚖️ |
| `--h-control-sm` | `28px` | 工具条按钮、紧凑下拉 | 不变 |
| `--h-control` | `36px` | 输入框、搜索框 | 不变 |
| `--h-control-lg` | `40px` | 标准按钮（`.primary-button` 现状 40px） | ✏️ 44→40 ⚖️ |
| `--h-control-xl` | `44px` | 列表行、触控目标 | 🆕 ⚖️ |
| `--h-topbar` | `68px` | 顶栏（`.topbar` 现状 68px） | 🆕 ⚖️ |

### 4.2 暗色主题（`[data-theme="dark"]`）

原则不变：**只翻颜色**（现有契约"暗色不重新定义字体/圆角/动效令牌"继续有效）。暖棕炭纸面保留，新增令牌全部给暗色值：

| 令牌 | 暗色值 | 说明 |
|---|---|---|
| `--paper` / `--paper-soft` / `--paper-sunken` | `#1c1b19` / `#242220` / `#141312` | 不变（暖棕炭，不是纯黑） |
| `--ink` / `--muted` / `--faint` | `#ece7dd` / `#bdb5a8` / `#9c9386` | 不变 |
| `--ink-ghost` | `#6e675c` | 🆕 比 faint 再暗一档 |
| `--accent` / `--accent-pressed` | `#a8c2e4` / `#c6d8ee` | pressed 在暗色是"更亮"（按压提亮，与亮色的按压加深对称） |
| `--accent-pressed-rgb` | `198, 216, 238` | 🆕 |
| 其余语义色 / 描边 / 阴影 / `--ring` | 现值 | 不变 |

高对比主题（`[data-contrast="high"]`）同样只补 `--ink-ghost: #b8b0a3` 一条，其余不变。

### 4.3 契约同步清单（这一批必须同一个提交内完成）

1. DESIGN.md §4.6 代码块：加上全部 🆕 令牌、改 `--h-control-lg` 值、删 `--spring-base/macro`、补 `--space-*` 新名。
2. `designTokens.test.ts` 的 `OWNED` 数组：加 `--space-2/6/10/20/40`（替代旧名）、`--ease-in`、`--ink-ghost`、`--accent-pressed`、`--h-control-xs/xl`、`--h-topbar`；删 `--spring-base/macro`；`--space-1..7` 从 OWNED 移除（过渡期作为别名存在，见 §10 B2）。
3. 纸张阶梯测试不动（色值未变，全部应直接通过）。

---

## 5. 排版方案

### 5.1 字阶：最终 8 档

| 档 | 值 | 行高 | 字重 | 用在哪 |
|---|---|---|---|---|
| `--fs-micro` | 12px | `--lh-ui` | 400/600 | 时间戳、计数、角标、eyebrow 大写标签（600）、来源 chip 内文字 |
| `--fs-caption` | 13px | `--lh-ui` | 400/600 | 按钮文字（600）、工具条、列表辅助行、tab |
| `--fs-ui` | 14px | `--lh-body` | 400 | 设置项描述、对话框正文、同步摘要 |
| `--fs-body` | 16px | `--lh-body` | 400 | 聊天消息、笔记正文、表单输入内容 |
| `--fs-reading` | 17px | `--lh-reading` | 400 | AI 回答长文、阅读器正文、Wiki 正文 |
| `--fs-title` | 20px | `--lh-tight` | 500 | 卡片标题、区块标题、对话框标题 |
| `--fs-heading` | 24px | `--lh-tight` | 500 | 弹窗标题、prose h1 |
| `--fs-display` | 32px | `--lh-tight` | 400 | 页面标题（`.page-heading h2`，衬线） |

**层级表达规则（吸收 Hana 墨色分级的核心）**：表达"次要"时，顺序是 ① 降色阶（ink→muted→faint）② 降字重（600→400）③ 最后才降字号，且字号最多降一档。写不出"为什么这处需要降两档字号"的理由，就不许降两档。

### 5.2 那 315 处 12px 怎么分流

按选择器族审计后的分流规则（数量为估算，**分批施工时以实测为准**）：

| 去向 | 判定标准 | 典型选择器 | 估计占比 |
|---|---|---|---|
| **留 12px**（→ `var(--fs-micro)`） | 纯元数据：用户扫一眼就够、不承担操作 | `.topbar-title span`、`.note-item-meta`、`.message-references small`、`.note-editor-hint`、时间戳/计数类 | ≈40%（~125 处） |
| **升 13px**（→ `var(--fs-caption)`） | 可点或参与操作判断的文字：按钮、chip、tab、select | `.source-chip`、`.message-references button`、`.library-switcher select`、`.notes-search input`、`.composer-references button`、`.settings-*-row` 的标签 | ≈40%（~125 处） |
| **升 14px**（→ `var(--fs-ui)`） | 成句的说明文字：摘要、描述、提示段落 | `.library-sync-summary` 内文、`.run-summary`、`.knowledge-context-block` 描述、`.library-setup-intro` | ≈15%（~50 处） |
| **个案处理** | 12px 出现在标题/正文位置的异常值 | 逐个看 | ≈5%（~15 处） |

12.5px（33 处）全部归并：控件文字→13，说明文字→14。13.5px（4 处）→14。15px（8 处）按语义归 14 或 16。理由：半档差异（0.5px）在 100% 缩放下的渲染差异依赖次像素，不同平台表现不一致，是"看起来差不多"的漂移源。

### 5.3 三条可执行规则

1. **中西混排**：中文与西文/数字之间不手动加空格，交给字体字面间距；新代码不再写 `&nbsp;` 或手动空格隔开中英文（DESIGN.md §5.5 既有规则的执行强化）。
2. **数字对齐**：一切表格、统计、倒计时、掌握度百分比所在的规则块加 `font-variant-numeric: tabular-nums`（落在 `.runtime-grid`、`.practice-summary`、`.review-*` 统计行、`.settings-*-row` 的数值列）。
3. **标点**：中文语境用「」与《》，英文引用用 ""；同一段不混用；句末标点只一个。文案类字符串的 lint 不做（成本高），但组件里的硬编码 UI 文案在 B8 批次人工过一遍。

---

## 6. 间距与密度方案

### 6.1 刻度与三层语义

刻度 12 档（§4.1），按数值分三层：

| 层 | 值 | 语义 | 例 |
|---|---|---|---|
| 组件内 | 2/4/6/8/10 | 一个控件内部的空隙 | 图标与文字 6px、chip 内距 4×8、输入框 0×12 |
| 组件间 | 12/16/20 | 同组元素之间 | 列表行间距、表单字段间距、工具条按钮 gap 8 |
| 区块间 | 24/32/40/48 | 页面级分隔 | `.page-heading` 与内容 32、卡片与卡片 24、页面上边距 40 |

**同屏值数量上限**：单一视口内出现的不同间距值 ≤ 4 种（比 DESIGN.md §6.1 的"3 种"放宽 1，因为实测三栏布局下 4 种是可达的下限；>4 种时一定有该合并的层）。

### 6.2 栏宽与 padding 定额

| 区域 | 规则 | 值 |
|---|---|---|
| 侧栏 `.sidebar` | padding | `var(--space-20) var(--space-16) var(--space-12)`（现 20/15/14，15/14 贴刻度） |
| 右栏 `.context-panel` | padding | 同上对称 |
| 页面容器 `.page-container` | padding | `var(--space-40) var(--space-40) calc(var(--space-48) * 2)`（现 44/40/90：44 贴 40，底部 90 是给 composer 的留白，保留语义改为计算值） |
| 顶栏 `.topbar` | 高 68 + padding `0 var(--space-24)` | 不变，令牌化 |
| 主内容 | `width: min(100%, var(--content-width))` 居中 | 不变 |

### 6.3 三页对照表（改前 → 改后）

**Chat**

| 选择器 | 现状 | 改后 | 说明 |
|---|---|---|---|
| `.conversation` | `padding: var(--space-6) var(--space-5) 170px` | `var(--space-32) var(--space-24) 170px` | 170px 是 composer 遮挡高度，新增注释说明；不硬塞进刻度 |
| `.user-message-wrap` | `margin-bottom: var(--space-5)` | `var(--space-24)` | 换名 |
| `.user-message-wrap .user-message` | `margin-bottom: 7px` | `var(--space-8)` | 7 贴 8 |
| `.assistant-heading` | `gap: 8px; margin-bottom: 14px` | `gap: var(--space-8); margin-bottom: var(--space-12)` | 14 贴 12（标题与正文的距离宜近不宜远） |
| `.message-references` | `gap: 5px` | `var(--space-6)` | 5 贴 6 |
| `.composer-wrap` | `padding: 22px max(24px,…) 27px` | `var(--space-20) max(var(--space-24),…) var(--space-24)` | 22→20、27→24 |

**Library**

| 选择器 | 现状 | 改后 | 说明 |
|---|---|---|---|
| `.library-toolbar` | `min-height: 64px; gap: 18px` | `min-height: 64px; gap: var(--space-16)` | 18 贴 16 |
| `.library-tabs` | `gap: 3px; padding: 3px; margin-bottom: 20px; radius 7px` | `gap/padding: var(--space-4)`；`margin-bottom: var(--space-20)`；`radius: var(--radius-md)` | 3 贴 4；7px 圆角见 §1.3 |
| `.library-context-bar` | `margin: -9px 0 22px; padding: 12px 4px; min-height: 76px` | `margin: 0 0 var(--space-24); padding: var(--space-12) var(--space-4)` | **-9px 负 margin 是对 tabs 下方间距的补偿 hack**，把 tabs 的 margin-bottom 改对之后负 margin 删除 |
| `.library-sync-summary` | `gap: 8px; padding: 10px 12px; margin-bottom: 12px` | `gap: var(--space-8); padding: var(--space-10) var(--space-12); margin-bottom: var(--space-12)` | 全部有档可归 |

**Reader**

| 选择器 | 现状 | 改后 | 说明 |
|---|---|---|---|
| `.reader-prose` | 三处定义（F4） | 合并一条：`max-width: var(--content-width); padding-top: var(--space-24); font-size: var(--fs-reading); line-height: var(--lh-reading)` | 见 §1.3 第 4 条 |
| `.reader-prose section` | `margin-bottom: 30px` | `var(--space-32)` | 30 贴 32 |
| `.reader-prose h3` | `margin: 0 0 3px; font-size: 20px` | `margin: 0 0 var(--space-4); font-size: var(--fs-title)` | |
| `.reader-section-prose h1/h2/h3` | 24/21/18px | `var(--fs-heading)` / `var(--fs-title)` / `var(--fs-reading)`+600 字重 | 21/18 不是档；h3 用字重而不是字号区分层级（§5.1 规则） |
| `.reader-actions` | `margin-top: 18px; gap: 8px` | `margin-top: var(--space-20); gap: var(--space-8)` | |
| `.reader-related-notes` | `gap: 8px; margin-top: 12px; padding-top: 12px` | 全部换令牌（数值不变） | |

---

## 7. 动效方案

### 7.1 最终曲线与时长

- **时长三档**：`--dur-fast` 120ms（按压、hover）、`--dur-base` 160ms（状态切换、浮层入场）、`--dur-slow` 220ms（弹窗、大块进场）。循环动画专用时长（spin/ink/shimmer）保留现状命名。
- **曲线六条**：`--ease-out`（入场）、`--ease-in`（退场，新增）、`--ease-in-out`（持续移动）、`--spring-press`（按钮/开关）、`--spring-pop`（浮层/卡片）、`--spring-panel`（抽屉/面板）。`--spring-accent` 保留定义但使用率 0，列入观察名单，B6 批若无新用途则删除。
- 不改数值。Hana 的 100/150/250ms 与本方案 120/160/220ms 差异无感知意义，换值是纯 churn。

### 7.2 keyframes 收敛：17 → 7

新建 `src/styles/animations.css`（`styles.css` 入口在 app.css 之前 @import），全部 `@keyframes` 的唯一真源。命名规范：**`bb-<动词>[-<方向/变体>]`**；文件头部保留旧名对照注释（照抄 Hana 格式）；可变参数用 CSS 变量传入。

| 新名 | 合并自 | 参数 |
|---|---|---|
| `bb-fade-in` / `bb-fade-out` | `km-alert-fade-in`、`overlay-fade-in`、`process-fade`、`graph-enter`（4→1；out 为新增） | — |
| `bb-rise` | `ui-modal-in`（×2）、`candidate-dialog-enter`、`notice-in`（×2）、`menu-enter`、`ui-fade-in`、`process-enter`（7→1） | `--rise-y`（默认 6px）、`--rise-scale`（默认 1；notice 用 0.99、modal 用 0.985） |
| `bb-slide-x` | `concept-detail-enter` | `--slide-x`（默认 8px） |
| `bb-pulse` | `wiki-ink-thought`、`process-ink`（2→1） | `--pulse-lo` / `--pulse-hi`（照抄 hana-pulse 的参数化思路；`--dur-ink`/`--delay-ink-a/b` 继续供墨点错峰） |
| `bb-spin` | `spin` | — |
| `bb-sheen` | `skeleton-sheen` | — |

裁决说明：`notice-in` 两个版本曲线不同，**以 2291 版为准**（带 scale 0.99 的版本是 M3/M4 有意写的），1116 版删除——但 notice 的动画时长用 `--dur-base`，曲线用 `--spring-pop`（现状已是，2290 行）。`ui-fade-in` 被 `src/ui/animations.tsx` 以类名引用：**类名不动**，只改 `.ui-fade-in` 规则里的 `animation` 值指向 `bb-rise`。`bobodan-process-ink`（chatPrimitives.tsx）同理只改 CSS 侧。

### 7.3 四类场景的标准做法

1. **入场**：`animation: bb-rise var(--dur-base) var(--spring-pop) both`；位移 4–8px，scale ≤0.99，>0.96 的缩放禁用（DESIGN.md §11.7）。
2. **退场**：`animation: bb-fade-out var(--dur-fast) var(--ease-in) both`；不做位移退场（元素消失时位移会拉动布局视线）。
3. **状态反馈**（hover/选中/按压）：transition，不动画；`transform` 配 `--spring-press` + `--dur-fast`，颜色配 `--ease-out` + `--dur-base`。
4. **循环动画**：只允许 `bb-pulse`（状态呼吸）、`bb-spin`（加载）、`bb-sheen`（骨架屏）三个；新增循环动画必须在 animations.css 头部注释里写出"为什么不能用静态状态替代"。

### 7.4 prefers-reduced-motion

在 animations.css 末尾统一收口（替换现在散落的处理）：

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 1ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 1ms !important;
  }
}
```

循环动画（pulse/spin/sheen）在 reduced-motion 下**直接 `animation: none`**，用静态色表达状态。JS 侧继续走 `lib/motion.ts` 实时读取（M4 已落地，不动）。

---

## 8. 组件规格表

可直接照写 CSS。四态列只写与静置态的差分。字号/间距/圆角全部引用 §4 令牌。height 指 `min-height`。

| 组件 | 高度 | padding | 圆角 | 描边 | 字号/字重 | 静置 | hover | active | focus-visible | disabled |
|---|---|---|---|---|---|---|---|---|---|---|
| 主按钮 `.primary-button` | `--h-control-lg`（40） | `0 var(--space-12)`+1px 光学 | `--radius-md` | 无（实色底） | `--fs-caption`/600 | 底 `--accent` 字 white | 底 `--accent-pressed`；`translateY(0)` 不动 | `scale(.97)` `--spring-press`/`--dur-fast` | `outline: 2px solid var(--blue-soft); outline-offset: 2px` | `opacity:.55; cursor:not-allowed`；**禁 pointer-events 之外还要保留 focus 不可达** |
| 次要按钮 `.quiet-button` | 40 | 同上 | `--radius-md` | `--border-strong` | `--fs-caption`/600 | 透明底 `--accent` 字 | 底 `--blue-wash` | 同主按钮 | 同上 | 同上 |
| 图标按钮 `.icon-button` | 38×38 | 0 | `--radius-md` | 透明 | —（图标） | 字 `--muted` | 底 `--blue-wash` 字 `--accent` | `scale(.94)` | 同上 | `opacity:.45` |
| 输入框（`.settings-field input` 等） | `--h-control`（36） | `0 var(--space-12)` | `--radius-md` | `--border-strong` | `--fs-caption`/400（输入内容 `--fs-body` 的场景：composer textarea 15px→`--fs-body`） | 底 `--surface-3` | 不动 | — | `border-color: color-mix(in srgb, var(--accent) 35%, transparent)` + `0 0 0 3px rgb(var(--accent-rgb)/.08)`（现 .composer:focus-within 的令牌化版） | 底 `--surface-0` 字 `--ink-ghost` |
| 下拉 `.library-switcher` | `--h-control-lg` | `0 var(--space-10) 0 var(--space-12)` | `--radius-md` | `--border-strong` | `--fs-caption`/600 | 底 `--paper-soft` | 底 `--paper` | — | 同输入框 | 同输入框 |
| 卡片 `.settings-section` | — | `--space-16` | `--radius-lg` | `--border-subtle` 发丝边 | 标题 `--fs-title`/500 | 底 `--surface-2` | 不动（卡片不做整卡 hover 抬升，§14 配额：每屏抬升 ≤1） | — | — | — |
| 列表行 `.notes-list > article` | `--h-control-xl`（44）起 | `var(--space-10) var(--space-12)` | `--radius-md` | 行间 `--border-subtle` 分隔线 | 标题 `--fs-body`/500，meta `--fs-micro` | 透明 | 底 `rgb(var(--accent-rgb)/.025)`（现值的令牌化） | 底加深一倍 | 行内首个可点元素出环 | — |
| 标签徽章 `.source-chip` | 30 | `var(--space-4) var(--space-8)` | `--radius-sm` | `rgb(var(--accent-rgb)/.13)` | `--fs-micro`/600 | 底 `--blue-wash` 字 `--accent` | 描边加深到 /.2 | — | 出环 | — |
| 弹窗 `.ui-modal-panel` | — | `--space-24` | `--radius-xl` | `--hairline` + `--ring` 外环（契约固定） | 标题 `--fs-heading`/500 | 底 `--surface-3` + `--shadow-dialog` | — | — | 焦点陷阱 + Esc 返回触发元素 | — |
| 菜单 `.library-more-menu > div` / `.slash-palette` | — | `var(--space-4)` | `--radius-md` | `--hairline` + `--ring` | `--fs-caption` | 底 `--surface-3` + `--shadow-float` | 项：底 `--blue-wash` | — | 项出环 | 项 `opacity:.45` |
| 提示条 `.notice` | — | `var(--space-10) var(--space-12)` | `--radius-md` | 无（`--hairline`+`--ring` 外环，契约固定） | `--fs-caption`（12.5→13） | 底 `--surface-3` + `--shadow-float` 字 `--muted` | — | — | — | — |
| 骨架屏 | 与被替换内容同形 | — | 跟随目标组件 | 无 | — | 底 `--surface-0`；`bb-sheen` 微光 ≤`--dur-shimmer`；reduced-motion 下静态 | — | — | — | — |
| 空态 `.notes-empty` 模式 | 内容区 ≥300px 高 | `--space-40` | — | 无框（题库空框事故的反例，UI_AUDIT §2.4） | 标题 `--fs-title`/500 衬线，说明 `--fs-ui` 字 `--muted` | 居中栅格 `gap: var(--space-12)`；最多一个主按钮 | — | — | — | — |

---

## 9. 页面级构图

统一骨架：**所有列表/工具页使用 `.page-scroll > .page-container > .page-heading + 内容`**。`.page-heading` 结构固定为：eyebrow 标签（`--fs-micro`/600/大写/`--clay`）+ h2（`--fs-display`/400/衬线/`--blue`）+ 一行说明（`--fs-ui`/`--muted`/衬线）+ 右侧动作组。eyebrow 目前部分页面用 12px 部分用 13px（`.notes-header` 用 13），统一 `--fs-micro`。

| 页面 | 主内容宽 | 区块间距 | 页头 | 空/载/错三态要求 |
|---|---|---|---|---|
| Chat | `--content-width` 居中（`.conversation`） | 消息间 `--space-24` | 无 page-heading（顶栏承担）；welcome 态居中 | 空=ChatWelcome（已有）；载=流式墨点 `bb-pulse`；错=`.assistant-message.failed` 左边条（已有，保留） |
| Practice / Bank | `--content-width` | 卡片间 `--space-16` | 标准 page-heading | 空=空态模式（§8），题库练习集折叠态用轻分隔行（UI_AUDIT 已修，保留）；载=骨架屏按题型同形 |
| Review | 与页头同宽（**禁止二次居中**，UI_AUDIT 已修，保留 `.review-container { max-width: none }`） | 行间分隔线 | 标准 page-heading | 空="今日无到期"静态文案+主按钮；载=3 行骨架行 |
| Library | 全宽（`.library-container`），树栏 270px | 工具栏/上下文栏/工作区 自上而下 `--space-0` 相接，内部 padding 见 §6.3 | 工具栏承担页头 | 空=`.library-empty-actions`（已有）；载=树栏骨架行；错=`.library-sync-warning` 模式 |
| Reader | `--content-width` | 章节间 `--space-32` | 标签条+视图切换（已有） | 载=正文宽度骨架段落 3 段；错=提示条 |
| Notes | `--content-width` | 列表行间分隔线 | 标准 page-heading（现已接近，eyebrow 13→12 统一） | 空=`.notes-empty`（已是规格来源） |
| Knowledge-map | 全宽画布 | 面板内 `--space-12` | 顶栏承担 | 载=图谱容器内居中 spin；空=引导建资料 |
| Settings | `--content-width`（`.settings-main`） | section 间 `--space-24` | 侧导航+分组标题 | 各 section 内自含；加载用 `.runtime-grid` 骨架 |

判断"8 个页面像一个人做的"的可验收替代指标：① 所有页面页头匹配同一 CSS 选择器结构（grep 可验）；② 所有空态字号组合 ⊆ {`--fs-title`, `--fs-ui`}；③ 所有加载态只用 `bb-sheen`/`bb-spin`/`bb-pulse` 之一。

---

## 10. 迁移方案

每批一个独立提交；每批跑 `npx vitest run` + `npx tsc --noEmit`；视觉批次加暗色截图对比。批次按"契约风险从低到高"排序。

### B1 — 动画收口（第一批，从这里动手）

**起始位置**：新建 `src/styles/animations.css`；删 app.css:2287–2291 的重复块；把 app.css 里 17 个 `@keyframes`（行号 18/83/185/316/377/392/439/1116/1292/1340/1341/1342/1421/1496/2288/2291/2301）全部移入并按 §7.2 合并为 7 个。

- 文件：`styles.css`（+1 行 @import，位置在 tokens.css 之后、app.css 之前）、`app.css`（-17 定义，~30 处 `animation:` 值改名）、新增 `animations.css`（~120 行，含旧名对照注释）。
- 改动量：~50 行。
- 注意：`ui/animations.tsx` 引用类名 `.ui-fade-in`、`chatPrimitives.tsx` 引用 `.bobodan-process-ink`——**类名全部保留**，只改 CSS 内 `animation` 属性指向新 keyframes 名。
- 验收：`grep -c "@keyframes" src/styles/app.css` = 0；`grep -c "@keyframes" src/styles/animations.css` = 7；vitest 全绿（动画名无契约覆盖，安全）；手动看一次通知弹出入场（曲线现为 2291 版，有视觉差，属修复）。
- 风险：notice 入场动画视觉变化（这是修 bug 不是回归）；无暗色风险。

### B2 — 令牌扩容与契约同步

- 文件：`tokens.css`（+§4.1 全部 🆕）、`DESIGN.md` §4.6 表同步、`designTokens.test.ts` OWNED 表更新。`--space-1..7` 以别名形式保留（`--space-1: var(--space-4);` 等），B5 完成后删。
- 改动量：~80 行（含文档）。
- 验收：契约测试全绿（doc==code、OWNED 全入表）；`--h-control-lg` 改值 44→40 后检查 `.primary-button` 等引用处高度符合预期。
- 风险：**契约测试必然先红后绿**（doc 与 code 必须同提交）；`--spring-base/macro` 删除前需最后确认 `grep -rn "spring-base\|spring-macro" src/` 为零（实测 app.css 已无，需再查 tsx）。

### B3 — 字号令牌化（596 处，分 5 子批）

按类名族分批：③a settings 族（144 类）、③b wiki 族（257 类）、③c library+reader+document 族、③d chat/composer/answer 族、③e 长尾。每处按 §5.2 分流表执行。

- 每子批改动：100–150 处声明。
- 验收：每子批后 `grep -oE 'font-size: *[0-9.]+px' app.css | wc -l` 单调下降；**新增棘轮**：以 B3 完成后的裸 px 剩余数为预算起只减不增（预算只挡 app.css 里的字面量，`font-size: var(...)` 不计）。
- 风险：12→13 的升级会改变控件视觉密度，每子批截一次 Chat/Settings 图对比；字号变大可能引起个别单行容器溢出——重点查 `.topbar-title`、`.library-switcher`（select 190px 限宽）。

### B4 — 行高收敛（~98 处 → 4 档）

- 映射：1.1/1.25/1.3/1.35/1.4→`--lh-tight`；1.45/1.5/1.55→`--lh-ui`；1.6/1.65→按语境（prose→`--lh-body`，控件→`--lh-ui`）；1.7 保留换令牌；1.75/1.8/1.85/1.9→`--lh-reading`。
- 验收：`grep -oE 'line-height: *[0-9.]+' app.css | sort -u` 结果 ⊆ {1.3, 1.5, 1.7, 1.85}。
- 风险：prose 行高 1.6→1.7 会改变阅读器/回答的页高，属可接受的排版修正；截 Reader 图对比。

### B5 — 间距令牌化（~370 处裸值）

- 先做 `.library-context-bar` 的 -9px 负 margin 重构（§6.3），再做全量替换：高频裸值 2/3/5/6/7/9/10/14/18px 按就近刻度归并（1px 差以内贴刻度，>1px 差逐个看）。每页面族一个子批。
- 完成后删除 `--space-1..7` 别名，OWNED 表同步。
- 验收：`grep -oE '(padding|margin|gap): *[0-9]+px' app.css | wc -l` ≤ 30（残留仅限光学对齐与 170px 这类带注释的例外）；新增裸间距棘轮。
- 风险：贴刻度会有 ±2px 位移，逐页截图；本批**最容易引起视觉 diff 疲劳**，建议每子批只截该页。

### B6 — 圆角与阴影收口

- 7px→`--radius-md` 等贴刻度（§1.3 第 5 条先动）；预算 60 逐批下调，目标 ≤10（剩余例外逐个写注释）；删 `--parchment`（5 处旧调用点换 `--paper-sunken`）；删 `--spring-micro` 别名（5 处换 `--spring-press`）；`--spring-accent` 无新用途则删。
- 验收：圆角棘轮预算下调实装；`grep parchment src/` = 0。
- 风险：契约里 M3 组件校准断言的是 `var(--radius-md)`，贴刻度不影响；删 `--parchment` 前确认暗色块无引用。

### B7 — 暗色泄漏与字面量清除

- 清单：`.composer`(:788)、`.composer-wrap`(:785)、`.topbar`(:636)、`.user-message`(:686)、`.message-references button:hover` 的裸 rgba、`.notes-list article:hover` 的 `rgba(27,54,93,.025)` 等。全部换 `rgb(var(--accent-rgb)/…)` 或表面令牌。`.practice-summary` 一族错误 fallback（F2）在本批删除。
- 数量：估计 40–60 处，**不确定，需要实测**（`grep -cE 'rgba?\(' app.css` 先量）。
- 验收：暗色主题下 Chat/Composer/Settings 截图与改前对比（改前图即泄漏证据）；`grep -nE 'rgba\(245|rgba\(250|#26364c|#36506c|#b0714e|#2c2a24|#5d7a4a|#faf8f4' app.css` = 0。
- 风险：**这是唯一可能让暗色主题"看起来更对但和之前不一样"的批次**——之前暗色下这些组件本来就是错的，差异即修复。

### B8 — 页面构图统一

- 按 §9 表逐页核对页头结构、空态规格、加载骨架；eyebrow 字号统一；`.notes-header` 等自建页头迁入 `.page-heading` 模式。
- 验收：§12 清单第 9–11 条。
- 风险：页头结构改动触碰 TSX（少量），跑该页测试。

---

## 11. 与既有文档的关系

| 旧结论 | 出处 | 本方案态度 |
|---|---|---|
| "吸收技法、不换色板与字体"（Q2 决策） | archive/frontend/FRONTEND_OPTIMIZATION.md §0 | **继承并再次确认**。本方案三处冲突裁决（保 12px、保圆角、保灰纸）与 Q2 完全一致；Hana 的色板与字档同样没有换入 |
| M1 分层 / M3 表面阶梯·发丝边 / M4 弹簧·IME / W-F6 主题 / M6 验收 | 同上 §6 | **全部继承**，本方案的令牌表在其上只做加法与收敛 |
| store 化与页面拆分路线 | archive/frontend/FRONTEND_OPTIMIZATION_V2.md §1 | **不冲突、不重复**。V2 管工程结构，本方案管样式层；B1–B8 不触碰组件结构 |
| 棘轮预算表（裸 ease 15、裸毫秒 4） | archive/frontend/FRONTEND_OPTIMIZATION.md §1.4 | **推翻（文档过时）**。实测两者均已归零（M4 已完成），§1.4 表与 `designTokens.test.ts` 当前值不符，建议顺手修正该表 |
| 高度阶梯 24/28/32/40/44/68（计划值） | DESIGN.md §6.5 | **推翻（以实装为准）**。tokens.css 实装 28/36/44，组件实测按钮 40、输入 36–42、行 44+。本方案 §4.1 给出裁定值 24/28/36/40/44/68，DESIGN.md 应以此为准更新 |
| `--radius-bubble` 18px（计划） | DESIGN.md §7.1 | **取消**。tokens.css 实装的是 `--radius-panel: 18px`，用户气泡用 `--radius-md`+2px 变体现状良好；文档与实现分叉以实现为准 |
| "同一屏不超过 3 种间距" | DESIGN.md §6.1 | **放宽到 4**（§6.1，实测三栏布局下 3 不可达） |
| 逐页修复结论（练习页、复习页、按钮换行、题库空态） | archive/frontend/UI_AUDIT.md §2 | **全部继承**，相关修复点已写入 §9 对应页面的"保留"项 |
| 字号/行高/间距无棘轮 | （空白） | **补上**：B3/B5 各新增一条棘轮，行高用"取值集合白名单"断言 |

---

## 12. 验收清单

每条都可用命令或一次性人工检查验证。在 `web/frontend/` 下执行。

- [ ] `grep -c "@keyframes" src/styles/app.css` 输出 `0`；`grep -c "@keyframes" src/styles/animations.css` 输出 `7`
- [ ] `grep -oE "font-size: *[0-9.]+px" src/styles/app.css | wc -l` 输出 `0`（`--fs-*` 定义在 tokens.css，不计）
- [ ] `grep -oE "line-height: *[0-9.]+" src/styles/app.css | sort -u` 的输出 ⊆ `{1.3, 1.5, 1.7, 1.85}`
- [ ] `grep -oE "(padding|margin|gap): *[0-9]+px" src/styles/app.css | wc -l` ≤ 30，且每条残留行内有注释说明例外理由
- [ ] `grep -nE "rgba\(245|rgba\(250|#26364c|#36506c|#b0714e|#2c2a24|#5d7a4a|#faf8f4" src/styles/app.css` 无输出
- [ ] `grep -rn "parchment" src/` 无输出；`grep -rn "spring-base\|spring-macro\|spring-micro" src/` 无输出
- [ ] `npx vitest run` 全绿（含新棘轮：裸字号预算、裸间距预算、行高白名单）
- [ ] 圆角棘轮预算 ≤ 10；裸 ease 棘轮 = 0；裸毫秒棘轮 = 0（既有，保持）
- [ ] 页头一致性：`grep -c "page-heading" src/styles/app.css` ≥ 6 且 Practice/Review/Library/Notes/Settings 五页 TSX 均渲染 `.page-heading` 结构（人工逐页核对一次）
- [ ] 暗色主题实拍：Chat（含 composer）、Settings、Library 三页截图，composer 底色 = `--surface-3` 暗色值、顶栏底色 = 暗色纸面（取色器抽 3 像素验证）
- [ ] `prefers-reduced-motion: reduce` 模拟下，页面无循环动画（DevTools Rendering 面板勾选后观察 30 秒）
- [ ] 空态抽查：Practice 空、Library 空、Notes 空三处，说明文字字号 ∈ {14px, 20px}（DevTools computed 面板）
- [ ] 构建：`npm run build` 成功且主 CSS gzip 不超过 M6 基线（33.8KB）+15%

---

## 附：300 字摘要

**最该先改的一处**：B1 动画收口——app.css:2287–2291 的重复 keyframes 是一个正在发生的静默覆盖 bug（`notice-in` 曲线被后定义的分叉版本覆盖），顺手把 17 个 `@keyframes` 收进 `animations.css` 注册表，50 行改动、无契约风险、当天可提交。

**最大的一处风险**：B2 令牌扩容时 tokens.css、DESIGN.md §4.6、测试 OWNED 表三方必须同一提交同步，否则契约测试必红；其次是 B5 间距贴刻度带来的 ±2px 全站位移，需逐页截图消化。

**需要拍板的决策点 4 个**：① 字号下限维持 12px（拒绝 Hana 9.9px 档）；② 圆角保留 6/8/12/16（拒绝方角，60 条预算压到 ≤10）；③ 纸色保留偏灰 #f5f4ed（拒绝 Hana 暖黄纸，饱和度 0.46 超事故阈值 0.35）；④ 间距刻度重编号为 px 同名 12 档（`--space-2…48`，133 处旧引用走别名过渡）。前三个都是"不改"，第四个是"改名字不改数值"。
