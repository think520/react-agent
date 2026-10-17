# 设置区重构方案 v2（对齐 openhanako 设置骨架）

> 2026-10-17。依据：**openhanako 源码实读**（`desktop/src/react/settings/`）+ 我们现有 `components/SettingsDialog.tsx`。
> 目标：把 Bobodan 的**整个设置区**（不只供应商）按它的信息架构重做；视觉仍用 Bobodan 令牌，不换皮肤。

## 0. 先更正一个事实：openhanako 的设置是「弹窗」，不是整页

证据：
- `settings/SettingsApp.tsx` 用 `createPortal` 渲染到 `settings.html` 的 `.titlebar` —— 这是 Electron **独立窗口**那条路；
- 同一套 `SettingsContent` 还有弹窗形态：`Settings.module.css` 的 `.settings-panel-modal`（`width/height:100%`）✓；
- 弹窗骨架：`.settings-header-modal` = 网格（`nav 宽 180px` + 内容列），`.settings-body` = flex（左 `.settings-nav` 180px 带右边框 + 右内容）；
- 导航：`.settings-nav` 顶部是**搜索框**（`.settings-search-shell`），下面 18 个 tab（图标 + i18n 标签，扁平列表）；搜索命中时**列表替换成检索结果**（`.settings-search-results` → 点结果跳 tab）；
- 分节原语：`settings/components/{SettingsPrimitives,SettingsRow,SettingsSection,ExpandableRow,StepSlider,NumberInput}.tsx` + 共享 `settings-components.module.css` —— 每个 tab 由 `SettingsPage` > `SettingsSection` 卡片 > `SettingsRow` 行 堆叠而成；
- 供应商页 = 左列表（分组 + 状态点 + 图标 + 未注册项 dim）+ 右详情（Base URL/API 类型/认证/headers/测试）+ `OtherModelsSection`（后台任务模型、搜索供应商、健康测试）+ `UsageLedgerSection`；添加自定义 = **弹窗内 overlay**（`AddProviderOverlay`），不新开弹窗。

**未确证**：用户截图里导航有分组标题（「我与助手 / 应用 / 能力 / 连接 / 更多」），但当前 checkout（`9a6cabf8`）的 `SettingsNav.tsx` 是扁平 18 项、没有分组实现 ✗ —— 可能来自更新的发行版，**不臆测**，先按「扁平 18 项 + 图标」实现，分组作为可选增强。

## 1. 我们现在的设置区（`SettingsDialog.tsx`，289 行）

已有：弹窗（`.settings-dialog`）+ 左导航 7 节（assistant/user/appearance/ai/memory/skills/status，图标 + aliases）+ 搜索（**只搜分节名** ✗）+ 右内容；`SettingRow/Toggle/Segmented` 三个行内小原语；供应商与记忆管理是**嵌套弹窗**（`ProviderManagerDialog` / `MemoryManagerDialog`）✗。

| 维度 | openhanako | 我们 | 差距 |
|---|---|---|---|
| 外壳 | 弹窗（180px nav + 内容） | 弹窗 + nav | ✅ 基本一致（细节样式可对齐） |
| 搜索 | **设置项级**索引 + 结果跳转 | **分节级**过滤 | ✗ 需要 `settingsSearchIndex`（每行 id/label/aliases/tab/anchor） |
| 原语 | Page/Surface/Stack/Inline/Section/Row/ExpandableRow/StepSlider/NumberInput | 三个小原语 + 手写 class | ✗ 抽 `components/settings/` 设计系统 |
| 分节内容 | 每节 = 卡片（Section）+ 行（Row），一致性高 | 平铺 row，混用手写 html | ✗ 统一为 Section 卡片 |
| 供应商 | 节内 master-detail | 嵌套弹窗 + chips | ✗ 节内主从（见 `SETTINGS` 方案 §3） |
| 记忆 | 节内结构 + overlay 查看器 | 嵌套弹窗 | ✗ 节内分区 |
| 用量 | UsageLedgerSection 台账 | 一个数字 | ✗ 轻量台账 |
| 导航分组 | （见未确证） | 无 | 🟡 可选 |

## 2. 目标信息架构（Bobodan 版，10 节）

| 节 | 内容 | 来源 |
|---|---|---|
| `我与学习` | 称呼/自我介绍/学习目标 | 现有 user |
| `Bobodan` | 助手昵称/教学风格/回答反馈 | 现有 assistant |
| `界面与阅读` | 字体/字号/阅读宽度/纸纹/动效/会话密度 | 现有 appearance（扩互动预览） |
| `AI 与模型` | **供应商主从** + 模型区（context/能力/★/读取）+ 用量台账 + 后台任务模型（只读） | 现有 ai + 新 |
| `检索与 RAG` | 检索模式（hybrid/fts/directory）、嵌入后端、降级提示、术语词汇表 | 新增（后端已有配置） |
| `记忆与数据` | 个人知识概览/候选/旧数据迁移/备份与恢复/数据目录 | 现有 memory（去弹窗） |
| `Skills` | 技能与命令列表（启用/禁用、详情） | 现有 skills（列表化） |
| `安全与隐私` | 密钥存储位置、日志/遥测开关、本地优先说明 | 新增 |
| `状态与关于` | 版本/构建、后端与索引状态、连接自检、更新记录 | 现有 status |
| `实验` | 实验开关（默认空） | 新增（占位） |

导航顺序建议：我与学习 / Bobodan → 界面与阅读 → AI 与模型 → 检索与 RAG → 记忆与数据 → Skills → 安全与隐私 → 状态与关于 → 实验（分组标题可选）。

## 3. 技术方案

```text
web/frontend/src/components/settings/
  SettingsPrimitives.tsx     # Page/Surface/Stack/Inline/Row/Section/ExpandableRow/NumberInput/StepSlider（移植，Bobodan 令牌）
  settings.module.css        # 复刻 settings-components.module.css 的类名语义（类名前缀 settings-）
  settingsSearchIndex.ts     # 每行 id/label/aliases/tab/anchor → 搜索命中渲染 + 跳转 + 高亮
  sections/                  # 每节一个文件（≤300 行），SettingsDialog 只负责外壳与路由
    AssistantSection.tsx / MeSection.tsx / AppearanceSection.tsx
    ModelsSection.tsx        # = 供应商主从 + 模型区 + 用量 + 后台角色
    RagSection.tsx / MemorySection.tsx / SkillsSection.tsx
    SecuritySection.tsx / StatusSection.tsx / ExperimentsSection.tsx
```

- `SettingsDialog.tsx`：外壳（header/nav/body/搜索）+ 按 tab 懒加载 section；不再持有各节状态 ✗。
- 供应商：`settings/providers/`（`ProviderList` 左 / `ProviderDetail` 右 / `ProviderModelList` / `AddProviderOverlay` / `ProviderHeadersField`）—— 沿用 openhanako 的结构，数据来自我们现有 `/api/settings/providers*`。
- 搜索：`settingsSearchIndex` 静态索引（节 + 行），支持中文别名；命中 → 切 tab + `scrollIntoView` + 高亮 1.6s。
- 后端小扩展（可选，S3 一起做）：`ProviderModel` 加 `context? / maxOutput? / vision? / reasoning?`（catalog presets 已带 models ✓ 直接透传）；`/api/settings/providers/summary` 若需要 `supports_oauth` 等字段，先不加 OAuth ✗。

## 4. 分步（每步一个提交，门禁同 M2：tsc/lint/vitest/build + mock e2e）

| 步 | 内容 | 验收 |
|---|---|---|
| **S1** ✅ | 设计系统（primitives + CSS）+ 外壳重排 + 10 节导航 | **已完成 2026-10-17**：`components/settings/SettingsPrimitives.tsx`（Page/Heading/Section/Stack/Row/Field/Toggle/Segmented/Footer）+ `.settings-section` 等结构类；10 节导航（我与学习/Bobodan/界面与阅读/AI 与模型/检索与 RAG/记忆与数据/Skills/安全与隐私/状态与关于/实验）；旧 7 节内容原样挂载（user→me、ai→models 旧 URL 兼容）；检索/RAG、安全与隐私、实验为占位（S4/S5 接入） |
| **S2** ✅ | 迁移 4 个简单节 | **已完成 2026-10-17**：`components/settings/sections/{Assistant,Me,Appearance,Status}Section.tsx`（37/27/33/17 行）；卡片式 `SettingsSection` + `SettingsRow/Field/Segmented/Toggle` + footer 保存按钮；枚举/文案与原版逐字一致（陪练式/今楷/noto-serif/800 宽/舒展）；SettingsDialog 279 行（4 节搬出） |
| **S3** | AI 与模型：供应商主从 + 模型区 + 用量台账 + 后台任务模型（只读）+ 删除 `ProviderManagerDialog` | 与 openhanako 供应商页同构；模型元数据扩展 |
| **S4** | 记忆与数据（去 `MemoryManagerDialog` 弹窗）+ 检索与 RAG 新节 | 弹窗清零；RAG 配置可读可改 |
| **S5** | 安全与隐私 / 实验（占位）+ 设置项级搜索上线 + a11y/键盘 + 清理旧 class | 搜索命中跳转可用；全量门禁绿 |

## 5. 风险

- 设置区被多处入口打开（AppShell 顶部按钮 / 命令面板 / ChatPage 的「打开设置」），外壳替换时**入口 API 不变** ✓（`SettingsDialog` 的 props 保持：settings/activeLibrary/section/onSectionChange/onClose/onSettingsChange）。
- 视觉回归：新原语必须复用现有 tokens（不发新色）；与 `docs/DESIGN.md` 设置骨架章节同步更新。
- 测试：设置相关测试面向行为（开关/保存/迁移），改结构时保持 `getByRole`/文案稳定 ✓。

## 6. 参考

openhanako：`desktop/src/react/settings/`（SettingsApp/SettingsContent/SettingsNav/store/actions/settings-search-index、`components/` 原语、`tabs/ProvidersTab.tsx`、`tabs/providers/*`、`tab*/providers/*`、`Settings.module.css`）。