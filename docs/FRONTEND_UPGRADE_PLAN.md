# Bobodan 前端升级方案（2026-10-20）

> 状态：**已拍板（Motion 受限使用，2026-10-21）；第一批止血已完成，后续待排期**  
> 性质：Bobodan 当前阶段唯一的前端视觉、交互、组件与依赖实施方案  
> 上游依据：[`ROADMAP.md`](ROADMAP.md)、[`DESIGN.md`](DESIGN.md)、[`reviews/2026-10-20-roadmap-review.md`](reviews/2026-10-20-roadmap-review.md)  
> 评估底稿（已归档）：[`archive/frontend/VISUAL_SYSTEM_PLAN.md`](archive/frontend/VISUAL_SYSTEM_PLAN.md)  
> 2026-10-21 已按本文顺序完成第一批止血；组件迁移、对照样板与依赖接入仍须按 §13 逐项开工。

---

## 0. 结论

**保留 Bobodan 的品牌与排版收敛方向，修正旧方案中的技术问题，按页面任务做对照样板，再推广。**

这份方案解决四类问题：

1. **先处理证据明确的回归**：知识地图收起左栏后空白、标签页显示文档 hash、低高度设置动作区被裁切——三项已于 2026-10-21 修复并现场复测；主题硬编码泄漏和字号偏好映射继续按计算样式核验。
2. **把“样式令牌”升级为“设计系统 + 组件行为 + 页面配方”**：不只统一字号、间距和圆角。
3. **建立受控的依赖与源码治理**：一个 UI primitive 体系、一个图标库、一个动画库、一个分栏库、一个 DnD 库、一个状态库。
4. **让 AI one-shot 可维护**：限定可组合组件、禁止裸值和新依赖、强制全状态与真实内容验收。

明确不做：

- 不全产品换皮或照搬 shadcn/ui Nova 默认视觉。
- 不把现有 `app.css` 一次性重写成 Tailwind utility class。
- 不引入第二套图标、动画、拖拽、状态或组件库。
- 不为了减少 grep 数量而改字号、间距和动画。
- 不把知识地图替换成普通 React Flow / DnD 画布。

---

## 1. 体验与代码证据

### 1.1 页面实测（2026-10-20）

运行环境：本地 FastAPI + Vite，IAB 浏览器视口约 `1331 × 764`。

| 页面 | 观察 | 判断 |
|---|---|---|
| Chat | 三栏、暖纸、墨蓝、猫形象成立；输入区层级清楚；暗色未看到明显白条 | 保留骨架，做引用与长回答验收 |
| Library | 文件树、工具栏、阅读区可用；刷新/同步/更多/导入同时出现；标签页出现 `56068ee874e4750e` | 工具动作需分层；标签必须显示可读标题或隐藏到标题加载完成 |
| Reader | 实际 `.reader-prose` 为 `18px / 34.2px`，宽约 `727px`；根变量 `--body-font-size = 16px` | 旧方案“16px 覆盖 17px”的诊断不成立；需重做字号偏好映射 |
| Practice | 开始卡限制在约 `720px`；在宽桌面留下明显右侧空白 | 阅读聚焦宽度不应机械套到所有任务页 |
| Review | 首屏先显示“正在整理复习队列…”再出现列表；完整态清楚 | 加载与内容切换应避免布局跳动 |
| Question Bank | 列表实际占满约 `991px`，单行高度约 `168px` | 管理列表应保留横向空间；不能全站统一窄栏 |
| Knowledge Map | 展开左栏时正常；收起左栏后图谱区空白，但 canvas DOM 与尺寸仍存在 | **真实回归**：不能靠换 DnD/动画库解决，需修复 Sigma resize/重绘链路 |
| Settings | 常规视口下结构完整、暗色可用；`1280 × 600` 下对话框高 `620px`、底部超出视口，保存按钮位于 `y=650–691`，无法完整看到 | **真实回归**：`min-height: 620px` 与 `max-height: 84vh` 冲突，需去掉硬最小值并验证内部滚动与动作区可达 |

### 1.2 第一批修复结果（2026-10-21）

| 问题 | 最小修复 | 验证 |
|---|---|---|
| Knowledge Map 收起左栏空白 | `ResizeObserver` 合并到下一帧，执行 `renderer.resize(true)` 后强制 `refresh()`；不改 Sigma 数据与节点拖拽 | IAB 实拍：收起左栏后图谱节点和标签仍可见 |
| Library hash 标签与失效文档空白 | 标签优先取 `title/source`，数据未就绪显示“正在读取资料…”；资料已不存在时显示“这份资料已不可用”，由用户关闭失效标签，不自动删除其阅读状态 | 组件回归 + IAB 实拍：`56068ee874e4750e` 不再上屏，空态可见 |
| Settings 低高度裁切 | 对话框高度改为 `max-height: min(84vh, 840px)` 与 `min-height: min(620px, calc(100dvh - 40px))`；助手主操作移出滚动内容，固定在对话框底部 | `1280 × 600` 实测对话框底部 `588px`、保存按钮 `y=537–577px`，均在视口内 |

本批门禁：`npm run lint`、`npm run build` 通过；Vitest `50` 个文件 / `325` 条用例全部通过。

### 1.3 代码与依赖事实

| 项目 | 当前状态 |
|---|---|
| React | `19.2.7` |
| React Router | `7.18.1` |
| Lucide | `1.24.0`，已使用 |
| Zustand | `5.0.14`，已有 5 个 store |
| Tailwind | `4.3.2`，仅入口导入，界面主要为手写 CSS |
| shadcn / Radix / CVA / clsx / tailwind-merge | 未安装 |
| Sigma + Graphology | 已用于知识地图，应保留 |
| `app.css` | 约 `235 KB / 2323 行 / 447 条 font-size` |
| 字号 | `12px × 315`、`13px × 108`、`14px × 26`，共 20 余种取值 |
| 行高 | 15 种以上取值 |
| keyframes | 17 个；`ui-modal-in`、`notice-in` 各重复定义 2 次 |
| 圆角 | 221 条声明，仍存在 7px 等刻度外值 |

这些数字只用于定位漂移，不作为用户价值的主验收标准。

---

## 2. 对旧方案的裁决

### 2.1 保留

| 旧方案决定 | 裁决 | 理由 |
|---|---|---|
| 保留暖灰纸、墨蓝、植物绿、橘棕和现有字体 | **保留** | 保住产品辨识度 |
| 不引入约 10px 小字 | **保留** | 中文学习界面的来源、反馈、状态需要认真阅读 |
| 不全面改方角 | **保留** | 无需为另一套审美重做控件 |
| 字号、行高、间距统一命名 | **保留，改方案** | 能减少页面间松散感，但迁移顺序要调整 |
| 修复硬编码颜色造成的主题泄漏 | **优先** | 用户直接感知 |
| 动画集中管理、去重 | **保留** | 防止静默覆盖 |
| 部分 12px 按用途提升到 13–14px | **保留** | 按角色分流，不做全局放大 |

### 2.2 必须修正

| 问题 | 结论 | 修正 |
|---|---|---|
| 间距令牌同名换义 | **原方案不通过** | 当前 `--space-2=8px`、`--space-4=16px`；新方案却改成 `2px/4px`。改用 `--spacing-*` 新命名空间，旧 `--space-*` 保留别名并渐进迁移 |
| RGB 语法混用 | **必须修** | 保留逗号三元组时写 `rgba(var(--accent-rgb), .08)`；不要写 `rgb(var(--accent-rgb) / .08)` |
| 用同一套墨色承担占位符与禁用 | **必须修** | 增加角色令牌：`--text-primary`、`--text-secondary`、`--text-placeholder`、`--text-disabled`、`--action-primary-bg/fg`、`--focus-ring` |
| 阅读器字号诊断 | **推翻旧判断** | 当前实际 18px，根变量 16px。必须先查清 `body_font_size`、阅读宽度与阅读器选择器的映射 |
| SVG / Canvas 绕过 12px 门禁 | **删除** | 换渲染方式不会让文字更大；应允许有理由的例外并做缩放验收 |
| 动画收敛为恰好 7 个 | **不通过** | 先只去重、建注册表、修静默覆盖；语义不同的菜单、弹窗、呼吸动画可保留不同曲线 |
| 全站统一 720px | **不通过** | Reader 正文可以窄，Bank/Library/Review 管理列表必须利用空间 |
| 所有 700 字重归并 600 | **不通过** | 以角色和字体渲染为准，不做机械替换 |
| 所有空态至少 300px | **不通过** | 首次使用、筛选无结果、资料不可用应有不同构图 |
| 所有页面套同一种页头 | **不通过** | 复用信息层级，不强制所有任务页同一结构 |
| 以 grep 数量作为主验收 | **不通过** | 关键是计算样式、真实阅读、键盘操作和内容遮挡 |

---

## 3. 设计系统

### 3.1 品牌锚点

- 暖纸底、墨蓝阅读秩序、植物绿状态、橘棕温度、少量花瓣粉。
- UI 用系统中文黑体；AI 回答和正文用 Noto Serif SC；文章阅读用今楷或宋体。
- 猫形象只承担品牌与状态，不替代控件语义。
- 深色主题是暖棕炭，不是纯黑；浅蓝只做链接和强调，实色按钮单独配前景色。

### 3.2 Token 分层

`tokens.css` 继续是 Bobodan 设计真相源，分为：

| 层 | 示例 | 规则 |
|---|---|---|
| 基础色 | `--paper`, `--ink`, `--blue`, `--sage`, `--clay` | 只允许设计系统定义 |
| 角色色 | `--text-primary`, `--text-secondary`, `--surface-raised`, `--action-primary-bg`, `--focus-ring` | 页面优先使用角色，不直接猜基础色 |
| 排版 | `--type-display`, `--type-heading`, `--type-body`, `--type-ui`, `--type-caption`, `--type-micro` | 形成角色映射，不只给数值起名 |
| 间距 | `--spacing-1: 2px` … `--spacing-12: 48px` | 新命名空间；旧 `--space-*` 只作过渡别名 |
| 行高 | `--leading-tight`, `--leading-ui`, `--leading-body`, `--leading-reading` | 只保留四档 |
| 圆角 | `--radius-sm/md/lg/xl` 加补充角色 | 不追求把所有例外清成零 |
| 动效 | `--ease-*`, `--dur-*`, `--spring-*` | CSS 保留基础；复杂布局与进出场交给 Motion |
| 用户偏好 | `--body-font-size`, `--content-width`, `data-theme`, `data-motion` | 必须允许用户覆盖，不能被固定值覆盖 |

推荐实现：

```css
/* 新刻度 */
--spacing-1: 2px;
--spacing-2: 4px;
--spacing-3: 6px;
--spacing-4: 8px;
--spacing-6: 12px;
--spacing-8: 16px;

/* 旧接口保留原义 */
--space-1: var(--spacing-2);
--space-2: var(--spacing-4);
--space-3: var(--spacing-6);
--space-4: var(--spacing-8);
```

上面的别名只示范相邻刻度；实施时必须先列完整映射表，不能边写边猜。迁移完成后再删除旧别名。

### 3.3 颜色角色与对比度

至少新增以下角色（示意值，实施时按亮暗主题成对校准）：

```css
--text-primary: var(--ink);
--text-secondary: var(--muted);
--text-tertiary: var(--faint);
--text-placeholder: #6b6256;
--text-disabled: #8a8175;
--action-primary-bg: var(--blue);
--action-primary-fg: var(--paper-soft);
--action-primary-hover: var(--blue-soft);
--action-primary-pressed: #142b4b;
--focus-ring: color-mix(in srgb, var(--blue) 55%, transparent);
```

验收：

- 普通文字和占位符按 WCAG 普通文字要求至少 `4.5:1`。
- 大字号按 WCAG 大文本规则验收。
- 用浏览器计算样式和自动对比度测试，不靠颜色名称判断。
- 暗色主题的浅蓝按钮不得默认套白字；实际前景/背景必须成对定义。
- 示例值不是可直接落地的最终色值；暗色主题必须覆盖全部角色，并用实际背景计算对比度。

### 3.4 排版角色

| 角色 | 默认字号 | 用途 |
|---|---|---|
| `display` | 32px | 页面主标题 |
| `heading` | 24px | 弹窗、文章一级标题 |
| `title` | 20px | 区块和卡片标题 |
| `body` | 16px | 聊天、表单、笔记正文 |
| `reading` | 17–18px | 长文阅读，接入用户偏好 |
| `ui` | 14px | 设置说明、对话框正文 |
| `control` | 13px | 按钮、下拉、标签页 |
| `caption` | 13px | 辅助行、列表说明 |
| `micro` | 12px | 等宽元数据、时间戳、计数、角标 |

规则：

- 12px 只用于少量元数据；来源、判错理由、提取警告、复习依据、表单提示优先 13–14px。
- 表达次要信息优先调色阶，再调字重，最后才降字号。
- 正文行高保持 `1.7–1.9`；标题使用紧凑行高。
- 数字统计使用 `font-variant-numeric: tabular-nums`。
- 用户字号偏好必须实际驱动正文计算字号。

### 3.5 间距与布局

按任务分宽度，不设全站唯一内容宽度：

| 场景 | 容器策略 |
|---|---|
| Chat | 对话列限制阅读宽度，输入区不遮内容 |
| Reader | 正文 `640–800px`，由用户偏好决定 |
| Practice | 题目主卡限制阅读宽度，辅助信息可进入侧区 |
| Review | 列表利用可用宽度 |
| Bank / Library | 全宽管理区，工具栏与筛选优先扫描效率 |
| Knowledge Map | 画布全宽，侧栏可调整和收起 |
| Settings | 分组内容有最大宽度，弹窗操作区固定 |

间距规则以“组件内 / 组件间 / 区块间”三层表达，不以同屏最多几种数值作为硬门禁。

---

## 4. 组件系统

### 4.1 采用方式

采用 **shadcn/ui 的源码所有权和组合方式**，不采用其默认品牌外观。

- 初始化时选择 `radix` base，Nova 只作为初始几何和密度参考。
- 生成组件进入 `web/frontend/src/components/ui/`。
- 品牌 token 继续来自 `tokens.css`；shadcn 语义变量通过桥接文件映射到 Bobodan token。
- 不用 `shadcn apply` 覆盖已定制组件；新增组件逐个审查。
- Tailwind 用于新 primitives；现有业务页面继续使用语义 CSS，分批迁移。

不引入 MUI、Ant Design、Chakra 或第二套 UI primitive 体系。

### 4.2 第一批组件（P0）

| 组件 | 必须统一的行为 |
|---|---|
| Button / IconButton | loading、防重复提交、图标位置、禁用原因、键盘行为、最小点击热区 |
| Field / Input / Textarea / Label | label、帮助文字、错误、必填、保存中、保存失败 |
| Dialog / AlertDialog | 初始焦点、焦点陷阱、Escape、焦点归还、未保存内容、关闭与取消语义 |
| Select / DropdownMenu / Popover | 键盘导航、类型提示、空选项、禁用项、窄屏定位 |
| Tabs / SegmentedControl | 选中态、方向键、读屏关系、溢出策略 |
| Switch / Checkbox / RadioGroup | 键盘、标签点击、即时保存失败回滚 |
| Tooltip | 只在补充信息时使用，不承载唯一关键说明 |
| Badge / SourceChip | 来源类型、可点性、长名称截断、不可用状态 |
| Notice / Toast | 成功/警告/失败、自动消失规则、重试、读屏通知 |
| EmptyState | 首次使用、筛选无结果、不可用三种文案与动作 |
| ResizablePanel | 最小/最大宽度、键盘调整、持久化、窄屏降级 |

### 4.3 第二批（按需）

- `Command` / 设置搜索：只有当搜索索引和键盘跳转确有需求时加入 `cmdk`。
- Sortable tabs：只在标签排序成为真实需求时加入 dnd-kit。
- Table / data grid：题库规模证明需要批量选择、列固定和虚拟化后再评估。

### 4.4 不该替换的现有组件

- `ImportDropZone`：已有 `dragCounter`、window 兜底和导入状态，优先保留。
- `GraphCanvas`：Sigma + Graphology 是图谱能力本身，不用 dnd-kit 或 Motion 替代。
- `Modal`：先以其焦点管理和嵌套栈为行为基线迁移到 Radix Dialog，不另建平行弹窗体系。
- 现有 Zustand stores：继续使用，不引入第二套全局状态库。

---

## 5. 页面任务配方

| 页面 | 首要任务 | 构图与交互 |
|---|---|---|
| Chat | 长回答可读、引用可发现、输入区不遮内容 | 中央阅读列；右侧上下文可收起；流式状态轻量；引用展开保留来源与定位 |
| Reader | 长时间阅读、定位引用、保留字号偏好 | 正文窄栏；目录和元数据不争主舞台；字号、宽度、字体由偏好驱动 |
| Practice | 题干 → 选项 → 提交 → 反馈顺序明确 | 主任务卡 + 可折叠辅助区；反馈紧邻答案；提交中防重复 |
| Review | 今天先做什么、为什么、预计多久 | 全宽清单；首屏说明下一步；加载骨架保持尺寸稳定 |
| Library | 扫描、筛选、长标题、来源状态、批量操作 | 文件树 + 内容区保留横向空间；工具动作分层；标签不显示 hash |
| Bank | 扫描效率、筛选、批量操作 | 全宽列表；筛选与批量动作分区；长题干可展开 |
| Settings | 标签、说明、控件、保存状态稳定 | 内部分类导航；内容区滚动；底部动作固定且不超出视口 |
| Knowledge Map | 图谱探索与概念审查 | Sigma 画布全宽；侧栏可收起；修复 resize；节点拖拽保留现有实现 |

### 5.1 三个对照样板

先做三组，不直接全站推广：

1. **Chat**：验证长回答、引用、输入区和右侧上下文。
2. **Practice**：验证主任务、提交、反馈和辅助信息。
3. **Library / Reader**：验证管理密度、文件树、阅读宽度和标签页。

样板使用同一批真实内容：

- 长中文标题；
- 较长回答；
- 多条引用；
- 错误反馈；
- 空结果和不可用资料；
- 普通与窄桌面窗口；
- 浅色、深色；
- 默认字号与最大字号；
- 200% 缩放、键盘和减动效。

---

## 6. 依赖与源码治理

> **路线裁决（2026-10-21）**：Motion 已改为**受限使用**，边界已写入 `ROADMAP.md` §3「动效体系」与 §4。当前仍未安装；接入前必须先有具体页面需求、按需加载方案和减动效回归。

### 6.1 批准的依赖矩阵

| 职责 | 选择 | 当前版本依据 | 使用边界 |
|---|---|---|---|
| UI primitives | shadcn/ui + Radix | shadcn CLI `4.22.1`；Radix 聚合包 `1.8.1` | 源码入仓，Nova 只作参考 |
| 样式工具 | Tailwind CSS | 已装 `4.3.2` | 新 primitives 使用，不强制重写旧 CSS |
| 图标 | Lucide | 已装 `1.24.0` | 唯一图标库 |
| 动画 | Motion for React | `motion@14.4.0`；从 `motion/react` 导入 | 复杂进出场、布局和拖拽反馈 |
| 分栏 | `react-resizable-panels` | `4.14.7` | Library、Map、Chat 侧栏 |
| 拖拽 | `@dnd-kit/core` + `sortable` + `utilities` | `6.3.1 / 10.0.0 / 3.2.2` | 标签排序、简单可排序列表 |
| 状态 | Zustand | 已装 `5.0.14` | 继续使用，不引入 Redux/Jotai |
| 类名工具 | `clsx` + `tailwind-merge` + CVA | `2.1.1 / 3.7.0 / 0.7.1` | shadcn primitives 组合 |

注意：

- 用户写的 `react-resizing-panels` 在 npm 不存在；正确包名是 **`react-resizable-panels`**。
- Motion 当前包名是 `motion`，不是 `framer-motion`。
- 所有版本在实施时重新解析并固定到 lockfile；表中版本只作本轮核对依据。

### 6.2 单一职责规则

- 一个 UI primitive 体系：shadcn + Radix。
- 一个图标库：Lucide。
- 一个动画库：Motion。
- 一个分栏库：`react-resizable-panels`。
- 一个 DnD 库：dnd-kit。
- 一个全局状态库：Zustand。

新增同类依赖必须先证明现有选择无法满足，并记录替代与迁移成本。

### 6.3 源码边界

```text
web/frontend/src/
  components/ui/        # shadcn 生成并归项目所有的 primitives
  components/           # 现有业务组件，逐步组合 ui/
  styles/tokens.css     # Bobodan token 真相源
  styles/shadcn.css     # Bobodan token -> shadcn CSS 变量桥
  styles/app.css        # 现有语义样式，逐页收缩
```

不得让 shadcn 默认变量形成第二套设计系统。`THIRD_PARTY_NOTICES.md` 与 lockfile 必须同步更新。

### 6.4 Motion 使用边界

- 用 `LazyMotion` + `m` 降低首屏体积。
- 只用于弹窗/抽屉进出场、消息出现、布局变化和有意义的拖拽反馈。
- 不把所有 hover、点击和列表项都动画化。
- 同时尊重系统 `prefers-reduced-motion` 和应用内 `data-motion="reduced"`。
- CSS spring token 保留为基础；不要让 Motion 与 CSS 对同一属性互相覆盖。

### 6.5 分栏与拖拽边界

`react-resizable-panels`：

- 先用于 Library 文件树、Knowledge Map 侧栏和 Chat 右侧上下文。
- 必须验证最小/最大宽度、键盘调整、宽度持久化、窄屏降级。
- Knowledge Map 收起后必须触发 Sigma `resize()` 并重绘；分栏库不能替代这条修复。

dnd-kit：

- 只用于标签排序和简单列表排序。
- 不替换文件上传拖放。
- 不接管 Sigma 节点拖拽。
- 文件树大范围拖拽必须先有权限、归档和撤销设计。

### 6.6 Zustand 边界

- 按领域保留 `chatStore`、`readerTabsStore`、`noticeStore`、`uiStore`、`handoffStore`。
- actions 放在模块级，避免组件闭包依赖。
- 用 selectors 订阅最小状态，禁止整页订阅。
- persist 增加版本号和迁移函数。
- 不把服务端缓存硬塞进 UI store；若未来出现真实缓存失效和竞态问题，再单独评估 TanStack Query。

---

## 7. One-shot 生成约束

AI one-shot 结果视为待审查 PR，不直接并入主分支。

必须：

- 只组合批准的 primitives，不新建平行按钮、弹窗、下拉和字段体系。
- 禁止裸颜色、裸字号、裸间距和裸动画时长；例外必须有注释与验收理由。
- 禁止新增图标、动画、拖拽、状态或 UI 库。
- 覆盖 loading、empty、error、disabled、focus-visible、保存中和保存失败。
- 使用真实中文长标题、长回答、多引用和错误内容验证。
- 通过 tsc、lint、vitest、production build 和 Playwright。
- 给出改动前后的计算样式与截图，不只给 grep 数字。

---

## 8. 实施顺序

| 阶段 | 工作 | 门禁 |
|---|---|---|
| 0 基准 | 固定三个样板的真实内容与视口；记录计算字号、宽度、对比度和键盘路径 | 基准可重复，有截图与 DOM 测量 |
| 1 止血 | **已完成（2026-10-21）**：知识地图收起空白、标签 hash、低高度设置动作区裁切；主题硬编码和字号偏好映射继续核验 | 明确回归有测试与实拍；lint / build / 全量前端测试通过 |
| 2 基础设施 | token 新命名空间、颜色角色、shadcn 桥接、Button/Field/Dialog 等首批 primitives | token 契约、tsc、lint、单测 |
| 3 三组样板 | Chat、Practice、Library/Reader 对照改造 | 真实内容、浅暗色、窄屏、200% 缩放 |
| 4 页面迁移 | Review、Bank、Settings、Knowledge Map、Notes | 每页独立提交与回归 |
| 5 交互增强 | Motion、resizable panels、dnd-kit 只接入已验证需求 | 键盘、减动效、resize 回归 |
| 6 清理 | 旧别名、裸值、重复 keyframes、未使用 CSS 和依赖 | 全量门禁 + 视觉抽查 |

不要从“17 个动画合成 7 个”或“批量替换 596 处字号”开始。

---

## 9. 验收标准

### 9.1 视觉与可访问性

- 普通文字和占位符对比度达到 `4.5:1`；大文本按 WCAG 规则。
- 浅色、深色、高对比度均可读。
- 12px 只出现在核准的元数据角色；来源、反馈和操作文字优先 13–14px。
- 键盘可完成主要任务；Dialog 初始焦点、陷阱和焦点归还正确。
- `prefers-reduced-motion` 与应用内减动效同时生效。

### 9.2 布局与交互

- `1280 / 1440 / 1920` 桌面、窄桌面和 200% 缩放不破版。
- Reader 无双滚动条，正文不被目录、工具栏或输入区遮挡。
- Practice 的题干、选项、提交和反馈顺序清楚。
- Review 和 Bank 保留横向扫描效率。
- Library 标签不显示文档 hash；长标题可读。
- Settings 底部动作在低高度视口可达。
- Knowledge Map 收起或调整侧栏后不空白。

### 9.3 工程门禁

- 现有测试基线在同一提交和环境重新运行；历史数字不得当作当前结果。
- 新增组件具备状态测试；关键布局有 Playwright 回归。
- `npm run build`、tsc、lint、vitest 全绿。
- 主 CSS 体积不得因迁移显著反弹。
- 依赖变更同步 lockfile 与第三方声明。

---

## 10. 里程碑与交付物

| 里程碑 | 交付物 |
|---|---|
| M0 基准 | 三组样板基准页、计算样式记录、已知回归清单 |
| M1 止血 | **已完成（2026-10-21）**：知识地图 resize、标签标题与失效态、低高度设置动作区；主题硬编码与字号偏好映射待继续核验 |
| M2 设计基础 | 新 token 命名空间、颜色角色、shadcn 桥、首批 primitives |
| M3 样板 | Chat、Practice、Library/Reader 三组对照结果与评审结论 |
| M4 推广 | Review、Bank、Settings、Map、Notes 分页迁移 |
| M5 收尾 | 旧别名与重复 CSS 清理、依赖审计、最终验收报告 |

---

## 11. 风险与回滚

| 风险 | 控制 |
|---|---|
| shadcn 默认视觉覆盖品牌 | 只生成源码；主题桥接只读 Bobodan token；样板先评审 |
| Tailwind 与旧 CSS 双体系长期并存 | 新 primitives 用 Tailwind，旧页面按页迁移；设清理阶段 |
| 方案与既有路线冲突 | Motion 目前写在 `ROADMAP.md` 的「明确不做」；先完成路线级裁决，再安装和接入 |
| 分栏改造导致 Sigma 空白 | 先写 resize 回归；收起/展开、键盘调整、窗口缩放均测 |
| Motion 与 CSS 动画重复 | 同一属性只允许一个控制源；复杂动画归 Motion，基础过渡保留 CSS |
| 批量字号替换造成密度回归 | 先做角色映射和三页样板；禁止机械全局替换 |
| 依赖数量膨胀 | 单一职责矩阵；新增依赖必须给出替代方案与删除计划 |

回滚以页面批次为单位：每批独立提交，保留旧路径直到该页验收通过。

---

## 12. 与既有文档的关系

- `ROADMAP.md` 仍是唯一排期入口。
- `DESIGN.md` 仍是视觉与交互硬约束；本方案确定后，需要把稳定规则同步进去。
- `archive/frontend/VISUAL_SYSTEM_PLAN.md` 是已归档的评估底稿（2026-10-28 移入 `archive/`），不再单独指导实施。
- `archive/frontend/` 中的 M1–M6 文档只作历史依据。

---

## 13. 开工前检查

- [ ] 确认本方案进入 `ROADMAP.md` 的哪个批次。
- [x] Motion 已裁决为受限使用，并同步 `ROADMAP.md` §3/§4；安装仍需具体页面需求与按需加载方案。
- [ ] 建立 Chat、Practice、Library/Reader 三组真实内容基准。
- [ ] 记录当前字号、宽度、对比度、键盘和 resize 行为。
- [ ] 确认 shadcn `components.json`、Tailwind 桥接和 `components/ui/` 边界。
- [x] 已修复知识地图空白、标签 hash 和低高度设置动作区裁切三个明确回归。
- [ ] 主题硬编码泄漏和字号偏好映射完成证据核验。
- [ ] 再引入 Motion、resizable panels、dnd-kit，逐项证明必要性。

---

## 附：一句话摘要

**Bobodan 已有成立的设计语言，当前缺的不是换皮，而是把品牌 token、无障碍组件行为、页面任务构图和受控依赖组合成一套可验收、可回滚、AI 也难以生成漂移的实现体系。**
