# 前端优化借鉴方案 v2（2026-10-17）

> 依据：**两个参考仓库**（各自的强项）+ 当前分支 M2 的**两档验收实测结论**。
> 参考一 **openhanako**：`F:\claude projects\openhanako-reference`（已更新到 `9a6cabf8`，v0.450.0+）—— 借**架构与工程范式**。
> 参考二 **open-claude-ui**：`F:\claude projects\open-claude-ui`（pin `ddf3aea`）—— 借**视觉与交互技法**（v1 方案已吸收）。
> 本文重点回答一个具体问题：**ChatPage / LibraryPage 为什么拆不动，以及怎么拆**。

---

## 0. 两个参考仓库的分工（先看清各自强项）

| | openhanako | open-claude-ui |
|---|---|---|
| 体量 | 前端 **826 文件 / 146,282 行** | `src/` 只有入口，价值在 **docs 逆向手册**（234KB CDS + 42KB 令牌 + 17KB 动效） |
| 强项 | **工程范式**：zustand slices + actions（~50 个 store 文件）、按区域拆聊天组件（`components/chat/` 40+ 文件）、CSS Modules、`data-theme` 主题系统、暖纸主题 | **视觉技法**：令牌矩阵、发丝边/表面阶梯、4 套弹簧常数、组件四态 |
| 适合借 | **结构、状态管理、主题机制** | **数值、动效、组件规格** |
| 不借 | 超大单文件（它自己也有 **2,209 行的 `InputArea.tsx`** ✗）、超大的 CSS module（`Settings.module.css` 6,975 行 ✗）、大量 `any`（store 里显式 disable ✗） | 陶土色板 / 品牌语汇 ✗ |

**重要观察**：openhanako 并不靠「把文件切小」解决复杂度 ✗ —— 它的组件照样上千行 ✓；它真正做对的是**把状态与逻辑搬出组件**（见 §1）✓。这正好对上我们 M2 卡住的地方 ✓。

---

## 1. ChatPage / LibraryPage 为什么拆不动（实测复盘）

| 尝试 | 结果 | 根因 |
|---|---|---|
| 把处理器抽成 `useChatActions(deps)` | 失败 ✗ | **依赖面 34 个**（refs / setter / 流式回调 / 导航 / 设置）；deps 声明 + 传参 ≈ 70 行 > 搬出收益 |
| container / hook / view 三层 | 失败 ✗ | 状态区的 `useEffect` 反过来调用处理器 → **双向依赖**；按括号切 effect 块时嵌套 `setState(...)` 使边界错位 |

**结论**：只要**状态与处理器还在组件闭包里**，任何拆分都要付「依赖清单」的过路费 ✗ —— 这笔费用与搬出的收益基本相等 ✓，所以怎么拆都不划算 ✗。

## 1.1 openhanako 的解法：**store 化 + actions 无闭包**

它的 store 目录是成对的：

- `session-slice.ts` / `session-actions.ts`、`chat-slice.ts` / `chat-slice` 类、`session-selectors.ts`、`create-keyed-slice.ts`、`stores/index.ts`（用 `create(...)` 组合全部 slice）；
- 关键约定写在 `session-actions.ts` 的头部注释里：**「所有函数直接操作 Zustand store，不依赖 ctx 注入，不持有闭包状态」** ✓✓。

也就是说：**处理器不再是组件里的闭包 ✗，而是模块级函数，直接用 `useStore.getState()/setState()`** ✓ —— 于是：

1. **没有依赖清单** ✓（不需要 deps 参数 ✗）；
2. **没有双向依赖** ✓（谁都能调 actions ✓）；
3. **组件只负责「读状态 + 渲染」** ✓；
4. actions 天然可单测 ✓（它自己的测试就有 `session-actions.test.ts` 2,317 行 ✓）。

### 1.2 迁移到 Bobodan 的具体方案（替代原来的 hook 拆分）

项目已经有 zustand（`zustand ^5.0.14` ✓）与 `src/stores/` ✓，不需要新依赖 ✓。

**目标结构**：

```text
web/frontend/src/stores/
  chatSlice.ts        # 状态：messages/status/sending/webSelections/…（≤300 行）
  chatActions.ts      # 处理器：send/sendResume/wiki/web/practice/interaction（≤600，超了再按域拆）
  chatSelectors.ts    # 派生值：planningRunIds/latestArtifact/artifactSurface 的纯输入
  chatStore.ts        # create() 组合 slice + actions 绑定
web/frontend/src/pages/chat/
  ChatPage.tsx        # 只做 layout：composer + transcript + 面板（目标 ≤400）
  ChatComposer.tsx    # 输入区（picker/mention/IME）
  ChatTranscript.tsx  # 消息流 + artifact 分发
  ChatWelcome.tsx     # 空态
```

**迁移顺序（每步一个本地提交、每步跑 `ChatPage.test.tsx` + 全量 vitest）**：

| 步 | 动作 | 验收 |
|---|---|---|
| 1 | 建 `chatSlice.ts`：把 ChatPage 的 `useState/useRef` 字段**原样**搬进 slice（先只搬字段，不改行为） | 组件仍能编译，测试全绿 |
| 2 | 逐族搬处理器到 `chatActions.ts`：先 **web 族**（4 个）→ **wiki 族**（7 个）→ **交互族**（4 个）→ **练习/设置族**（7 个）→ 最后 **send/sendResume**（流式接线） | 每族搬完跑该页测试 + tsc |
| 3 | effect 迁到「订阅动作」：把原来依赖 messages/artifacts 的 effect 改成 `subscribe` 或在 actions 内触发 | 行为不变（F1 seq 幂等、F7 滚动契约逐项核对） |
| 4 | 组件改 selector：`useChatStore((s) => s.messages)` 等 | ChatPage ≤400 行 |
| 5 | 删残留状态与未用 import | lint 0 |

**风险与缓解**：① 迁移期间**双源状态** ✗ → 一次只迁一族，旧字段先保留引用 ✓；② zustand v5 语义（选择器必须稳定 ✓）→ 用 selector 函数而非对象 ✓；③ 行为回归 → 296 条前端测试 + 15 mock e2e + 7 live 是硬护栏 ✓；④ **不要一次搬完** ✓（这是前两次失败的直接教训 ✓）。

**预期结果**：ChatPage **1,031 → ≤400** ✓；`chatSlice` ≤300 ✓；`chatActions` ≤600（可分 2 个文件）✓；LibraryPage 同法（`librarySlice/libraryActions` ✓）**1,461 → ≤400** ✓。

---

## 2. 其他可借鉴项（openhanako → Bobodan）

| 项 | openhanako 做法 | Bobodan 怎么借 |
|---|---|---|
| **actions 无闭包** | 模块函数直接操作 store | ChatPage/LibraryPage 的解法核心 ✓（§1） |
| **selectors 模块** | `session-selectors.ts` | 新增 `chatSelectors.ts` / `librarySelectors.ts`，派生值不再散落组件 |
| **按区域拆聊天组件** | `components/chat/`：Transcript / MessageSurface / AssistantMessage / UserMessage / MarkdownContent / MessageActions / ToolGroup / Cards ✓ | 我们已有 `components/artifacts/*` ✓；补齐 `ChatTranscript` / `ChatMessage` / `ChatActions` 三层 ✓ |
| **CSS Modules per feature** | 每组件配 `*.module.css` | 与我们已完成的 CSS 分层结合：全局 tokens ✓ + 每页/每组件 css 文件 ✓（不引入 CSS Modules 语法，保持现有类名 ✓） |
| **`data-theme` 主题系统** | `[data-theme="warm-paper"]:root` 多主题 | 把我们现有的 `data-reading-font` / `data-paper-texture` 升级为 `data-theme` 主题契约（暖纸默认 / 暗色 / 高对比），为打包后的系统主题适配留口 ✓ |
| **暖纸主题对照** | `--bg: #F8F4ED` + base64 纸纹 | 我们 `--paper: #f5f4ed` ✓ 同一调性；可对照校准纸纹实现（我们按需 ✓ 不强求 base64 ✓） |
| **store 级单测** | `__tests__/stores/session-actions.test.ts` 2,317 行 | 迁移后给 `chatActions` 加**纯函数单测** ✓（比测组件便宜得多 ✓） |

**不借**：超大单文件（2,209 行 ✗）、超大 CSS module（6,975 行 ✗）、store 里显式 `any` ✗。

---

## 3. 结合 open-claude-ui 的视觉升级（v1 → v2 差异）

v1 已吸收的技法**不变** ✓：令牌矩阵 / 表面阶梯 / 发丝边 / 圆角高度矩阵 / 弹簧常数 / 组件四态 ✓（`docs/DESIGN.md` v2 已写好 ✓）。

v2 **新增两项**：

- **W-F6 主题系统**（借 openhanako）：`data-theme` 契约 + 主题令牌表 + 契约测试（每个主题必须覆盖全部语义 token ✓）；
- **W-F7 聊天区域化组件**（借 openhanako 的 `components/chat/` 结构）：Transcript / Message / Actions / Cards 四层，配合 §1 的 store 化 ✓。

---

## 4. 修订后的工作流与状态

| 编号 | 内容 | 状态 |
|---|---|---|
| W-F1 | CSS 分层 + 字体延迟加载 | ✅ 已完成（主 CSS 197.77 → 31.64 kB gz） |
| W-F2 | 页面拆分 | ✅ **完成（2026-10-17）**：AppShell 790→599、api.ts 1,407→19、ChatPage 1,031→**579**、LibraryPage 1,526→**544**、SettingsDialog 289 —— 全部 ≤600 ✓ |
| W-F3 | 视觉语言融合（令牌/发丝边/遮罩） | 🟡 计划中 |
| W-F4 | 动效与 IME | 🟡 计划中 |
| W-F5 | 字体与包体 | 🟡 计划中 |
| W-F6 | 主题系统（`data-theme`） | ✅ **完成（2026-10-17）**：`[data-theme="dark"]` + `[data-contrast="high"]` 只翻转颜色变量（不重定义字体/圆角/动效，契约测试保证 ✓）；后端 `appearance.theme/contrast` 默认值与枚举校验 ✓；设置「界面与阅读」可切换并持久化 ✓；跟随系统时实时响应 `prefers-color-scheme` ✓；暗色/高对比实拍验证 ✓ |
| W-F7 | 聊天区域化组件 | 🆕 借 openhanako |

**与 M2 两档验收的关系**：两档验收的结论不变 ✓；本文 §1 就是「已知债」的**解法** ✓ —— 不是回头再做一遍 ✓，而是换一条**能一次做对**的路线 ✓。

---

## 5. 参考与出处

- openhanako（`liliMozi/openhanako`，本地方向已更新至 `9a6cabf8`）：`desktop/src/react/stores/index.ts`（slice 组合）、`desktop/src/react/stores/session-actions.ts` 头部注释（actions 无闭包原则）、`desktop/src/react/components/chat/`（区域化组件）、`desktop/src/themes/warm-paper.css`（主题令牌）。
- open-claude-ui（`Caho1/open-claude-ui`，pin `ddf3aea`）：`docs/v1/01-设计哲学与设计令牌体系.md`、`04-动效物理学…`、`docs/v2/05-生产级参考实现代码.md`。
- 项目现状证据：`docs/FRONTEND_OPTIMIZATION.md` §1/§6.1（实测体量与两档验收）、`CHANGELOG.md` 2026-10-17 各条（两次失败复盘）。