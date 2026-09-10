# Bobodan 整机优化计划书

> 版本：v1.1（2026-08-11）
> v1.1：经 grill-me 确认，补齐 FE-4 页面联动范围与图谱动效配方（维持 sigma.js）、LB-1 版本管理 / 学习事件边界 / Obsidian 冲突策略。
> 性质：与 P5G 并行的工作流，不打乱现有 P5 系列计划
> 借鉴来源：Pi（earendil-works/pi，agent 运行时图纸）、OpenHanako（liliMozi/openhanako，外围工程 + 前端丝滑）
> 定位说明：Bobodan 是"自己造的发动机"，本文按 Pi 的图纸优化发动机结构；按 OpenHanako 的经验装修车厢（前端体验）。不推倒重来，`core/agent_loop.py` 是资产不是负债。

---

## 执行状态（2026-08-13 完成主体，分支 feat/optimization-plan，已推送 origin）

| 阶段 | 状态 | 落地说明 |
|---|---|---|
| AG-0 外围地基 | ✅ 完成 | 事件总线 / 事件四层收敛 / SSE 流身份+重放 / 流消毒守卫 / 适配层门面 |
| FE-1 前端地基 | ✅ 完成（基础） | selector 归一化 / 动画原语 / 块级 ErrorBoundary / CSS Token / @ 别名；上滑分页待 AG-1 |
| LB-1.1 用户编辑 | ✅ 完成 | Markdown 优先 + 检查点 + 最近 10 版 + 哈希冲突三选项 + 编辑器 UI |
| AG-2 循环增强 | ✅ 完成 | 两层钩子 / 证据门禁与白名单沉淀为 before_tool 门禁 / 只读并行 / 去重 |
| FE-2 流式体验 | ✅ 完成（核心） | StreamBuffer 30fps / 自适应节流 / 贴底滚动 / seq 去重；Markdown 顶层 reconcile 待补 |
| AG-3 记忆与压缩 | ✅ 完成 | before_turn 注入生命周期 / KV cache 布局 / checkpoint 压缩 |
| FE-3 过程披露 | ✅ 完成（过程折叠） | 过程折叠（阈值 3）；CardParser 实时卡片待补 |
| LB-1.2 AI 协作编辑 | ✅ 完成 | 提案 → 确认 → 应用 → 撤销（复用 Wiki 检查点） |
| AG-1 会话革命 | ⏸ 条件完成 | P5G 未验收 → 仅设计 + JSONL 迁移路径 + 测试，未切换线上默认 .json 格式 |
| FE-4 页面联动与图谱动效 | ✅ 完成（主体） | 页面联动（FadeIn / 上下文跳转 / 学习范围共享）+ 配方 1/2/3/6 + spotlight + 力参数 + 降级 |

### 遗留事项
- FE-1 上滑分页：依赖 AG-1 会话格式，且默认 max_messages=20 使价值有限。
- FE-2 Markdown 顶层 reconcile（流式阅读选中文字不被打断）、TailFade、完整重连客户端。
- FE-3 CardParser 实时卡片：现有 SSE chat_artifact 已近实时发卡片，延迟感已缓解。
- FE-4 配方 4（活跃节点呼吸）/ 5（新节点脉冲）+ forceAtlas2 布局异步化（worker）。
- Playwright e2e：关键流程（断线重连 / 编辑回滚 / AI 提案撤销）当前以后端单元与端点测试为等价测试。

验证：Python 1343 passed（基线 1233 → +110，零回归）、Vitest 46 passed、前端 lint 与生产构建通过；SSE 对外事件名不变、证据门禁行为不变。

---

## 0. 背景与原则

### 0.0 参考项目优先级（2026-08-11 用户指定）

Bobodan 遇到难题、问题、优化需求时，**首要翻阅这两个项目**查找解决方案：

1. **tw93 旗下项目**（https://github.com/tw93）：Pake（网页打包桌面应用）、MiaoYan（分栏编辑预览 Markdown 笔记）等，本地优先、轻量、克制审美。
2. **liliMozi/openhanako**（https://github.com/liliMozi/openhanako）：本地源码在 `F:\claude projects\openhanako-reference`（注意是上个版本）。

这两个也是用户最喜欢的项目和审美。找不到答案再扩散到其他相关开源项目。

### 0.1 为什么是"优化"而不是"重构"

- Bobodan 的 AgentLoop 是自研 ReAct 循环 + 证据门禁，已被 1000+ 测试保护。循环本身是资产。
- OpenHanako 自己也没写循环（委托 Pi SDK），它的精华在围绕循环的外围工程：事件总线、流式解析、能力冻结、记忆编译。
- Pi 的精华在边界切割：持久化、上下文投影、事件流、钩子、provider 各自独立可替换。
- 因此：**循环不动，补基础设施；事件流升级为一等公民；能力按钩子化沉淀；会话改为可审计流水账。**

### 0.2 借鉴边界（明确不照搬）

| 来源 | 借鉴 | 不借鉴 |
|---|---|---|
| Pi | 会话事件源、上下文分离、事件四层收敛、可拦截钩子、只读工具并行、压缩 checkpoint、KV cache 意识 | 分叉树（fork/clone）、TUI、扩展市场、供应链硬化全套 |
| OpenHanako | 事件总线过滤路由、流式标签解析、per-session 能力冻结、记忆编译传送带、30fps 流缓冲、DOM reconcile、贴底滚动、乐观消息三态、过程折叠 | 思维链展示、mood 人格协议、插件生态、WS 传输层迁移 |

### 0.3 与 P5G 的关系

- **AG-0 / FE-1 / LB-1（用户编辑部分）可与 P5G 并行**：全部是新增文件或纯前端改动，对 P5G 验收零冲击。
- **AG-1（会话格式变更）等 P5G 验收后启动**：会话格式影响所有端，桌面端稳定后再动。
- 每阶段沿用 PROJECT_GUIDE 纪律：**验收条件成立才进下一阶段**。

---

## 1. 差距分析摘要

Bobodan 现状 vs 两个参考项目的主要差距（按影响排序）：

| # | 差距 | 参考做法 | 解决阶段 |
|---|---|---|---|
| 1 | 会话 JSON 整份覆盖写，无历史/恢复/审计 | append-only JSONL 事件源 + id 序列 | AG-1 |
| 2 | 事件流是循环顺手 yield 的副产品，命名按 UI 需求 | 四层收敛：agent → turn → message(delta) → tool | AG-0 |
| 3 | 证据门禁/白名单硬编码在循环参数里 | 可拦截钩子：返回值表达 `{block, reason}` 语义 | AG-2 |
| 4 | 记忆注入无生命周期纪律 | 注入挂 before_turn、token 预算、与证据门禁解耦 | AG-3 |
| 5 | 工具串行执行 | 只读工具并行 + 结果按模型原始顺序恢复 | AG-2 |
| 6 | 无思考块/卡片流式概念 | CardParser 流式标签解析（不含思维链） | AG-0 / FE-3 |
| 7 | web 直连 session，无总线 | 带过滤事件总线 | AG-0 |
| 8 | 无 per-session 能力冻结 | prompt/tool 快照 + restore repair | AG-1 |
| 9 | 无流消毒 | stream-guard：畸形 toolcall 恢复为文本 | AG-0 |
| 10 | 长会话无压缩 | checkpoint 结构化压缩 + 保留尾部 | AG-3 |

---

## 2. A 系列：发动机（Agent 运行时，按 Pi 图纸）

### AG-0 外围地基（低风险，纯增量，立即开工）

目标：事件流与运行时解耦，为后续一切铺路。全部为新增文件，不改现有循环。

**AG-0.1 事件总线（core/event_bus.py）**
- 带过滤的事件总线：`subscribe(callback, session_id=None, event_types=None)`，session 索引 + types Set 索引。
- listener 抛错不中断分发（try/catch 包每个 listener）。
- 参考：openhanako `hub/event-bus.ts`。
- 用途：多会话并发隔离；web 后端、trace、usage 记账、测试断言统一走总线。

**AG-0.2 事件流收敛（core/agent_events.py）**
- 事件类型四层收敛：`agent_start → turn_start → message_start → message_delta → message_end → tool_start → tool_end → turn_end → agent_end → agent_settled`。
- `message_delta` 带增量语义（content delta + 顺序号），不带累积快照。
- `agent_settled` 解决"run 到底完没完"歧义（区分单次 run、重试、排队）。
- 现有事件（assistant_delta / tool_start / tool_end / assistant_done）映射到新命名，**web 适配层（web/backend/events.py）翻译到 SSE 时保持现有对外事件名不变**，前端零冲击。
- 参考：Pi SDK 事件协议、openhanako `lib/pi-sdk/stream-guard.ts`。

**AG-0.3 SSE 流身份（web/backend/sse.py 升级）**
- 每轮 turn 一个 `streamId`，事件按 `seq` 递增。
- 断线重连按 `streamId + seq` 游标补发（服务端 ring buffer 上限 5000 条 / 8MB，turn 结束清空）。
- 事件去重：客户端维护 `consumedSeqs`，重放不二次渲染。
- 参考：openhanako `server/session-stream-store.ts` + `services/stream-resume.ts`。
- 注意：传输层仍是 SSE，不换 WS。

**AG-0.4 流消毒守卫（core/stream_guard.py）**
- 包装 provider 流：畸形/空名 toolcall 缓冲并在结束点尝试恢复为文本；工具协议碎片丢弃不回写成可见文本；流层错误统一转 `error` 事件，永不裸抛。
- 参考：openhanako `lib/pi-sdk/stream-guard.ts`。

**AG-0.5 适配层门面（core/runtime/ 目录）**
- 为 provider / 工具 / 记忆建立唯一门面（类似 openhanako `lib/pi-sdk/index.ts` 的纪律，但不做构建期扫描：Python 侧用 import 约定 + 测试约束）。
- 目的：将来任何外部运行时依赖（如接入 Pi SDK 或换 provider 体系）只改门面。

**AG-0 验收**：现有 Python 测试全绿（预计 1100+）；事件总线有单元测试；SSE 流身份断线重连有 Playwright 测试；前端对外事件名不变。

---

### AG-1 会话革命（中风险，P5G 验收后启动）

目标：会话从"整份 JSON 覆盖写"变为"可审计的 append-only 流水账"，裁剪从"删消息"变为"投影"。

**AG-1.1 事件源会话格式（core/session.py 改造）**
- 会话正文 JSONL：一行一个 entry，`{id, type, ts, ...}`。消息、工具结果、模型切换、流身份变更都是 entry。
- `parentId` 字段保留但默认线性（不做分叉树，为将来留位）。
- 旧 `.json` 会话：读取路径保留，加载时一次性迁移为 JSONL 并归档原文件；迁移前校验，失败不删除。
- 现有 `max_messages` 原子分组裁剪逻辑保留为 context 投影策略。

**AG-1.2 持久会话与模型上下文分离（core/context_builder.py）**
- session 文件回答"发生了什么"（完整历史永不删）；context 构建回答"模型需要什么"。
- 裁剪/压缩成为纯投影函数（build_context(messages, budget) → 输入给模型的 messages），可安全重试、可审计。
- 参考：Pi `session-manager.ts` 的 `buildContextEntries()` / `buildSessionContext()`。

**AG-1.3 per-session 能力冻结（core/session_snapshot.py）**
- session 创建时冻结 systemPrompt / skills / 记忆参与态 / toolNames 快照；restore 时用快照重建，缺失工具做 repair。
- 配置/技能/记忆变更不影响旧会话（保护 prefix cache 与执行一致性）。
- 参考：openhanako `core/session-prompt-snapshot.ts`、`repairRestoredToolSnapshotDetailed`。

**AG-1.4 模型切换作为会话一等事件**
- `model_change` 写入 JSONL entry、参与 context 构建；切换 provider 后旧会话可恢复、可审计。
- 参考：Pi `model_change` / `thinking_level_change` entry。

**AG-1 验收**：旧会话迁移 Playwright 测试（导入→提问→重启→恢复）；千条消息会话可打开、可恢复、滚动位置保持；配置变更后旧会话行为不变。

---

### AG-2 循环增强（依赖 AG-0）

目标：循环瘦身为"调用 LLM → 执行工具 → 检查守卫"三件事，能力全部钩子化。

**AG-2.1 内部化两层钩子（core/hooks.py）**
- tool 级：`before_tool`（返回 `{allow}` 或 `{block, reason, terminate}`）、`after_tool`（结果消毒、审计、证据状态记录）。
- turn 级：`before_turn`（记忆注入、复习提醒）、`after_turn`（usage 记账、标题生成、学习事件）。
- Python 简单注册表：`register_hook(event, fn)` + 按 event 顺序分发。不开放插件 API。
- 参考：Pi 钩子返回值语义（`tool_call` 返回 `{block, reason, terminate}`）、openhanako extension 注入模式。

**AG-2.2 证据门禁沉淀为策略钩子**
- `CombinedResponsePolicy` 变为一组策略对象挂"最终回答前"检查点：local evidence 策略 + concept map 策略。
- 对外接口不变，`max_retries` 重试逻辑保留；现有测试继续跑。
- 工具白名单（`allowed_tool_names`）、web 权限确认（`request_web_search` 逻辑）一并沉淀为 before_tool 钩子。

**AG-2.3 只读工具并行执行（core/agent_loop.py 工具执行段）**
- 白名单内只读工具（rag_search / concept_map_query / knowledge_status 等）并发执行，线程池 2~4。
- 写操作工具（change_dir / 文件写入 / obsidian 导出）严格串行。
- 结果严格按模型调用顺序回填；`tool_start`/`tool_end` 事件顺序不变（前端无感知）。
- 线程安全：每个并发工具调用独立连接或锁保护（SQLite / Qdrant）。
- 参考：Pi preflight 顺序化、执行并发、结果按原始调用序恢复。

**AG-2.4 工具执行去重**
- 按 `toolCallId + 参数哈希` 稳定 key 去重，防止模型重复调用同一工具重复执行（幂等）。
- 参考：openhanako `wrapToolExecutionOnce`。

**AG-2 验收**：证据门禁测试全绿且实现改为钩子；多只读工具轮延迟下降（Playwright 或基准测试可测）；重复工具调用不重复执行。

---

### AG-3 记忆与压缩（依赖 AG-0 / AG-2）

目标：记忆注入有生命周期纪律；长会话有压缩能力；为本地模型预留 KV cache 意识。

**AG-3.1 记忆注入生命周期化（core/memory_injector.py）**
- 注入挂 `before_turn`：每轮开始前检索相关已确认个人知识 + 学习状态（掌握度/薄弱点），打包注入。
- token 预算默认 1500（可配置）；注入内容只能调整讲解方式，不能冒充原文证据（证据门禁边界不变）。
- 提取不做 LLM 版：学习事件已是确定性自动沉淀（做题/阅读/复习），不需要 LLM 提取钩子。
- 参考：Pi `before_agent_start` 注入点 + token 预算（db0 扩展默认 1500 token）。

**AG-3.2 KV cache 友好的 prompt 布局**
- 静态前缀在前（身份/证据契约/稳定规则）、动态尾部在后（记忆/当前上下文），中间显式 cache 分界线。
- 注入块 turn 间保持稳定（前缀缓存从第一个不同 token 全部失效，乱动 = 每轮全量重算）。
- 参考：openhanako `core/agent.ts` `buildSystemPrompt`、pi-memory 的 cache-stable snapshot。

**AG-3.3 长会话 checkpoint 压缩（core/session_compactor.py）**
- 判据：context 超限（保留输出余量，如 `contextWindow - 16384`）。
- 摘要为结构化 checkpoint：目标 / 进展 / 阻塞 / 下一步 + 保留尾部最近对话。
- 压缩不删历史（compaction 只是 context 投影）；旧 checkpoint 存在时增量合并。
- 参考：Pi `compaction.ts`（shouldCompact 判据 + summarizer prompt + 固定骨架）。
- 溢出兜底：provider 报 `context_length_exceeded` 时自动丢弃失败消息 → 压缩 → 重试一次。

**AG-3 验收**：长会话（>200 轮）回答质量不塌（人工抽检 + 测试）；压缩后历史可恢复；记忆注入不突破预算；KV 布局稳定（若接本地模型可测 cache 命中）。

---

## 3. B 系列：车厢（前端体验，参考 OpenHanako）

### FE-1 前端地基（纯前端零后端依赖，立即可做）

- **selector 归一化**：`sessionScopedValue` 模式，读 per-session map 时在 selector 内做 key 归一化 + 空数组常量，其他 session 更新不触发本组件重渲染。
- **乐观用户消息三态**：`appendOptimistic → confirm → markFailed`，发送零延迟感知，失败标红可重试。
- **块级 ErrorBoundary**：每个 content block 独立错误边界，一个卡片崩溃不影响整条消息。
- **动画原语封装**：三档纸感 spring 预设 + `FadeIn / Collapse / SlideIn / AnimatedList`，业务组件只从 `@/ui` 导入，换动画库零成本。
- **CSS Token 体系**：语义 Token + rgb 拆分变量（`--accent-rgb` 用于组合透明度）；主题切换只改 `data-theme` 属性不走 React。
- **上滑分页 + scrollTop 补偿**：`scrollTop < 200` 触发加载更早消息，`prevScrollHeight` 差值补偿无跳动。

### FE-2 流式体验（依赖 AG-0.3 的 streamId + seq）

- **StreamBuffer 30fps 节流**：SSE 事件写纯 JS buffer，33ms 批量 flush store，markdown 渲染随 flush 节流。
- **Markdown 顶层节点 reconcile**：流式追加时逐顶层节点比较 outerHTML，已稳定段落保留 DOM 身份，用户选区不被打断。
- **贴底滚动 rAF 指数缓动**：τ=85ms，大跳变（>720px）瞬移，用户干预即取消跟随，ResizeObserver 内容增减跟随。
- **自适应流式文本节流**：`Intl.Segmenter` 分词 + backlog 自适应批量 + hard catch-up；`prefers-reduced-motion` 全量显示。
- **TailFade 尾部渐隐**：流式尾部 grapheme 包 span 加 100ms 淡入，打字机 dots 用 steps() 循环。

### FE-3 过程披露（依赖 AG-0.2 事件收敛 + 消息模型）

- **过程折叠**：连续 ≥3 条纯过程消息合并为一个折叠块（摘要 + 展开面板），流式尾随 turn 不折叠；折叠时消息仍注册 DOM ref（定位/框选可用）。
- **工具组折叠**：`tool_end` 时自动折叠多工具组，摘要"n 个工具 / n 次失败"，未完成显示运行 dots。
- **CardParser 卡片实时化**：模型流式输出 `<card type="citation|practice|confirm">`，前端实时解析渲染，替代"工具结束才发 artifact"的延迟感。
- **不做**：think/mood 标签解析（思维链不展示，mood 是 openhanako 人格协议）。

### FE-4 页面联动与图谱动效

**页面联动（已确认范围）**：
- ① 带上下文跳转（双向、无感）：练习页"问 AI"跳 Chat 带上"我正在做 Dijkstra 第 3 题"上下文，答完能回原位；知识地图点击概念 → Chat 问它，属同一机制。
- ② 学习范围状态共享（带联动反馈）：当前学习范围在 Chat / Practice / Review / Library 是同一份状态，一处修改处处可见。
- ③ 轻量导航过渡：页面切换统一 FadeIn（淡入 + 微移），不做整页滑动切换。
- 不做：组件级 dashboard 联动（选侧栏资料 → 主区实时预览），稀释对话主入口定位。

**知识图谱动效（技术底座：维持 sigma.js + graphology + forceAtlas2，不换库）**：

现有 GraphCanvas 已有：选中聚焦、hover 高亮（瞬时无过渡）、边 hover 标签、拖拽 + 位置保存（800ms 防抖）、相机动画（偏快偏硬）、LOD 渐进显示。在此基础上补：

| 配方 | 内容 | 参数 | 状态 |
|---|---|---|---|
| 1 入场 | 先布局后入场，节点按距图中心距离错峰点亮 | 画布 500ms 淡入；相机 600ms；节点 size 0.85→1.0 + 上浮 6px，400ms；stagger 35ms，总 ≤1.2s | 做 |
| 2 hover 过渡 | 过渡层 tween（reducer 插值），"结构被点亮" | 进 180ms / 出 280ms，ease-out | 做 |
| 3 聚焦升级 | 相机缓动 + 选中节点细环（1.3×，静态）+ 度数行走 | 相机 460ms ease-in-out；`+`/`-` 扩展到 2/3 度，Esc 返回（抄 Kumu） | 做 |
| 4 活跃节点呼吸 | 最近确认/练习/复习的概念微呼吸 + 极淡光晕 | ≤15 节点，3s 周期，5% 振幅，相位按 id 散开，10fps 轮询（不写 shader） | 做 |
| 5 新节点入场脉冲 | 候选确认进图谱时波纹环 | size 0.2→1.0 450ms；波纹 1→2.4×，alpha 0.5→0，700ms，播一次 | 做 |
| 6 拖拽反馈 | 抓起放大 + 描边，松手回落 | 抓起 100ms；回落 180ms ease-out；不做 spring 回弹 | 做 |
| 7 粒子边 | react-force-graph 风格粒子流动 | — | 不做（保留箭头） |
| 8 全图呼吸 | 整图常驻动画 | — | 不做（噪音，Living Graph 教训） |

**额外交互**：搜索 spotlight（匹配节点戴 glow ring + 其余调暗，抄 Obsidian Graph Type to Search）；力参数用户可调（center / repel / link 三档，抄 Obsidian，成本极低）。

**降级纪律（必做）**：canvas 动画手动检测 `prefers-reduced-motion`（canvas 不走 CSS）；布局异步化（forceAtlas2 上千节点是同步阻塞，改 worker 或异步版，期间显示"正在铺开"提示）；动效可关停开关；活跃节点轮询 10fps 有性能预算。

### B 系列验收

- FE-1：千条消息会话滚动不卡（DevTools Performance 可测）；发送消息零延迟感知。
- FE-2：流式渲染 30fps 封顶；流式阅读中选中文字不被打断（Playwright 可测）；断线重连不丢渲染进度。
- FE-3：长会话 DOM 节点控制在折叠块量级；练习卡边生成边展示。
- FE-4：跨页面跳转上下文不丢；图谱节点动效符合暖纸面克制审美（不炫技、可关停）。

---

## 4. LB-1 资料协作（新功能）

### 定位

用户导入 Bobodan 的资料不应是只读牢房。资料库要像 Obsidian 一样可编辑，AI 在用户确认下可协助维护。**"原始资料是 truth source"原则不变，一切写入走检查点。**

### 功能拆解

**LB-1.1 用户编辑（Markdown 优先）**
- Markdown / 文本类资料：内联编辑，检查点 + 版本 + 冲突提示。
- PDF / DOCX / PPTX 等二进制格式第一版只读。
- **版本管理（已确认）**：保留最近 10 个版本（完整文件快照，Markdown 文件小成本可忽略）；回滚粒度 = 单文件级（恢复快照 + 触发联动）；不做行级 diff 回滚、不做全库快照；检查点复用现有 Wiki 检查点机制（`.bobodan/checkpoints/`）。
- **Obsidian 双开冲突（已确认）**：编辑前记录内容哈希，应用编辑前重算对比；不一致 → 三选项（覆盖外部修改 / 放弃本次编辑 / 另存为新文件进 `raw/inbox/`）；不做自动合并（文本合并易错）；不做双向同步（文件系统即共享真相）。AI 提案应用前同样做哈希检测，外部改过则提案暂停。
- 编辑后自动触发：重索引 → 引用它的 Wiki 页标记 `needs_update` → 检查点可回滚。

**LB-1.2 AI 协作编辑（提案 → 确认）**
- AI 对 raw/ 保持只读权限，改为产出**编辑提案**（diff + 理由 + 影响范围预览：哪些 Wiki 页 / RAG 引用会受影响）。
- 用户确认后应用；复用 Wiki 的"计划 → 确认 → 检查点 → 撤销"工作流。
- AI 创建新资料：同样走提案确认，创建后自动进 `raw/inbox/` 并索引。
- 权限模型：编辑提案只允许 Markdown 类资料；AI 不得直接写文件。
- **编辑与学习事件的关系（已确认）**：编辑本身不触发 LearningEvent、不影响掌握度（学习事件只认做题/阅读/复习等确定性行为）；但编辑内容是高质量信号，AI 观察到"用户在 X 概念页做了补充编辑"时生成 KnowledgeCandidate，走 P5F.1 候选确认流；练习/复习上下文中的编辑可轻量关联到错题（仍只进候选区，不动掌握度数字）。

**LB-1.3 联动与一致性**
- 资料变化 → 索引重建 → 受影响 Wiki 页 `needs_update` → Chat 回答引用自动指向新版本。
- 冲突（用户编辑 vs AI 提案同时进行）→ 明确提示，不静默合并。

### 验收

- 用户可编辑 Markdown 资料并回滚；外部修改冲突有明确提示。
- AI 提案 → 确认 → 应用 → 撤销全链路 Playwright 测试。
- 编辑后引用它的 Wiki 页标记更新，回答不再引用旧内容。

---

## 5. C 系列：性能预算（横切面）

| 指标 | 目标 |
|---|---|
| 流式渲染 | 30fps flush 封顶（33ms 批量写 store，markdown 随 flush 节流） |
| 长会话 | 连续 ≥3 条纯过程消息自动折叠；千条消息 DOM 节点控制在折叠块量级 |
| 滚动 | 贴底跟随 τ=85ms 指数缓动；大跳变（>720px）瞬移 |
| 断线恢复 | 重连后按 `streamId + seq` 游标补发，不丢渲染进度 |
| 内存 | 消息缓存 LRU 上限（Web 端约 8 会话，超出折叠 + 分页兜底） |
| 图谱 | 数百至数千节点流畅交互（拖拽/缩放/聚焦）；forceAtlas2 布局异步化，避免大图同步阻塞 |

---

## 6. D 系列：技术栈结论

**保持不动**：Python + FastAPI + SQLite + React + Vite + Zustand + SSE + Electron（P5G.2 路线）。

**补强**：
- 前端引入 motion（openhanako 同款，动画原语底座）。
- 必要时 TipTap（富文本输入，FE 阶段先留接口不实现）。
- 图谱底座已定：维持 sigma.js + graphology + forceAtlas2（见 FE-4），不换库；需补布局异步化。

**明确不引入**：虚拟滚动库（折叠 + 分页够用）、WS 传输层、事件总线库（自研 200 行）、插件市场体系、Neo4j。

---

## 7. 排期总览

```text
与 P5G 并行（立即开工）
  AG-0 外围地基（事件总线 / 事件收敛 / SSE 流身份 / 流消毒 / 门面）
  FE-1 前端地基（selector / 乐观消息 / ErrorBoundary / 动画原语 / Token / 分页）
  LB-1.1 用户编辑（Markdown 优先，检查点 + 冲突提示）

依赖 AG-0（AG-0 完成后启动）
  AG-2 循环增强（钩子 / 证据门禁沉淀 / 只读并行 / 去重）
  FE-2 流式体验（StreamBuffer / reconcile / 贴底滚动）

依赖 AG-2 / 消息模型
  AG-3 记忆与压缩（注入生命周期 / KV 布局 / checkpoint 压缩）
  FE-3 过程披露（过程折叠 / 工具组折叠 / CardParser）
  LB-1.2 AI 协作编辑（提案 → 确认）

P5G 验收后启动
  AG-1 会话革命（JSONL 事件源 / 上下文分离 / 能力冻结 / 模型切换一等事件）

依赖 AG-1
  FE-4 页面联动与图谱动效（跨页跳转上下文 / 图谱配方 1-6 / spotlight / 力参数）
```

**阶段门禁**：每阶段验收条件成立才进下一阶段；任何阶段不得只交付静态占位。

---

## 8. 明确不做（防止范围蔓延）

- 会话分叉树（fork / clone）——字段留位，不做 UI 和管理。
- 思维链 / mood 展示——产品规则与定位分界，不破。
- WS 迁移——SSE + seq 已覆盖重放需求。
- PDF / DOCX 编辑——二进制文档编辑是深坑，第一版只读。
- AI 直接写文件——一切写入走提案确认。
- 插件市场、多 Agent、频道社交入口——P5G 已定的边界，不变。
- 虚拟滚动库、Neo4j、事件总线库——现有方案够用。

---

## 9. 参考实现索引

| 借鉴点 | 参考源 |
|---|---|
| 事件总线过滤路由 | openhanako `hub/event-bus.ts` |
| 流式标签解析 / CardParser | openhanako `core/events.ts`、`server/routes/chat.ts` |
| 流消毒守卫 | openhanako `lib/pi-sdk/stream-guard.ts` |
| SSE 流身份 + 重放 | openhanako `server/session-stream-store.ts`、`services/stream-resume.ts` |
| 30fps 流缓冲 | openhanako `hooks/use-stream-buffer.ts` |
| Markdown 顶层 reconcile | openhanako `components/chat/MarkdownContent.tsx` |
| 贴底滚动缓动 | openhanako `hooks/use-continuous-bottom-scroll.ts` |
| 过程折叠 | openhanako `components/chat/process-fold.ts` + `ProcessFoldBlock.tsx` |
| 乐观消息三态 | openhanako `chat-slice.ts` |
| 事件源会话 + 上下文分离 | Pi `session-manager.ts`、`docs/latest/session-format` |
| 事件四层收敛 | Pi `docs/latest/sdk#events`、`docs/latest/rpc#event-types` |
| 可拦截钩子语义 | Pi `docs/latest/extensions`（tool_call / tool_result / input） |
| 只读工具并行 | Pi（preflight 顺序化、执行并发、结果按原始序恢复） |
| checkpoint 压缩 | Pi `compaction.ts` |
| 记忆注入生命周期 | Pi `before_agent_start` 钩子 + db0 / pi-memory 扩展 |
| KV cache 意识 | pi-memory cache-stable snapshot、openhanako `buildSystemPrompt` |
| per-session 能力冻结 | openhanako `core/session-prompt-snapshot.ts` |
| 图谱动效 | 子代理研究报告：维持 sigma.js + graphology；配方参考 obsidian graph（spotlight / 力参数）、Kumu（度数行走）、Heptabase（整理即动画）、react-force-graph（hover 高亮 / 粒子边反面参考） |
