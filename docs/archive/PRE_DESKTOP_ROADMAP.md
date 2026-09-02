# Bobodan 桌面版之前的路线规划（草案）

> 版本：v0.1（2026-08-28，草稿待确认）
> 依据：openhanako 参考库更新到 v0.450.0（本地 `F:\claude projects\openhanako-reference`，较 7 月 11 日旧版新增 519 个提交）后的三路研究报告
> 前提决策：**P5G.2 Electron 桌面版推迟**。桌面版不是不做，而是等调试/测试基建补齐、Web 端打磨到位之后再启动。本路线覆盖"桌面版之前"的全部工作。

---

## 0. openhanako 三条最重要的启示

1. **它有 763 个 Vitest 测试文件、零 Playwright。** 整个 Electron + 服务端 + 移动 PWA 产品的质量完全不依赖浏览器 e2e：路由级契约测试挂载真实 HTTP app + mock 引擎依赖，流式逻辑抽成纯模块（seq 重放缓冲）单测。Bobodan 的 12 个陈旧 Playwright 用例恰恰是"浏览器测试锁实现"的反面教材。
2. **LLM 只在一个模块缝上 mock。** `lib/pi-sdk/index.js` 被统一 `vi.mock`，其余依赖全部构造函数注入；没有录制的 HTTP cassette，也没有假 provider 服务器。100+ 测试从不碰网络。
3. **桌面不可怕，可怕的是把服务端塞进宿主进程。** openhanako 的 server 是独立 Node sidecar（stock runtime spawn，原生模块零 ABI 地狱），配 `server-info.json` 端口/令牌握手文件 + 启动心跳 + 崩溃诊断（后者由契约测试保护，不许退化）。

---

## R0 质量与调试基建（对应"难调试难测试"，最高优先级）

| # | 事项 | 借鉴源 | 说明 |
|---|---|---|---|
| R0.1 | **测试策略成文化**：写 tests/README，定义 keep/delete 规则（"锁文案的删"、"mock 私有字段的删"），清理前必须 test+typecheck+lint 全绿 | `tests/README.md` | 直接治理 12 个陈旧 Playwright 用例 |
| R0.2 | **e2e 降级为契约测试**：删除大部分浏览器用例，改为 FastAPI TestClient 路由级测试（挂真实 app + FakeScriptedProvider）；仅保留 2-3 条冒烟 e2e（启动→提问→流式回包） | `tests/sessions-route.test.ts` 等 | 覆盖不降、速度 ×50、不再陈旧 |
| R0.3 | **LLM 单缝 mock**：建 `FakeScriptedProvider`（脚本化 delta 序列 + 工具调用 + 错误注入），pytest fixture 统一注入；现有 provider 契约不变 | `vi.mock(pi-sdk)` 模式 | 后续一切 agent 测试的地基 |
| R0.4 | **一键 dev 脚本** `scripts/dev.py`：随机端口 + 写 `server-info.json`（port+token）→ 注入 Vite 代理 + 隔离 dev 数据目录（`~/.bobodan-dev`）+ 双向联动启停 | `scripts/dev-web.js` | 一条命令起全栈，开发与 e2e 共用 |
| R0.5 | **`bobodan diagnose` CLI**：资料库注册表/索引状态/迁移记录/usage 概要/最近日志一屏输出（脱敏），用户报障可粘贴 | `cli/data.ts` 的 `hana data diagnose` | 本地应用排障标配 |
| R0.6 | **持久化治理轻量版**：所有 SQLite/JSON 存储登记清单（owner/路径模式/格式/启动阶段）入库检查；schema 指纹脚本 + tripwire 测试 | `shared/persistence/store-registry.ts`、schema tripwires | Bobodan 已有 6+ 个库，迁移前先立账 |
| R0.7 | **数据 epoch 机制**：破坏性 schema 变更走日志化、检查点化的 epoch 迁移，"旧内核打不开新数据"双向互斥 | `core/data-epoch-*` | AG-1 会话 JSONL 切换的前置保险 |

## R1 前端体验第二批（车厢精装）

| # | 事项 | 借鉴源 | 说明 |
|---|---|---|---|
| R1.1 | **消息操作条 + 编辑重发**：悬停显示 复制/重答/编辑；用户消息内联编辑后重发（保留复习信封上下文） | `MessageFooterActions.tsx`、`UserMessage.tsx`、`SessionNodeActions.tsx` | Chat 最大交互缺口 |
| R1.2 | **会话内查找 Ctrl+F** + **时间线导航条**（按轮次标记、点击跳转、滚动联动） | `ChatFindBar.tsx`、`ChatTimelineNavigator.tsx` | 长对话必备；对应 P5G.3"正文搜索" |
| R1.3 | **Toast 通知系统 + 错误呈现器**：action 按钮、persistent、dedupeKey；错误 → 人话一行 + 可展开详情 + 错误码 | `toast-slice.ts`、`error-presenter.ts` | 现在各页内联 ErrorNotice 各自为政 |
| R1.4 | **@-mention 升级为 inline badge**：引用资料/会话/笔记在输入框内成为 CodeMirror 徽章 chip（Bobodan 已有 @ 菜单雏形） | `MentionMenu.tsx`、`extensions/*-badge.ts` | 引用体验跨代提升 |
| R1.5 | **ContextRing 复用**：今日复习负载 / 上下文窗口占用的环形指示 | `ContextRing.tsx` | 学习场景天然适配 |
| R1.6 | **动效升级**：motion 库三档 spring 预设（paper/paperGentle/paperSnap）+ AnimatedList 布局动画（会话列表重排）；keyframes 统一登记册 | `ui/motion.ts`、`AnimationPrimitives.tsx`、`animations.css` | 与现有三档时长 token 体系衔接 |
| R1.7 | **文档版本 diff 视图**：10 版快照回滚前先看差异（3 栏：版本/版本/行级 diff） | `FileHistoryModal.tsx` + `line-diff.ts` | LB-1.1 已有版本库，补眼睛 |

## R2 学习闭环增强（openhanako 的运行时能力 × Bobodan 的学习场景）

| # | 事项 | 借鉴源 | 说明 |
|---|---|---|---|
| R2.1 | **自主循环子系统 → 复习提醒/学习计划**：sessionId 键控的循环轮次 + 单槽闹钟服务 + 预算/连续失败护栏 + 存活不变量 + 开机恢复 | `lib/loop/*` | **不依赖 Electron 托盘即可做定时复习**，直接替代 P5G.3"复习自动化"，且是 Web 端可测试的 |
| R2.2 | **Usage ledger 归因强化**：start/finish/error 生命周期 + 按 provider 正确的缓存 token 语义 + 来源归因 | `lib/llm/usage-ledger.ts` | Bobodan usage.db 升级 |
| R2.3 | **后台任务统一抽象（deferred results）**：长任务（wiki 批整理/概念提取）持久化 + 投递意图（仅通知 UI vs 唤醒父轮）+ 重试 | `lib/deferred-result-*`、`subagent-run-store.ts` | 统一现有 wiki run 持久化的散装实现 |
| R2.4 | **个人知识周期整理（Memory Dream）**：周期性 原子化→去重→合并 主题化，revision store 可恢复 | `lib/memory/dream/*` | 个人知识候选会越积越多，需要它 |
| R2.5 | **工具目录延迟装配**：schema 出 KV 前缀、BM25 工具搜索、桥接工具保持真实权限语义 | `core/tool-catalog.ts`、`tool-catalog-bridge.ts` | 工具数增长后保护 KV cache |
| R2.6 | **压缩升级**：比例预留 `max(16384, 10% 窗口)` + 轮中压缩缝 + 有损即时模式 | `session-compaction-runtime.ts` | AG-3 session_compactor 迭代 |
| R2.7 | **会话打开恢复三件套**：健康尾扫 + 工具快照修复 + lineage 哈希 | `session-health.ts`、`tool-snapshot-repair.ts` | AG-1 JSONL 切换时一并落地 |

## R3（远期，通往桌面）

- **release digest 生成器**：双语结构化发布说明作为数据（schema 校验），现在就可以给 CHANGELOG 用，将来直接喂给桌面版更新 UI（`scripts/generate-release-digest.mjs`）。
- **signed update trains**：桌面版的 OTA 轨道（签名清单、pointer 通道、暂存激活+回滚）。桌面版启动时的核心件，先研究不实现。
- **sidecar 打包范式**：服务端独立进程 + stock runtime，避免 electron-rebuild —— 桌面版启动时照抄。

## 明确不借鉴

- openhanako 无 Ctrl+K 命令面板、无练习/图谱视图（Bobodan 的学习域视图是独有资产）。
- 其反模式：2366 行的 InputArea / 2016 行的 SessionList 巨石组件、localStorage 存 UI 态、`window.confirm` 与自绘 ConfirmDialog 并存（Bobodan 本轮刚统一掉）、CSS 选择器耦合 JS 行为、假 busy 定时器。

## 排期建议

```text
R0（1-2 周量级）：R0.3 → R0.4 → R0.1/R0.2 → R0.5 → R0.6/R0.7
R1 与 R2 交错推进，每项独立可交付、独立提交
P5G.2 桌面版：待 R0 完成 + R1/R2 主体落地后重新评估
```

## 待确认

1. R0 的 e2e 处置尺度：激进删除（只留 2-3 条冒烟）还是保守（保留但修复）？
2. R2.1 复习提醒的交付面：Web 端横幅/toast 先行，系统级通知留到桌面版？
3. 本文档确认后是否并入 `docs/PROJECT_GUIDE.md` 作为正式阶段规划？
