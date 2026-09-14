# 更新日志

所有重要变更都记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/)，版本号遵循 [语义化版本](https://semver.org/)。

## [未发布]

### 变更
- **A4 批次二 · 事件落库与断线续传（P1-17，2026-09-14）**：续传这条路**每一节都在、就是没通电**——seq 打戳、`StreamStore`、`/streams/{id}/replay` 端点、前端按 seq 去重，全都写好了；但存储是**进程内内存缓冲**，而且每个 run 在 `finally` 里调 `emitter.clear()`（断线也走这条路径）——**清除的时机与重放的目的正好相反**，所以重连永远读不到任何东西，重启更是一片空白。
  - 复现：新增 `tests/test_event_log.py` 五条（每流单调 seq、游标读取、**新实例仍能读到**（模拟重启）、12 线程并发 append 得到唯一 seq、保留策略淘汰旧流）+ `tests/test_web_backend.py` 一条端到端：写入两帧 → 清掉进程内 store 缓存（模拟重启）→ 请求 replay 端点仍然拿到 `seq: 2` 与内容。**修前失败信号**：`ModuleNotFoundError: core.event_log`；以及旧实现下 replay 在 clear 之后返回空。
  - 修法：新增 `core/event_log.py`（SQLite `stream_events(stream_id, seq, event, data, created_at)`，seq 的读改写放在 `begin_immediate` 事务里保证并发唯一，`read_after` 游标读取，`prune` 按保留天数与流数量上限回收）；`StreamStore` 可挂一个 `EventLog`，挂上之后**完全以日志为准**（内存缓冲不再参与——否则重启后缓冲自己的计数器会与日志的 seq 打架）；`get_stream_store(workspace)` 按 workspace 缓存；`create_run` 改用 workspace store 并在开跑时 `prune()`；**删掉两处 `emitter.clear()`**；replay 端点改为读持久日志，并同时接受 `after_seq` 与 `Last-Event-ID`（浏览器 EventSource 重连时会自动带它）。
  - 留待：客户端重连时发 `after_seq` 的接线、以及「宽限期内可续、超期 abort」——两者都依赖批次三的协作取消原语，放在那一批一起做，避免又造一个「写了没通电」的机制。
- **A4 批次二 · 上下文压缩接线 + 配对兜底（P0-8、P1-11，2026-09-14）**：审计说的三重问题都成立——①`context_window` 参数存在但**两个生产调用方都不传**，压缩路径永不触发（死代码）；②即便触发，`checkpoint` 也是 `None`，`project_context` 丢掉中段却不留任何摘要（静默丢失）；③尾部切点用 `rest[-tail:]`，可能正好落在 `role=tool` 上，把配对的 `assistant(tool_calls)` 切掉，严格 provider 直接 400。另外 P1-11 指出「暂停在 ask_user 后不 resume 直接发下一条」同样会留下悬空 `tool_call`。
  - 复现：新增 `tests/test_context_projection.py` 八条——①切点永不落在 tool 响应上（拉回边界而不是前移）；②丢弃的中段必须转成确定性 checkpoint（含目标与用过的工具）；③孤儿 tool 响应被丢弃；④缺失的 tool 响应被补桩（`assistant` → `tool` 顺序）；⑤健康 transcript 原样通过；⑥**经由 AgentLoop 实测**发往 provider 的 payload 里悬空 tool_call 已被补桩；⑦`resolve_context_window` 对缺失/0/非数字回退到保守默认；⑧`AgentService.run_stream` 确实把 window 传给 loop。**修前失败信号**：`ImportError: INTERRUPTED_TOOL_RESULT`（机制不存在），以及 loop 发出的 transcript 里 `assistant(tool_calls)` 后面直接跟 `user`。
  - 修法：`repair_tool_pairing()` 放在**最终序列化层**（`_build_context` 的返回处，也就是 provider 真正看到的 payload），两条不变量一次覆盖，任何将来的投影改动都不会再引入非法 transcript；`_tail_start()` 把边界往**前**拉而不是往后推（保持配对完整）；`structural_checkpoint()` 用规则而不是模型抽取目标/工具/失败数——**用模型去总结一个刚刚超窗的上下文，需要正是刚才耗尽的那份预算**；`DEFAULT_CONTEXT_WINDOW = 32000` + `resolve_context_window(config)`，Web 与 CLI 两个生产入口都传，`config.yaml` 增加 `agent.context_window`。
- **A4 批次二 · hooks 最小接线 + P0-9 工具结果上限（2026-09-14）**：`core/hooks.py` 与它的四个派发点早在 AG-2.1 就写好了，但**生产代码里注册数为零**——文档声称承载权限检查与结果消毒，实际运行的代码里没有这两件事。同时 P0-9 指出单条工具结果没有任何上限（只有 `read_file` 自带 1MB），`rag_search` 还会把同一批 chunk 在 JSON 与格式化文本里序列化两遍。
  - 复现：新增 `tests/test_builtin_hooks.py` 七条——①超长结果必须被截断且**保留头尾**并带省略说明；②短结果原样通过；③**失败结果永不截断**（错误文本是唯一的排查线索）；④经 `dispatch(AFTER_TOOL, …)` 走一遍派发后拿到的替换结果确实被限界；⑤白名单门对未启用工具返回 `unavailable in this runtime`（与既有测试断言的文案一致）、对 `allowed=None` 放行；⑥重复注册不产生重复 hook；⑦**构造一个 AgentLoop 后注册表里必须能查到这两个内建 hook**——这正是审计测试盲区第 7 条缺的守护。**修前失败信号**：`ModuleNotFoundError: core.builtin_hooks`，以及注册表在生产路径下始终为空。
  - 修法：新增 `core/builtin_hooks.py`——`cap_tool_result`（32000 字符上限、头尾各 40%、中间替换为省略说明并提示用 offset/limit 续读、失败结果豁免）与 `allowlist_gate`（把白名单作为**每次派发的数据**传入，而不是全局注册，避免 specialist 的白名单污染主循环）；`AgentLoop.__init__` 调用幂等的 `register_builtin_hooks()`（每个运行路径都会构造 loop，覆盖面最广，也不怕新增调用方忘记接线）；原先内联的白名单判断改为走注册表派发，行为与文案保持不变。
- **A4 止血轮立项（2026-09-14）**：外部审计 [`TECH_AUDIT_2026-09-14.md`](TECH_AUDIT_2026-09-14.md) 落库（15 P0 / 36 P1 / 33 P2 / 12 测试盲区）。本轮按「先止血 → 再接线 → 横切原语单独立项」推进；`docs/ROADMAP.md` 新增 **§2 A4 止血轮**，把要做哪几条与审计编号对应起来，P2 不排期。审计编号 `P0-x` / `P1-x` 成为稳定引用，后续提交信息带编号。
  - 立项前对照三个本地参考项目（DeepTutor / OpenMAIC / openhanako-reference）逐条核查，确认可照搬项（工具渐进披露、原子写地基、事件表 + `Last-Event-ID`、lease 队列、序列化后配对兜底）与**不要抄的坑**（Windows 上 `fcntl` 缺失即静默无锁、`setdefault` 给模型留缝、ring buffer 不能当唯一恢复依据）。其中 DeepTutor 的 `tools/file_tools.py` 路径校验写了却从未接线、`events/event_bus.py` 只发无订阅者，与本次审计「不缺架构缺接线」的判断互为印证。
  - 验收口径：每条先写会失败的复现测试再修；断线取消 / Qdrant 双开 / 删除确认 / 向量补建四类必须真实集成或故障注入；CHANGELOG 记录复现方式与失败信号。
- **设计规格层重写 + 骨架层落地（2026-09-14）**：用户实测反馈「前端 UI 还是不好看、不够丝滑」，复查 `docs/DESIGN.md` 后确认问题不是「约束太紧」，而是**紧在禁令、松在规格**——对照 DeepTutor / openhanako / OpenMAIC 三个参考项目（见 `docs/REFERENCE_PROJECTS.md`）找出可借鉴项后，先重写规格层，再落地骨架层。
  - **诊断（全部为实测）**：三档纸色 `#f5f4ed` / `#f7f5ef` / `#f3efe5` 只差 2–4/255，等于一档；全站只有 31 条 `transition`；文档写「辅助说明 12–13px」而 494 条 `font-size` 里 233 条（47%）低于 12px；`--blue*` 被引用 188 次而 `--petal-wash` 只有 2 次。禁令没有反面（§14 原先全是绝对禁止、没有配额），实现只能退到「发丝线列表 + 只用主色」。
  - **§4 颜色改为面积预算**：每个色相给正面配额（墨蓝 / 纸色作结构色不限；sage、clay 每屏各 ≤ 1 个整块区域；petal ≤ 视口 2% 且必须列调用点，否则删 token）；§14 只禁止「超出预算」与整页主题化。
  - **§4 token 表成为唯一真相源**：改成代码里真实使用的命名（文档里那套 `--color-*` 从未被实现），34 条 token 的名与值必须等于 `styles.css` 的 `:root`，由契约测试逐条校验。
  - **§7 表面 / 边框 / 高度分档**：纸色三档拉开（`--paper-soft` 提亮、新增 `--paper-sunken` 作停靠面）、边框分 0.06 / 0.12 / 0.20 三档、新增 `--shadow-lift` 给内容 hover 与选中；圆角扩到 6 / 8 / 12 / 16 四档并明令禁止 5 / 7 / 9px；配额写死「内容区每屏 ≤ 1 层嵌套表面、≤ 1 处抬升」。
  - **§5 / §6 / §11**：字号下限（辅助 ≥12 / UI 标签 ≥13 / 正文 16–18）写成硬约束并记录当前差距；新增 4 / 8 / 12 / 16 / 24 / 32 / 48 间距刻度（只有图标与 1px 边框豁免）；新增三档 spring 预设（CSS `linear()` 近似、过冲 ≤2%）+ 允许 `scale` 0.96–1.02 与 ≤220ms 布局动画——**仍不引入 motion 库**。
  - **§14 拆成「底线」与「配额」**，新增 **§16 组件规格与交互四态**：静置 / hover / active / focus-visible / disabled 四态表 + 逐组件规格表（页面容器、停靠栏、顶栏、卡片、列表行、主次要按钮、图标按钮、输入框、chip、状态块、浮层、弹窗抽屉）。
  - **骨架层落地**：侧栏与右栏改用 `--paper-sunken`（三级结构第一次显形）、顶栏与右栏 tab 的 active 走 `--shadow-lift`、导航与按钮补 hover 抬升与 spring 按压、圆角与间距开始引用 token、shell 一层 10 处 10–11px 标签提到 12px、`--muted` / `--faint` 拉开并加深（正文对比度同时改善）。
  - **防漂移**：新增 `web/frontend/src/lib/designTokens.test.ts` ——文档 ↔ 代码 token 一致性（含「代码里属于规格命名空间的 token 必须写进文档」的反向检查）+ 三条棘轮（<12px 字号 ≤226、裸 `ease` ≤16、不在 §7 刻度上的圆角 ≤73、过渡里的裸毫秒 ≤5），只允许下调。已实测：故意把文档里的 `--paper` 改成 `#f5f4ee`，测试精确报出 `--paper: 文档 #f5f4ee / 代码 #f5f4ed`。
  - **F19 批次 1 · Chat 页（2026-09-14）**：按新规格收敛 Chat 面。实测起点：一条消息里塞着 8.8px 的时间戳（`<small>` 在 11px 的 `.run-summary` 里按 0.8em 缩）、9–11px 的 `personalization-chip` 与来源 chip、10px 的编排器下拉与输入提示、12.5px 的选项 chip。
    - **字号**：`.run-summary` 11→12、`personalization-chip` 9/10/11→12、`.source-chip` 11→12、`.composer-hint` 10→12、选项 chip 12.5→13、下拉触发器 10→13（菜单项 11→13、分组标题 9→12、`.dropdown-item small` 9→12）；正文侧 `.user-message` 15→16、`practice-ready-card p` 12→13、`.answer-prose table` 14→`var(--body-font-size)`。实测结果：**Chat 页正文与辅助文字最小 12px，不再有低于下限的元素**（审计脚本对 71 个文本节点逐个取计算样式）。
    - **密度**：`.assistant-message` 48→32、`.user-message-wrap` 34→24、`.conversation` 内边距 44/30→32/24、`.source-row` 18→16、`answer-actions` 14→16，全部改走 `--space-*`；圆角全部改走 `--radius-*`（含原先 4px/7px 的越轨值），`.dropdown-panel` 那处写死的旧纸色 `rgba(247,245,239,.98)` 换成 `var(--paper-soft)`。
    - **交互态**：`.source-chip` 的 `ease` 换成 `var(--ease-out)`，按压改用 `var(--spring-micro)`；下拉触发器/菜单项补 transition，选项 chip 选中态补 `--shadow-lift`。
    - **回归测试**：`e2e/interaction.spec.ts` 新增「每一个 Chat 文案都在字号下限之上」——同一会话的**未作答卡与已作答两种状态**都逐节点扫描（低于 12px 就把元素与像素值列出来）、选项 chip ≥13、气泡与答案正文 ≥16、把 `--body-font-size` 调到 18px 后正文跟着变、宽视口下编排器工具条不溢出。三视口通过。
    - 棘轮同步下调：<12px 字号 226→**208**、裸 `ease` 16→**15**、脱轨圆角 73→**69**、裸毫秒 5→**4**。
    - 验证：Python `1450 passed`、Vitest `63 passed`、ESLint 与生产构建通过、Playwright 全量通过。
  - **F19 批次 2 · Practice·Review 页（2026-09-14）**：这一批直接对着用户的原始抱怨做——「题目周围有许多空白、题目显示太单调太淡、我的答案和参考答案都是浅色细字」。
    - **答案不再又浅又小**：练习结果里 `.answer-feedback small`（参考答案）原先**没有字号**、只知道继承 `<small>` 的 0.8em，颜色还是 `--muted`；现在 14px / `--ink` / 500 字重。小结里 `.recap-item small`（你的答案）11px `--muted` → 13px `--ink` 500；`.answer-feedback p`（批改意见与解析）改为跟随 `var(--body-font-size)`；判定标签 `.answer-feedback > div` 15px/700。
    - **输入与选项**：简答题 `.short-answer` 原先没有字号（继承容器），现在 16px 且跟随阅读偏好，圆角与内边距走 token；选项文字 14px → `var(--body-font-size)`，选项徽标 12→13px，选项行补 hover / 选中抬升与四态过渡。
    - **字号下限扫尾**：`.practice-header span` 11→12、`.practice-summary header span` 10→12、`.review-summary span` 11→12、`.review-kind` 11→12、`.review-row p` 11→12、`.review-more` 11→12、`.resume-row small` 10→12、`.practice-ai-drawer` 头部与上下文 10→12、`.page-heading` 眉标 11→12 与说明 14→15。
    - **密度与层级**：`.question-sheet` 内边距 30px→`var(--space-6)`、圆角 8→`var(--radius-lg)`；题目下间距 25→`var(--space-5)`；练习容器 34/30→`var(--space-6)/var(--space-5)`；小结与回顾的 gap / padding / 圆角全部改走 `--space-*` / `--radius-*`；`.practice-ai-drawer` 写死的旧纸色 `rgba(247,245,239,.98)` 换成 `var(--paper-soft)`；`.practice-mode button` 的 15px 胶囊改为 `var(--radius-xl)`。
    - **回归测试**：`e2e/app.spec.ts` 的判断题流程补上结果区字号断言（判定 ≥15 / 正文 ≥16 / 参考答案 ≥13）。
    - 棘轮同步下调：<12px 字号 208→**195**、脱轨圆角 69→**65**，裸 `ease` 与裸毫秒不变。实测复核：`/practice/11` 与 `/review` 两页的可见文本**已经没有低于 12px 的元素**。
    - 验证：Python `1450 passed`、Vitest `63 passed`、ESLint 与生产构建通过、Playwright 全量通过。
  - **停靠面回调 · 侧栏不再是一条黄带（2026-09-14，用户反馈）**：用户给的参照是 [tw93/Kami](https://github.com/tw93/Kami) 与 Claude 网站的暖纸风，并指出左右侧栏的颜色突兀。查参照项目的 `tokens.json` 后发现**本项目的调色板本来就与 Kami 同源**——画布 `#f5f4ed` 就是 Kami 的 `--parchment`，品牌色 `#1B365D` 就是 Kami 的 `--brand`；出问题的只是上一批自己挑的停靠面 `#efeade`：它比画布深 9–19/255，且 **HSL 饱和度 0.35 高于画布的 0.29**，于是整条侧栏渲染成饱和的橄榄黄。
    - 改成用 Kami 自己的三档：停靠面 `#f0eee6`（Kami 的 inline-code 灰）、画布 `#f5f4ed`（parchment）、抬升面 `#faf9f5`（ivory）。与画布的通道差收到 5–8/255。
    - **把「不突兀」变成可执行约束**：`DESIGN.md` §7 与 `designTokens.test.ts` 新增「纸张阶梯」——三档顺序固定、与画布每个通道差 ≤ 8/255、停靠面必须更灰（HSL 饱和度 ≤ 画布）。同一组断言对每个纸色主题都跑（含 `[data-paper-texture="off"]`，它原先只换了画布与抬升面，停靠面会漂到 11/255，已补上自己的值）。
    - 已实测这组断言真的会咬人：把停靠面改回 `#efeade` 会同时报出 `--paper-sunken` 通道超限与 `expected 0.3469 to be less than or equal to 0.2857`。
  - **F19 批次 3 · Library·Reader 页（2026-09-14）**：资料列表是整个应用里字号最失控的一页——50 行文档每行都带一个 **9px** 的 `.document-extraction-state`（「尚未提取」×47 / 「已提取」×3）和 **10px** 的 meta 行。
    - **资料列表**：状态 chip 9→12（`max-width` 70→88、`border-radius: 999px`→`var(--radius-xl)`）、标题 12→14、meta 10→12、行内边距与圆角改走 `--space-*` / `--radius-*`；工具条上下文 10→12、更多菜单 12→13 与浮层 5px 内边距→`var(--space-1)`。
    - **阅读器**：`section-location`（「资料片段」，单页 64 处）10→12、`reader-topbar-title span`（`COURSE DOCUMENT` 眉标）10→12。
    - **表单与编辑器一族**：用一条**按选择器前缀限定**的脚本（先 dry-run 打印 23 条改动再 `--apply`）把 `library-setup-dialog` / `library-path-hint` / `library-migration-preview` / `document-editor*` / `document-proposal*` / `reader-related-notes` / `document-bulk-tools` 的 9–11px 辅助文字统一提到 12px，`.library-tabs` / `.reader-tab` / `.chapter-rail` / `.library-switcher` / `.document-search` 提到 13px。
    - **回归测试**：`e2e/app.spec.ts` 的首次导入流程补上「建库弹窗内不得有低于 12px 的文字」断言。
    - 棘轮同步下调：<12px 字号 195→**167**、脱轨圆角 65→**60**。实测复核：`/library` 与 `/library/read/*` 两页可见文本**已无低于 12px 的元素**（资料列表 50 行、阅读器 300+ 文本节点）。
    - 验证：Python `1450 passed`、Vitest `69 passed`、ESLint 与生产构建通过、Playwright 全量通过。
  - **F19 批次 4 · 低频页 + 收口（2026-09-14，F19 完成）**：这一批用**按选择器前缀限定**的脚本做，先 dry-run 打印 123 条改动再 `--apply`；脚本本身也留在流程里，改的是选择器前缀可枚举的面。
    - **覆盖面**：设置页全部 8 个分区（含 AI 与模型 / 记忆与数据 / Provider / 状态与关于），Wiki 维护与编辑器，笔记列表与编辑器，知识地图（目录视图 / 来源视图 / 力导向参数），以及共用外壳（连接条、错误边界、快捷键面板、迁移预览、onboarding）。
    - **规则**：交互控件（导航、tab、工具条、预设行、编辑器工具条、快捷键分组）提到 13px；辅助文字（提示、字段说明、徽标、计数、摘要、告警）统一到 12px。
    - **收口扫尾**：另跑一条只做「低于 12px 全部提到 12」的脚本，把此前没有审计到的表面补齐——composer 作用域、@ 提及列表、斜杠命令面板、过程折叠、消息引用按钮、右栏的上下文关系 / 指标 / 文档 / 下一步，移动端底部导航，以及 5 条写在多行规则里的知识地图与侧栏标题。顺带修掉 `.candidate-badge` 的 9px 圆角与写死的 `#fff`。
    - **结果：整份 `styles.css` 的 494 条 `font-size` 声明里，低于 12px 的是 0 条**（本轮起点 233 条）。`designTokens.test.ts` 的那条棘轮随之从「预算 167」变成**门禁 0**：此后任何新增的低于 12px 字号都会直接失败。
    - 验证：Python `1450 passed`、Vitest `69 passed`、ESLint 与生产构建通过、Playwright `80 passed / 1 skipped`——全量在三视口重跑，确认这把扫过 200 条规则的改动没有破坏既有流程。实测复核：chat / practice / bank / library / reader / review / notes / knowledge-map 与设置的全部 8 个分区，可见文本均无低于 12px 的元素。
  - **F19 未做**：间距与圆角尚未全量收敛到 token（脱轨圆角 73 → 59，仍有存量）；暗色主题只留了可换主题的 token 形状与 `[data-theme]` 钩子。；暗色主题（本轮只把 token 改成可换主题的形状）。
  - 验证：Python `1450 passed`、Vitest `57 → 63 passed`、ESLint 与生产构建通过、Playwright `77 passed / 1 skipped`；`tests/conftest.py` 的 tripwire 确认全量跑前后真实工作区库未变。
- **题库收口 · 第 1 批（2026-09-11，E18 补齐）**：首轮交付后逐条对照 `QUESTION_BANK_DESIGN.md` §6 的验收条件，发现四处「设计写了、实现没有」的缺口，本批补齐前三处。
  - **筛选轴补全**：`difficulty`（难度）与 `source`（资料，精确匹配）打通 store → service → API → UI；题库页新增题型 / 难度 / 资料三个下拉（复用 `DropdownSelect`），资料列表来自 `bank_overview` 新增的 `by_source`，并补了「清除筛选」。`GET /api/quiz/bank` 的 `qtype` / `difficulty` 改为受校验参数。
  - **按当前筛选组卷**：批量按钮不再排除「已收藏」，并把概念 / 关键字 / 题型 / 难度 / 资料一起带进 `/api/quiz/bank/practice`，真正做到「练我正在看的这些」；按钮文案改为按状态取名词（错题 / 收藏题 / 未作答题…），免得出现「重练前 5 道未作答」这类句子。
  - **复习页去掉 20 条窗口**（D5/S4 的正式验收）：`get_review_queue` 现在返回题库的真实错题总数 `wrong_total`，行数窗口放宽到 200（路由上限 500），被截断时给「在题库中查看全部」。此前只统一了错题**定义**、窗口还在，错题超过 20 时两处数字会对不上——`QUESTION_BANK_DESIGN.md` §5 的 S4 状态已据实修正。
  - 仍未做：UI「问 AI」带 `question_id` 引用某题、命名练习集、S6 联网搜题、S7 导出与备份（见设计文档 §5 的收口清单）。
  - 验证：Python `1430 passed`、Vitest `57 passed`、lint 与生产构建通过、Playwright `59 passed / 1 skipped`（题库 e2e 由 6 条增至 9 条，覆盖难度 / 资料筛选与按筛选组卷）。
- **题库收口 · 第 2 批（2026-09-11，E18 补齐）**：D4 后半的「引用某一道题」落地。
  - 题库每行新增「问 AI」：把 `question_id` 写进对话草稿（`handoffStore.setChatDraft`）并跳到 Chat，用户可以先改再发。
  - `bank_list` 新增 `question_id` 参数，agent 按 id 读回**同一道题**（顺带补上 `difficulty` / `source` 过滤）；读回走的是题库路径，因此**未作答的题依旧不返回答案**——没有为「引用」新开一条泄题通道。
  - `GET /api/quiz/bank?question_id=` 同步支持（`ge=1`，`0` 返回 422）。
  - 验证：Python `1432 passed`、Vitest `57 passed`、lint 与构建通过、Playwright `62 passed / 1 skipped`（题库 e2e 增至 12 条，新增三视口「行内问 AI 把 id 带进对话草稿」）。
- **题库收口 · 第 3 批（2026-09-11，E18 补齐）**：命名练习集（D2 的承载物、D8 的两张小表）+ 测试隔离加固。
  - `question_sets(id, name, created_at, updated_at)` 与 `question_set_items(set_id, question_id, position, added_at)`：**只存 id、不复制题面**（有测试钉住列定义），集合因此永远不会与题库脱同步；建表走 `CREATE TABLE IF NOT EXISTS`，现有库零迁移。
  - 全套 REST：`GET|POST /api/quiz/sets`、`GET|PATCH|DELETE /api/quiz/sets/{id}`、`POST /api/quiz/sets/{id}/items`、`DELETE /api/quiz/sets/{id}/items/{question_id}`、`POST /api/quiz/sets/{id}/practice`（`question_set_not_found` → 404）。
  - 题库列表新增 `set_id` 视图：看集合只是多一个筛选条件，状态 tab / 分页 / 批量练照常工作，不必另写一套渲染；空集合读作空而不是「没有筛选」（空 id 列表会被当成无约束，这点单独处理）。
  - 题库页新增「练习集」区：按**当前筛选**存为命名集合（默认名取筛选摘要）、查看、练这集、改名、删除（走统一确认弹窗）；每行可加入某个集合或「新建并加入」，看集合时可逐题移出。
  - 按 D4，**agent 依旧不碰集合结构**（三个只读 / 收藏工具不变），集合的建改只在 UI 侧。
  - **测试隔离加固**（同批发现）：`tests/test_learning.py` 的两次 `generate_path` 与 `tests/test_repl.py` 全模块都把「当前目录」当工作区，会打开并迁移**开发者的真实 `.knowledge/bobodan.db`**——本轮新增题集建表让这个泄漏第一次产生了实际写入。修掉三处（显式传 `tmp_path` / 模块级 `monkeypatch.chdir`），并在 `tests/conftest.py` 加**会话结束的 tripwire**：跑完比对真实库的大小与 mtime，被动过就让这次运行失败并说明原因。此后全量跑的前后哈希与 mtime 完全一致。
  - 验证：Python `1437 passed`、Vitest `57 passed`、lint 与构建通过、Playwright `65 passed / 1 skipped`（题库 e2e 增至 15 条，新增三视口「按筛选建集 → 查看 → 练这集」）。
- **题库收口 · 第 4 批（2026-09-11，S6 联网搜题）**：D9 的第三类来源——「搜现成的题」。
  - 出题接口新增 `mode` 开关（`generate` / `search`）。`search` **只提取网页上已经存在的题目**（教材练习、课程测验、文档里的练习题），照原样保留题面与选项，不自己编写；页面里没有现成题就返回 `no_web_questions`，**不凑数、也不退回本地出题**——这条有回归测试钉住：搜题模式下 `generate_from_query` 一旦被调用就直接失败。
  - 「搜题没有本地分支」是刻意的：`search` 存在的理由就是「别人已有的题」，而不是「本地资料能生成什么」。因此它先要联网同意（沿用既有 `web_consent_required` 流程，文案改为解释两种模式的区别）。
  - 证据链与 D9 一致：来源页仍是不可变快照、`attribution_kind="web"`；每条来源额外标 `third_party: true`，这就是导出时区分「模型写的」与「页面本来就有的」的依据（第 5 批使用）。前端沿用现成的 `AttributionBadges` → `WebSourceBadge`：显示「网页来源」、可点回原文、可查看当时保存的引用片段。
  - 练习页新增「让 Bobodan 出题 / 搜现成的题」切换，并说明两者区别；搜题模式下没写主题会给出明确提示。
  - **未做**：把联网题的新概念注册成概念候选（D9 的硬边界「不进知识地图」本来就成立——没有任何路径把题目概念写进图谱；缺的是「只进候选」那半句的钩子），已在设计文档 §5 标注。
  - 验证：Python `1444 passed`、Vitest `57 passed`、lint 与构建通过、Playwright `68 passed / 1 skipped`（题库 e2e 增至 18 条，新增三视口「练习页切到搜题模式 → 请求带 mode=search」）。
- **题库页排版重构（2026-09-14）**：用户实测反馈「字体太小、组件占比太多、题目周围空白多、题目和答案太淡」。逐条查证后按 `docs/DESIGN.md` 的硬约束重做题库页的字号、层级与密度（**只改前端样式与结构，后端零改动**）。
  - **字号回到规范线**：§5 要求正文 16–18px / UI 标签 13–14px / 辅助说明 12–13px，而题库页此前有 9/10/11/12px 共 15 处。现在行内**最小字号 12px**（e2e 会扫描 `.bank-row` 内所有文本节点断言），筛选 / 下拉 / 搜索 / 分页 / 练习集一律 12.5–13.5px。
  - **题干跟随用户设置**：题干此前硬编码 17px、不读 `--body-font-size`，所以设置里的「正文字号」（15/16/17/18）对题库无效。现在用 `var(--body-font-size)` + `font-weight: 500` + `--ink`：靠字重与前景色取得存在感，而不是一味放大（参考 DeepTutor `QuestionCard` 的 `text-[14px] font-medium text-[var(--foreground)]`）。
  - **题目成为一张轻纸片**：`.bank-row` 从「发丝分隔线 + 两列 grid」改成单列轻卡片（细边框 + `--paper-soft`，**无阴影**），并按状态给 3px 左侧竖条（错题 clay / 基本正确与答对 sage / 未作答 中性）；文字状态 chip 保留——不把颜色当作唯一表达（DESIGN.md §14）。
  - **答案不再是一行浅灰小字**：答案区从 `12px + --muted` 的裸段落改成带「你的答案 / 参考答案」标签的**左边框色块**（复用练习页既有的 `.answer-feedback` 语言，13.5px + `--ink`，错题走 clay）；同时「你的答案：X」在行内可见，值用 `--ink` + 500 字重。没有采用 DeepTutor 那种「卡片里再放一个带边框的答案框」，因为那是 §14 明确禁止的卡片套卡片。
  - **控制区压缩**：状态筛选、搜索、题型 / 难度 / 资料下拉、清除筛选合并成**一个可换行区块**（此前是三行）；概念 chips 保留一行；练习集面板改为默认折叠的 `<details>`（有集合时自动展开）。首题 y 坐标 538 → **482**。
  - **行高与首屏**：桌面单行题 **208 → 169px（−19%）**，可见题目从约 2 行到约 **2.8 行**；做法是把右侧竖排的 4–5 个 40px 按钮改成页脚横排，并去掉与来源章重复的来源字符串。移动端因按钮必须换行，行高基本持平（281–337px）。
  - **范围纪律**：`.mention-tabs` / `.dropdown-trigger` / `.source-chip` 是全站共享类，只在 `.bank-toolbar` / `.bank-*` 作用域内覆盖；`.primary-button` 的 40px 最小高度是 DESIGN.md 硬规则，**没有为了压行高去违反它**。
  - **未做**：全站排版批次——`styles.css` 350 条 `font-size` 里仍有 247 条 < 13px，已把实测差距记进 `DESIGN.md` §5 作为后续验收口径。
  - 验证：Python `1450 passed`（后端零改动，跑一次确认没误伤）、Vitest `57 passed`、lint 与生产构建通过、Playwright `77 passed / 1 skipped`（题库 e2e 24 → 27 条，新增三视口「行内最小字号 ≥12px / 题干跟随 `--body-font-size` / 行高与首题位置上限 / 答案标签」）；另在真实 vault 库 17 题上量了改造前后对比并截图核对。
- **题库收口 · 第 5 批（2026-09-11，S7 导出与备份）**：D7 的两件事——Markdown 导出与备份 / 恢复。
  - **题库级备份 / 恢复**：`bobodan-question-bank` 带 schema 版本号的 JSON，覆盖题目、作答记录、会话、**收藏**与**命名练习集**——后两者只存在于这张库里，丢了无处可寻；恢复是**整体替换**（不做合并，否则会留下指向上一个资料库的作答记录），前端先弹统一确认框再提交。删除顺序按外键逆序（先子后父），这个 bug 是被往返测试抓出来的。
  - **Markdown 导出**：按当前筛选或某个命名练习集导出，按状态分组、带你的答案 / 参考答案 / 解析 / 知识点 / 来源。**D9 的第三方约束在这里落地**：来自外部页面的题（`third_party`）默认排除，并在导出说明里写明排除了几道；显式 `include_third_party` 时逐条标注「第三方题目（联网来源）…请勿再分发」。
  - 题库页页头新增「导出 Markdown / 备份 / 恢复」三个入口；排除第三方题目时用全局提示位告知，不静默。
  - **边界**：这是**题库自身**的备份。资料库整体备份 / 恢复仍属 `PROJECT_GUIDE.md` 的「数据保护专项」，届时把这份一起纳入。
  - 验证：Python `1450 passed`、Vitest `57 passed`、lint 与构建通过、Playwright `74 passed / 1 skipped`（题库 e2e 增至 24 条，新增三视口「导出下载 .md / .json」与「恢复前确认」）。
- **题库 MVP（E18 S1–S5，2026-09-10，分支 `feat/e18-question-bank`）**：把「每道生成的题都已经落库」接成用户能看见、能收藏、能重练的题库，兑现 `PracticePage` 里那句长期失真的「留空时会从现有题库与资料重点中选择」。设计依据 `docs/QUESTION_BANK_DESIGN.md`（D1–D9）。
  - **数据层**：`questions` 新增 `bookmarked_at`（沿用 `_ensure_db` 的 PRAGMA 迁移，幂等，现有题目零迁移）；新增 `list_bank_questions` / `count_bank_questions` / `bank_overview` / `set_bookmark`。状态**全部派生**——用 `MAX(id)` 子查询取最近一次作答，不物化任何状态列。未作答的题在列表与工具输出里都**不返回答案与解析**，题库不会变成答案表。
  - **错题语义收敛（有意为之的用户可见变更）**：`get_wrong_answers` 从「所有答错的尝试」改为「最近一次仍答错」，`partial` 不再算错（与 E15 三态判分对齐），`get_weakness_analysis` 同步排除 `partial`。答错后重练答对的题会同时从错题本和题库的错题筛选里消失；复习调度（SM-2）不受影响。
  - **接口**：`GET /api/quiz/bank`（状态 / 题型 / 资料 / 概念 / 关键字筛选 + 分页 + overview）、`POST /api/quiz/bank/bookmark`（幂等）、`POST /api/quiz/bank/practice`（按题目 id 或按当前筛选起练）。
  - **练习页题库视图**：新增 `/practice/bank`（静态段注册在 `practice/:practiceSessionId` 之前；作为 Practice 的一个视图，不新增一级导航）：状态筛选带计数、关键字搜索、概念筛选、分页、收藏、单题重练与按状态区分的批量重练；未作答的题不显示参考答案。
  - **复习衔接**：复习页与题库共用同一个「错题」定义，两页互有入口。
  - **Agent 工具**：`tools/question_bank.py` 提供 `bank_overview` / `bank_list` / `bank_bookmark`，只声明 `workspace`（`execute_tool` 只注入工具声明过的参数），只读 + 收藏、**不含起练**，因此不会重新打开 E13 已封堵的「聊天文本练习」通道。
  - **本轮未做**：命名练习集（D8 的两张小表）、S6 联网搜题、S7 导出与备份、题库行内「问 AI」引用某题；均记录在 `QUESTION_BANK_DESIGN.md` §5 与 `ROADMAP.md`。
  - 验证：Python `1427 passed`（+22）、Vitest `57 passed`、前端 lint 与生产构建通过、Playwright `56 passed / 1 skipped`（新增 `e2e/question-bank.spec.ts`，三视口各 2 条）。
  - **交付后审查修正**：`incorrect` 改成**兜底桶**——最近一次作答只要不是「通过」就算错题（`verdict = incorrect`、E15 前旧行、以及任何未识别的 verdict）。原来的写法会让一个未识别的 verdict 在界面上标成「答错」，却既进不了错题筛选、也不计入任何计数，四个状态加起来对不上总数；现在四个派生状态永远把题库分完，并有两个不变量测试钉住。`GET /api/quiz/bank` 的 `state` 改为受校验参数，拼错返回 422，而不是静默把整库列出来。题库页在结果集变小（例如在「已收藏」页取消最后一条收藏）时把页码收回有效范围；批量按钮按状态改用对应文案（未作答是「开始做」、答对是「复习」，不再一律叫「重练」）。
- **测试套件隔离修复（2026-09-11）**：`tests/conftest.py` 现在把 `BOBODAN_WORKSPACE` 一并指向一次性目录（此前只隔离了 `BOBODAN_HOME`）。默认工作区就是当前目录，所以任何没有显式传 workspace 的 store 都会打开开发者的真实 `.knowledge/bobodan.db`——这已经实际发生过一次：套件静默迁移了真实库的结构。对照实验确认因果：去掉这行 pin，跑完全量后真实库会重新出现；加回后全量运行对该路径没有任何连接，并且在把真实库放回原位后，跑前跑后的文件哈希与 mtime 完全一致。新增 `tests/test_isolation.py` 钉住这条边界。（第 3 批发现这层 pin 只盖住走环境变量的路径；`learning/path.py` 的 `workspace="."` 与 `cli/repl.py` 的 `os.getcwd()` 仍会打开真实库，已随第 3 批修掉并补上会话结束的 tripwire。）
- **文档体系收敛（2026-09-03）**：新增统一路线图 `docs/ROADMAP.md`——合并 openhanako 前置路线（R0-R3）、参考项目调研报告借鉴清单（DeepTutor D1-D13 / OpenMAIC O1-O10 / qiaomu Q1-Q10 / 前端 F1-F18）、整机优化计划遗留、2026-08-01 体验审查未决项与 P5G.2/3 剩余，按 W1 学习闭环 / W2 检索与 RAG / W3 前端第二批 / W4 运行时底座 / W5 发布通道五个工作流组织，附执行波次、已拍板决策与合并后的明确不做清单。7 份已完成或被取代的文档（任务书 / 审查报告 / 旧路线 / 知识地图设计）移入 `docs/archive/`；`docs/README.md` 重写为 6 份活跃文档索引；`rag_design.md` 顶部加 embedding 决策更新横幅（用户自配 API 取代 Ollama 假设，详见调研报告第十章）。调研报告保留为活文档（ROADMAP 条目的论据与源码索引）。
- **R0 质量与调试基建（2026-08-28，分支 `feat/r0-quality-infra`，依据 `docs/PRE_DESKTOP_ROADMAP.md`）**：借鉴 openhanako v0.450 的测试与调试实践，正面解决"桌面版前难调试难测试"。
  - **测试策略成文**（`tests/README.md`）：风险驱动分层 + keep/delete 规则（删锁文案、删 mock 私有字段、删环境依赖的间歇失败用例），LLM 测试必须走单缝。
  - **ScriptedProvider**（`tests/llm_fake.py`）：唯一认可的 LLM 测试替身——脚本化文本/工具调用/错误注入、分块流式、请求全量记录；`scripted_provider` fixture 统一注入，替代散装 FakeProvider。
  - **e2e 收缩**：删除 13 条分支前就长期失败的浏览器用例（业务契约已由 Python 路由测试等价覆盖）；新增 3 条三视口冒烟（启动与主路由渲染 / composer 与斜杠面板 / 设置打开与 Esc 关闭）；移动端仿真无法点击 100dvh 设置页下半区的用例按政策跳过（桌面/窄屏覆盖）。结果：45 用例从 12 条永久失败变为全绿。
  - **一键开发栈**（`scripts/dev.py`）：随机空闲端口 + 健康轮询 + `~/.bobodan-dev` 隔离数据目录（`--fresh` 可清空）+ `server-info.json` 握手文件 + `BOBODAN_API_URL` 注入 Vite 代理 + 双进程联动回收；真实用户数据零接触。
  - **`agent.py diagnose`**：只读脱敏健康报告（运行时/供应商目录不含密钥/资料库注册表与存储计数/日志指针），各节失败软着陆，可直接粘贴到 issue；3 个测试钉住脱敏与容错契约。
  - **持久化登记册**（`core/persistence_registry.py` + tripwire 测试）：21 个存储全部登记 owner/scope/rebuildable/purpose；源码出现未登记存储文件名即测试失败，登记项失去引用同样失败。
  - 验证：全量 pytest 见下方记录、vitest/lint/build 通过、`dev.py` 与 `diagnose` 真实启动冒烟通过。
- **前端体验与动效体系优化轮（2026-08-27，分支 `refactor/perf-2026-08`）**：全面审查后的交互层收敛，六个提交。
  - **弹窗基元**：新增 `ui/Modal`——统一 backdrop 与 220ms 入场、模块级层级栈（嵌套管理器只关最顶层，修复供应商/记忆管理器叠加在设置页时一次 Esc 两层同关的竞态）、焦点陷阱与焦点归还；`ConfirmDialog + useConfirm()` 替换全部 10 处原生 `window.confirm` 破坏性确认。
  - **动效收敛**：时长归一到 `--dur-fast/base/slow` 三档 token、缓动只剩两条 token 曲线；去重 `spin` 关键帧；删除零消费的 Collapse/SlideIn/AnimatedList；Bobodan 处理状态图不再按状态重挂载（预加载四态图消除闪烁）；mention 面板与其余弹出菜单共用 menu-enter 入场。
  - **减少动效对齐 OS 语义**：应用内开关现在施加与 `prefers-reduced-motion` 一致的全局停用规则；图谱相机/hover 补间与流式打字机改为实时读取 `lib/motion.ts`（原先只在挂载时快照一次）。
  - **品牌形象接入**：失败回答换 curious 表情；Knowledge Map 加载、复习/笔记/阅读器加载态统一为品牌插画变体；图标型空状态补齐品牌状态图；笔记页复用共享 EmptyState 且个人知识管理浮层不再双重遮罩。Chat 欢迎页曾改用 hero 插图，**经用户对比后确认保留原版**（方形形象 + 居中标题，hero 图自带底色与页面纸色不一致、浮层卡片显杂乱），已回退并在品牌 README 标注 hero 暂不接线。
  - **加载平滑**：知识地图改为「实例创建一次 + 数据增量同步」——候选审查、概念编辑不再重建 WebGL 渲染器、重放入场动画和相机复位；Library/阅读页切换文档保留旧正文淡出（stale-while-revalidate），不再白屏闪转圈；Practice「问 AI」接入 StreamBuffer 打字机缓冲并支持 Markdown 渲染。
  - **可发现性**：Ctrl/Cmd+N 新对话真实生效（此前按钮上有提示但无绑定）；阅读页补 `[` / `]` 章节导轨键；顶栏新增键盘快捷键参考弹窗（只列真实存在的绑定）。
  - **掌握度去占位**：知识地图侧栏「掌握状态」接通既有 `/api/learning/progress?concept=` 接口，显示真实状态/评分/下次复习（此前硬编码「尚未练习」）。经核实，「已停止」标记与孤儿提取运行启动扫描此前已实现。
  - DESIGN.md §11 同步三档动效 token 与减动效语义。验证：Vitest 46 passed、lint/tsc 与生产构建通过、Python 全量 1365 passed；Playwright desktop 项目与本分支起点基线**完全持平**（12 处失败均为分支前已存在的陈旧/环境用例，hero 初版曾挤出新对话页 composer 导致 slash-palette 用例失败，限高后通过）。SSE 对外契约与证据门禁行为不变。
- **后端并发模型优化（2026-08-27，分支 `refactor/perf-2026-08`）**：聊天 SSE 流改为在专用受限通道（CapacityLimiter 16）上泵送，不再占用 FastAPI 共享请求线程池（默认 40 线程）——此前每条活跃对话流会独占一个池线程直至该轮结束，极端情况下会饿死普通端点；对外 SSE 事件契约不变。`/api/kb/import` 的文件解析/提取工作下沉到线程池，不再阻塞事件循环（该端点此前是唯一 async def 路由却在循环内做阻塞解析）。验证：Python `1365 passed`（1362 基线 → +3 泵流单测）、`test_web_backend` 全量回归零失败。
- **Library 重构后续打磨（2026-08-27）**：编辑器向资料库全库开放——`course_document` 与 `obsidian_note` 资料也可在列表页/阅读页编辑（原始资料 truth source 原则不变，仍走检查点 + 最近 10 版 + 哈希冲突三选项）；系统区域保持只读（`.knowledge` 运行时索引、`.bobodan/checkpoints` 版本快照、`.bobodan/archive` 归档），旧工作区的 `.bobodan/sources` 与 `managed-vault` 用户内容不受影响。知识地图工具栏新增「添加概念 / 添加关系」弹窗（用户手写即视为已审查，`evidence_level='user'` 边界不变）。修复章节导轨关闭后被悬停热区立即重新弹出的问题；阅读 tab 栏改为吸顶。验证：Python `1362 passed`（1356 基线 → +6 回归测试）、Vitest `46 passed`、前端 lint 与生产构建通过。
- **完成 Library 重构 + 图谱编辑（TASKS_LIBRARY_REWORK v1.0，2026-08-13）**：分支 `feat/library-rework`，按任务书落地 4 个任务。
  - **任务 1 布局方案 A**：Library 拆为列表页 `/library` + 阅读页 `/library/read/:id`（`ReaderPage.tsx`）；阅读页顶部细条（返回 / 上一份下一份 / 编辑 / 概念提取）、正文居中限宽、返回列表恢复滚动位置（localStorage）、键盘导航（Esc / Shift+J/K）、移动端天然兼容。
  - **任务 2 openhanako 三件套**：多文档 tab（点击切换 / 双击关闭 / 滚轮横滑，每 tab 保留滚动位置，`readerTabsStore.ts`）；章节导轨（右缘 64px 悬停热区弹出 heading 列表，点击跳转 + 高亮）；选中文字浮出动作（带到对话 / 基于此出题）。
  - **任务 3 编辑入口 + 分栏编辑器**：列表行内 + 阅读页顶部「编辑」按钮（md/txt/markdown）；`DocumentEditor.tsx` 升级为分栏编辑预览——编辑/预览并排、60fps 双向滚动同步（rAF 节流）、`Ctrl+\` 切换分栏/纯编辑、可拖拽分栏分隔线，保留检查点 / 10 版历史 / 回滚 / 哈希冲突三选项。
  - **任务 4 图谱编辑**：`graph/concept_store.py` 新增 `update_concept`（部分更新 + 改名唯一冲突校验）与 `create_relationship`（自环 / 重复 / 非法类型 / 缺失概念全拒绝，`evidence_level='user'`）；`web/backend/routers/kb.py` 新增 `PATCH /api/kb/concepts/{id}`、`POST/DELETE /api/kb/relationships`；`ConceptSidebar.tsx` 加编辑概念 / 删除关系 / 添加关系，写入后经 `uiStore.graphRevision` 即时刷新图谱。
  - 验证：Python `1356 passed`（基线 1343 → +13，零回归）、Vitest `46 passed`、前端 lint 与生产构建通过。
- **完成整机优化计划（AGENT_OPTIMIZATION_PLAN v1.1，2026-08-13）**：按计划书依赖顺序落地 A 系列（发动机）、B 系列（车厢）、LB-1（资料协作）全部 10 个阶段核心，14 个 commit，分支 `feat/optimization-plan`（已推送 origin）。
  - **A 系列（发动机，按 Pi 图纸）**：AG-0 外围地基——`core/event_bus.py` 过滤事件总线、`core/agent_events.py` 事件四层收敛、`web/backend/sse.py` SSE 流身份（streamId + seq + 重放 ring buffer）、`core/stream_guard.py` 流消毒守卫、`core/runtime/` 适配层门面；AG-2 循环增强——`core/hooks.py` 两层钩子、证据门禁/工具白名单沉淀为 before_tool 门禁、只读工具并行执行、工具执行去重；AG-3 记忆与压缩——`core/memory_injector.py` before_turn 注入（1500 token 预算）、`core/prompt_layout.py` KV cache 分界线、`core/session_compactor.py` checkpoint 纯投影压缩。
  - **B 系列（车厢，按 OpenHanako 经验）**：FE-1 前端地基——`src/ui/` selector 归一化 / 动画原语 / 块级 ErrorBoundary / CSS Token / `@/` 别名；FE-2 流式体验——`streamBuffer.ts` 30fps 节流 + 自适应文本节流、`scrollEasing.ts` + `useStickyBottomScroll.ts` 贴底滚动、SSE seq 去重；FE-3 过程披露——`processFold.ts` + `ProcessFoldBlock.tsx` 过程折叠；FE-4 页面联动与图谱动效——FadeIn 页面过渡、知识地图概念→Chat 上下文跳转、学习范围共享，图谱入场 / hover 过渡 / 聚焦度数行走 / 拖拽反馈 / 搜索 spotlight / 力参数可调 + prefers-reduced-motion 降级（维持 sigma.js + graphology + forceAtlas2）。
  - **LB-1 资料协作**：LB-1.1 用户编辑——`service/document_edit_service.py` Markdown 优先 + 检查点 + 最近 10 版 + Obsidian 双开哈希冲突三选项 + 编辑后重索引/Wiki needs_update，`DocumentEditor.tsx` 编辑器 UI；LB-1.2 AI 协作编辑——`service/document_proposal_service.py` 提案→确认→应用→撤销（复用 Wiki 检查点机制），`DocumentProposalCard.tsx` 提案卡。
  - **AG-1 会话革命（条件执行）**：P5G 未验收（P5G.2 Electron / P5G.3 支撑页面待办）→ 仅交付设计 + `core/session_jsonl.py` JSONL 迁移路径 + 测试，未切换线上默认 `.json` 会话格式。
  - 验证：Python `1343 passed`（基线 1233 → +110，零回归）、Vitest `46 passed`、前端 lint 与生产构建通过；SSE 对外事件名不变、证据门禁行为不变。
- **前端视觉统一与沉浸式笔记编辑器（2026-08-13）**：新建主题化 `DropdownSelect` 组件（原生 select 下拉面板无法跟随暖纸色主题），全面替换 composer、设置页、Library、知识地图、记忆管理、供应商管理、候选审查的所有原生下拉；`/notes` 写笔记从填表改为沉浸式 Markdown 编辑（正文为主角、第一行 `#` 自动提取标题、编辑/预览切换、Ctrl+Enter 保存、关联资料折叠）；统一视觉细节——补 `--sage-deep`/`--ink-soft`/`--accent`/`--shadow-dialog` token、替换 13 处散落硬编码绿色、统一弹窗阴影、统一圆角（composer/run-summary 10→8、candidate-panel 12→8）、补 send-button 与 5 个 tab 组缺失的 hover 态、复选框主题化。布局和配色主基调不变。验证：Vitest `19 passed`、前端 lint 与构建通过（纯前端改动）。
- **Chat 体验与个人笔记统一（2026-08-13）**：① 概念关系卡片不再重复/空渲染——图谱空结果不输出卡片、一轮多次查询只保留第一张、收到卡片不自动弹右侧面板（改为卡片内按钮按需打开）；② 侧栏新增一级「笔记」导航 → `/notes` 页面，个人笔记统一到个人知识（Wiki note 停止新建、隐藏「个人笔记」Tab、已有笔记原地只读保留）；③ 笔记 ↔ 资料库双向轻联动——个人知识新增 `references` 字段，写笔记可关联资料、资料阅读器显示相关笔记（笔记永不进入概念图谱，只做关联展示）；④ 流式观感修复——前端加渐进显示缓冲，证据门禁回放 token 时呈现打字机效果而非整段弹出。验证：Python `1233 passed`、Vitest `19 passed`、前端 lint 与构建通过。
- **完成 P5G.4 模型供应商管理（Provider Catalog）**：新增 `providers/catalog.py`，供应商配置迁移到 `~/.bobodan/provider.json`（API key 可在设置页 UI 填写，不再需要手改 `config.yaml` / `.env`；首次启动自动迁移旧配置，key 留空时回退环境变量，零断供过渡）。供应商下挂多模型，聊天框与任务路由（主题发现 / 页面撰写）升级为「供应商 → 模型」两级选择（`provider::model` 引用，旧纯供应商格式兼容）。设置页新增「管理供应商」：预设模板（含免 key 的本地 Ollama）+ 完全自定义（OpenAI 兼容协议）、远程 `GET /models` 自动拉取模型列表、手输兜底、测试连接、删除（密钥脱敏返回，编辑留空保持原 key）。验证：Python `1231 passed`、Vitest `19 passed`、前端 lint 与生产构建通过、真实启动冒烟（settings / 新增 / 删除 / 测试连接 / 模型级 chat 引用）通过。
- **完成 P5G.1 单进程本地 Web**：新增 `python agent.py web`，一条命令启动完整产品（FastAPI 托管 React 生产构建 + SPA 深链接回退 + `/api/*` 不被拦截）；默认 `127.0.0.1`、端口被占用自动向后查找、启动后自动打开浏览器；生产模式应用数据位于 `~/.bobodan`、日志写入 `%LOCALAPPDATA%\Bobodan\logs\web.log`（`--dev` 保持开发行为）；启动失败给出端口/配置/构建三类可操作提示。验证：Python `1212 passed`、Vitest `19 passed`、生产构建与真实启动冒烟通过。
- **桌面端资料进库设计落地（2026-08-12）**：应用数据统一 `~/.bobodan` 点目录；资料库根目录全格式扫描（PDF/DOCX/PPTX 丢根目录或任意子目录即可被索引，`raw/` 旧 source 保持稳定，`wiki/` 等内部结构不索引）；新增 `agent.py library init --default` 一键创建 `Documents\Bobodan 资料库`；切片句子边界软切（句号 → 分号 → 逗号回退，中文长句不再腰斩）+ 阅读器相邻切片去重标题。设计决策全文见 `docs/PROJECT_GUIDE.md` P5E.1 小节。验证：Python `1217 passed`、Vitest `19 passed`、前端构建通过。
- **完成 2026-07-26 项目审查整改**：修复审查报告中的 B1–B9 正确性问题，并继续沿“单一正常运行真相源、旧数据只做显式迁移”的原则收敛后端与前端。
- 正常运行时退役旧 Markdown Memory、JSON sparse/local RAG、JSON / Neo4j 图谱和 `WikiCompiler`；Wiki 保留为高级维护与历史整理，不再作为默认 RAG 证据。
- 本地资料检索统一到 SQLite `knowledge.db`、中文 CJK 2-gram FTS5 与可选 Qdrant；修正混合检索排序，增加有界缓存并收紧并发数据库访问。
- 知识地图统一使用已审查的 `concept_graph.db`。旧 `graph_store.json` 只在设置页惰性检测，经预览、用户确认、写后校验和 SHA-256 记录后归档。
- 个人知识统一使用结构化 SQLite。旧 `.bobodan/memory/*.md` 与 daily 文件仅提供只读预览和显式迁移，不再写入或注入 Agent Prompt。
- Provider 增加类型化错误与统一重试边界；MiniMax 流式响应加入拒答检测，并禁止已经输出首个 chunk 后从头重试造成重复回答。
- 学习调度改为保守 SM-2，`mastered` 项仍会进入后续复习；题目生成增加错题变体，批改解析失败不再污染掌握度和错题本。
- 前端路由使用懒加载与应用级错误边界；拆分 Chat 流归约、命令路由、artifact 和跨页状态，修复上下文竞态、错误帧处理与旧数据迁移交互。
- 刷新根 README、文档索引与审查记录，使产品说明与当前运行时一致。
- 验证结果：Python `1160 passed`（2 条既有 warning），前端 lint 与生产构建通过，Vitest `19 passed`，`git diff --check` 通过。

- **后续路线调整**: 下一阶段改为 P5E“用户主动触发的 LLM Wiki”。资料导入只建立原文索引，用户要求整理后先生成变更计划，确认后才写入可互链、可回到原文、可撤销的 Wiki；可信联网顺延到 P5F，发布收尾顺延到 P5G。
- **侧栏品牌头像**: 左上角恢复使用正式主头像 `bobodan-avatar-64.png`，不再把低频 `friendly` 表情图作为固定品牌入口。
- **Docs cleanup**: 新增 `docs/README.md` 作为文档索引，新增 `docs/DESIGN.md` 作为长期视觉设计参考；将 `docs/OPENAI_AGENT_CODEX_REFERENCE_FOR_BOBODAN.md` 纳入当前工程边界参考；将已实现或历史详细设计移入 `docs/archive/`，当前执行入口收敛到 `docs/NEXT_STEPS_EXECUTION_PLAN.md`。
- **REPL UI 改进**: thinking 动效增加实时计时器（`⠋ thinking · 3.2s`）。工具调用显示改为 Claude Code 风格（`▸ tool_name(args)` → `✓ preview`），消除多余空白行。thinking 动效在工具执行期间保持可见。
### 修复
- **A4 止血 · P0-4 静态托管路径穿越（2026-09-14）**：`web/backend/static.py::spa_fallback` 直接 `dist / full_path` 后交给 `FileResponse`。Windows 上带盘符的绝对路径会**整体替换**左侧（`dist / "C:/Windows/win.ini"` 就是那个文件），百分号编码的 `..%2F` 则在所有平台越界。
  - 复现：`tests/test_static_hosting.py` 新增两条用例（百分号编码穿越、Windows 盘符绝对路径），断言越界必须 404 且响应体不含 canary 文件内容。**修前失败信号**：`assert 200 == 404`；另外单独探针确认两种请求都返回 `200` 且响应体就是 canary 原文（不是回退到 SPA index）。
  - 修法：candidate 先 `resolve()`，必须 `is_relative_to(dist)` 才允许返回；越界一律 404，不再回退 SPA index（避免用 200 掩护探测）。
- **A4 止血 · P0-5 + P0-6 工具沙箱边界与写保护（2026-09-14）**：`tools/base.py::execute_tool` 原来是 `call_args = dict(args)` 加 `setdefault("workspace", ...)`，**模型传的 `workspace` 会赢**；同一个函数里 `document_ids` 却用了覆盖写法，说明作者知道要覆盖、只是没把沙箱根归到同一类。配套两处：`_is_denied_path` 只比对 basename（`.git/config`、`.knowledge/knowledge.db`、`.session/<id>.json` 因此读写都畅通），`_is_within_workspace` 用大小写敏感的 `startswith`（Windows 下 `C:\Foo` 与 `c:\foo` 是同一文件）。
  - 复现：`tests/test_tool_base.py` 三条（模型自带的 `workspace` 不得生效、未声明参数必须被丢弃、`chat_session_id` 与 `search_provider` 等会话身份不得由模型指定）+ `tests/test_file_ops.py` 两条（内部目录不可读、不可写），另加一条**反向测试**（工作区本身位于名为 `venv` 的目录下时仍要能读）。**修前失败信号**：`assert "/tmp/project:x" == "/attacker:x"`、以及 `write_file` 对 `.git/config` 返回 ok=True 并真的把文件写了出来。
  - 修法：按函数签名做参数白名单（接受 `**kwargs` 的工具除外）；所有会话作用域参数改为**赋值而非 setdefault**（含 `cwd`、`workspace`、`document_ids`、`web_research_id`、`search_provider`、`jina_fallback`、`research_session_id`、`chat_session_id`）；拒绝列表改为按**工作区之下的路径段**匹配并忽略大小写，`_is_within_workspace` 走 `os.path.normcase`；trace 增加按**内容形态**脱敏（`Bearer` / `Basic` / `token=` / `api_key` / `password` 以及 `sk-`、`ghp_`、`xox`、`AIza` 形态），覆盖 `args`、`content`、`result_summary`、`error` 四处，而不只是字段名匹配。
- **A4 止血 · P0-7 中文 token 估算（2026-09-14）**：`core/session_compactor.py` 与 `core/memory_injector.py` 各有一份 `CHARS_PER_TOKEN = 4`（中文按 1 字≈0.25 token 估）。实测（本项目语料 + cl100k_base）：25 个中文字 = 29 token、54 个 ASCII 字符 = 9 token。低估的方向最危险——`should_compact` 永不触发、1500 的名义记忆预算实际能塞进数千 token，最终以 provider 400 收场。
  - 复现：两个测试文件各加一条 `test_estimate_tokens_counts_cjk_conservatively`。**修前失败信号**：`AssertionError: (7, 25)`——25 个中文字被估成 7 个 token。
  - 修法：新增 `core/token_budget.py` 作为唯一估算器（宽字符 ≥ `0x2E80` 记 1.2/字、其余保留历史 1/4）；压缩器与注入器改为复用它，注入器的预算核算从「字符数 × 4」改成真正的 token 计数。
  - 注意：估算修正后 `memory_injector` 的 1500 预算**第一次真的生效**（此前实际放行约 4 倍内容）。按约定本轮不动这个数字，先让它真实生效。
- **A4 止血 · P0-11 删概念 500（2026-09-14）**：`relationships.from_id/to_id` 引用 `concepts(concept_id)` 却没有 `ON DELETE` 动作，而 `PRAGMA foreign_keys` 是开的（实测确认为 1），于是**只要这个概念在关系里出现过**（确认过候选、手建过关系必然如此）删除就会抛 `FOREIGN KEY constraint failed`，`service/concept_service.py::delete_concept` 没有 try/except，用户侧就是 500——概念删不掉。有意思的是同一张 schema 里 `evidence.rel_id` 写了 `ON DELETE CASCADE`，说明作者会用级联，只是漏了这两处。
  - 复现：`tests/test_concept_store.py` 新增两条（删带关系的概念、删概念同时清理布局位置）。**修前失败信号**：`sqlite3.IntegrityError: FOREIGN KEY constraint failed`（用原始 SQL 探针复现，确认 `foreign_keys = 1`）。
  - 修法：在 `ConceptStore.delete_concept` 里一个事务内先删关系（其 evidence 由已有的 `rel_id` 级联带走）、再删无外键的 `concept_positions`、最后删概念。放在 store 而不是 service，是为了让 API、Wiki 流程与测试走同一条路径。
- **A4 止血 · P1-21 grep chunk_id 跨进程不稳定（2026-09-14）**：`rag/grep_retriever.py::_matches_to_hits` 用 Python 内置 `hash()` 生成 `grep:<doc>:<8hex>`。`hash()` 对字符串按进程随机加盐，**重启后同一段原文的 id 就变了**，而错题变式正是按 `chunk_id` 回原文定位——表现为「练习里引用得到、重启后找不到」。
  - 复现：新增 `tests/test_grep_chunk_id.py`，用两个不同 `PYTHONHASHSEED` 的子进程各算一次 id 并比对。**修前失败信号**：`grep:doc-1:968c90e5 != grep:doc-1:65b66b45`。
  - 修法：改用 `rag/sqlite_store.py` 里已有的 `_stable_hash`（sha256 前 16 位），id 形态变为 `grep:<doc>:<16hex>`。
- **A4 止血 · P1-28 `/kb reset` 与 manifest 自相矛盾（2026-09-14）**：`reset` 删了 `knowledge.db` / `bobodan.db` / `sync_state.json` / `import_report.json` / qdrant 目录，唯独没删 `manifest.json`。而 `build_library_summary` 正是从 manifest 读文档列表，于是 reset 之后**「资料总数」还显示 1（连同文件名与 last_sync），而 `list_documents` 是空的**——两个接口互相打脸。
  - 复现：`tests/test_kb_service.py` 新增一条：写入带一份文档的 manifest，确认 summary 是 1，执行 reset，再确认 summary 归零。**修前失败信号**：`assert 1 == 0`，且 summary 里仍带着 `courses=[CourseSummary(file_count=1)]` 与旧的 `last_sync`。
  - 修法：把 `manifest.json` 加进 reset 的清理列表。它是派生索引（下次 sync 会重建），与已清理的 `knowledge.db` 同级；用户的研究记录（`research.db`）不在清理范围，这是有意的。
- **A4 止血 · P0-13 + P1-8 原子写地基（2026-09-14）**：`raw/` 是「不可变证据层」，会话文件是对话的唯一记录，但两处都是裸 `open(path, "w")`：崩溃、磁盘写满或并发读取都可能看到半截文件，两个写者还会互相覆盖。项目里偏好设置与资料库注册表**早已**用 temp+replace（`wiki.reliability.atomic_text`），只有这两处没跟上。
  - 复现：新增 `tests/test_atomic_io.py` 三条——①写原文时 `os.replace` 抛错，原文必须保持不变且不留临时文件；②会话保存失败时磁盘上的快照必须还是上一版且仍可解析；③跨进程互斥（子进程持锁，父进程 0.5s 内必须 `LockTimeout`）。**修前失败信号**：①`assert '新内容' == '原始内容'`（原文被摧毁）；②`after != before`；③`ModuleNotFoundError: core.atomic_io`。
  - 修法：新增 `core/atomic_io.py`——同目录 `NamedTemporaryFile` 写入后 `flush + fsync`，`os.replace`（对 Windows 的 `PermissionError` 做指数退避重试，因为读/杀毒/索引器会短暂占用目标），失败时清理临时文件并保持原文件不动；目录 fsync（非 Windows）；`path_lock` 做进程内每路径串行；`workspace_write_lock` 用 `msvcrt`/`fcntl` 双平台实现跨进程互斥（**参照项目在 Windows 上 `fcntl` 缺失即静默无锁，是明确要避开的坑**）。会话保存与原文/版本 manifest 改写为走它。
  - 留待：`workspace_write_lock` 目前只有测试在用，接入 sync 等多文件写者属于 P0-15 那一项。
- **A4 止血 · P0-12 删除确认（2026-09-14）**：`sync_sources` 的删除判定是 `deleted_sources = [s for s in old_state if s not in new_state]`——**只要这一轮扫不到就判删除**。而扫描用的 `os.walk` 没有 `onerror`，目录读不到时静默跳过；网络盘/外接盘瞬断、权限变化、符号链接失效都会让文件「消失」。后果是级联删掉 `documents`/`chunks`/`directory_entries`、清掉 Qdrant 向量、把概念证据标 stale，而概念证据的修复又依赖 excerpt 精确匹配——匹配不上就永久 stale。
  - 复现：新增 `tests/test_sync_deletion.py` 五条：①扫描器遇到「列得出但读不了」的文件必须记录错误（注入一个幽灵文件名）；②同一来源必须**连续两轮**缺失才删除；③扫描报错时完全不删除（保留计数）；④重新可见的来源清掉待删计数；⑤vault 扫描同样要报告不可读文件。**修前失败信号**：`ImportError: cannot import name _resolve_deletions`（机制不存在），以及一次性缺失即进入删除清单。
  - 修法：抽出纯函数 `_resolve_deletions(old_state, new_state, previous_missing, scan_failed)`——连续 `DELETION_CONFIRMATIONS = 2` 轮缺失才判删，`scan_failed` 为真时一个都不删且不推进计数；计数随 `sync_state.json` 持久化（顺带改走原子写）；`_scan_course_files` / `_scan_library_root` / `scan_vault` 三个扫描器都接 `onerror` 与逐文件 `OSError`，把「列得出但读不了」记入错误而不是让文件凭空消失；扫描错误会进 sync 摘要的 `errors`，用户能看到「扫描不完整」。
- **A4 止血 · P0-15 Qdrant 双开（2026-09-14）**：qdrant-client 的 local 模式会对目录加锁，而 `rag/retriever.py::_retrieval_pipeline` 长期持有一个 client 的同时，`obsidian/sync.py` 又自建了第二个——同一个路径两个 client。表现为**偶发**的「检索不可用 / 导入失败」，最难排查的那类。`clear_retrieval_cache` 只在少数入口被调用，`sync` 不调它。
  - 复现：新增 `tests/test_qdrant_lifecycle.py` 四条：①同一 workspace 两次取必须拿到同一个对象；②不同 workspace 必须不同；③检索管线持有的必须是共享注册表里那一个（真实构造管线断言对象同一性）；④关闭后注册表必须真的丢弃它（否则 reset 时目录仍被锁、`rmtree` 会失败）。**修前失败信号**：`ImportError: cannot import name shared_qdrant_store`。
  - 修法：`rag/qdrant_store.py` 新增按 client 身份（local 路径 / server url+collection）去重的共享注册表，`shared_qdrant_store()` 与 `close_shared_qdrant_store()` 是唯一入口；检索管线与 `sync` 都改用它；`_close_pipeline`（LRU 淘汰路径）**不再关闭**共享 client，避免把别人正在用的连接关掉；`clear_retrieval_cache(workspace)` 负责关闭并注销，因为 reset 之后要删掉那个目录。
- **A4 止血 · P1-14 读改写串行化（2026-09-14）**：`service/preference_service.py::patch` 是「读 revision → 校验 → 写」，中间没有任何锁。两个并发请求都读到同一个 revision、都通过校验、都被告知写入成功，**其中一个改动静默消失**。另一类是 SQLite 侧：Python sqlite3 默认延迟开启事务，读改写会在提交时才拿写锁，输的一方拿到 `SQLITE_BUSY_SNAPSHOT`——活儿干完了才失败。
  - 复现：新增 `tests/test_preference_lost_update.py`（两个线程用 barrier 保证都读到同一 revision 再写）。**修前失败信号**：`AssertionError: ['ok', 'ok']`——两个调用者都收到成功。另加 `tests/test_db_transactions.py` 两条，用两个连接实测 `BEGIN IMMEDIATE` 在**开始时**就拿写锁（对手立刻 `OperationalError`），而 `BEGIN DEFERRED` 要到 INSERT 才失败。
  - 修法：`patch` 的读→校验→写收进 `path_lock` 临界区（并复用它下已有的 `_atomic_json`，顺带拿到 fsync 与 Windows 重试）；`core/db.py` 新增 `begin_immediate()` 原语（事务已开时幂等，避免 "transaction within a transaction"），`graph/concept_store.upsert_concept` 的名称查重与写入改为同一写事务——此前两个并发 upsert 会都通过查重，输的一方撞唯一索引而不是得到 409。
- **阅读器章节目录关不掉（2026-09-14，用户反馈）**：点章节导轨的 ✕ 之后它会立刻弹回来。原因是关闭动作会在指针底下挂出 64px 的触发带（`.chapter-rail-zone`），而浏览器在光标底下的元素变化时会重算 hover 并补发 `mouseenter`——于是这次的 `setRailOpen(false)` 被它自己引发的事件撤销了，注释里「关闭时触发带不存在」的假设在 Blink 上不成立。改为记住关闭发生的位置，来自**同一坐标**（±8px）的那次 hover 直接忽略，指针离开触发带即解除。回归测试 `e2e/app.spec.ts`「the chapter rail dismisses and does not re-open under the same pointer」先复现（旧代码报 `Expected: 0, Received: 1`）再验证修复，同时钉住「离开后再靠近仍然能唤出」这条正向行为。
- Wiki 默认区分“知识页 / 资料索引 / 个人笔记”，资料索引不再与概念页混排或显示为 `obsidian_note`；新生成的资料索引限制为短摘要、学习地图和关键结论，不再逐章复刻原文，已有页面可通过“AI 更新当前页”生成需确认的更新计划。耗时与 Token 估算改用同 Provider、同模型的真实请求样本并显示可信度，完成计划展示本轮实际用量、Provider 缓存和 Bobodan 本地缓存。
- Wiki 取消现在会在每次模型请求前重新检查停止标记，不再继续执行同一批次内尚未发出的请求；刷新过的旧会话即使 artifact 与 plan 状态不一致，也会继续轮询并收敛为“已取消”。缺少 `summary / changes` 的中断记录按空计划安全显示，不再导致整个 Chat 页面白屏。
- Wiki 资料摘要页和同名概念页改用类型感知的规范 ID，不再在 Library 中相互折叠；资料摘要、实体、概念、综合分析和问题页均显示正确类型。
- Wiki 计划写入失败后会把最新校验状态持久化回 Chat artifact；刷新、切换会话或重启后仍能继续选择“保留原页”或“补全后重新规划”。
- **Wiki 暂停恢复与状态动效修正**: Wiki 页面因异常缩减保护而暂停时，不再暴露“隔离区”内部术语；计划卡显示具体页面、可读原因和“保留原页继续 / 补全后重新规划”操作。同一校验错误不再重复累积，保留原页路径会安全写入其余页面。Chat 运行状态移除容易被理解为进度条的伸缩横线，改为三点墨迹错峰动效。
- **P5F 练习与设置可用性修正**: 判断题改为明确的“正确 / 错误”选项并显示中文题型与难度；Bobodan 运行状态保持在回答正文流内；减少动效不再破坏开关圆点位置，Skills 说明不再挤压开关。
- 修复新会话练习卡的跳转竞态：用户快速点击“开始练习”后，延迟的 Chat 会话地址更新不会再把页面拉回对话。
- **P5F 自主联网与练习闭环修正**: 联网权限升级为“每次询问 / 模型自动”双模式，默认保持询问；自动模式下模型可调用受限 `web_research`，程序按来源类型、排名和域名去重自动读取最多 3 个来源。
- Practice 生成增加资料标题模糊匹配、选中资料章节回退和一次 LLM JSON 修复重试；`langchian` 等拼写问题可解析为对应本地资料，资料不足时按联网权限继续，而不是直接显示通用错误。
- `question_generate` 改为返回可持久化的“练习已就绪”卡片；点击后幂等创建 Practice session 并进入一题一卡页面，不再把完整题目堆在 Chat 正文。
- Chat 处理状态改为正文流内的 Bobodan `thinking / reading / writing / ready` 图片状态；只展示工具、资料和任务进度，不展示模型原始思维链。
- 用户偏好升级为 schema v3；验证：Python `1102 passed`、Vitest `5 passed`、TypeScript 与生产构建通过、Playwright 多视口 `57 passed`。

- **Review 状态字体与滚动条**: `到期 / 错题 / 薄弱点` 使用 Luo 短标签强调；全局滚动条改为透明轨道与暖灰细滑块，并修复右侧资料名称撑宽面板造成的横向滚动条。
- **复习出题错误继承当前资料范围**: Review 现在按知识点关联并复用历史题目 ID，不再把用户当前选择的无关资料范围套到历史复习项上；只有没有历史题时才回退到重新生成，避免无资料报错和检索跑偏。
- **Trace per-run 文件碰撞**: `TraceWriter` 文件名增加微秒时间戳和短 run suffix，同一 session 在同一秒内连续 run 不再写入同一个 JSONL；`list_traces()` 兼容旧秒级文件名。
- **Workflow 手动掌握度联动**: `ReviewScheduler.mark_manual(..., "mastered")` 后会触发 `PlanWorkflowTracker.check_plan_completion()`，手动标记已掌握后今日任务和计划状态会同步更新。
- **LearningStore SQLite 文件锁**: `LearningStore._conn()` 改为真正关闭连接的 context manager，避免 Windows 上临时 workspace 或后续 Web runtime 遇到 `bobodan.db` 文件锁。
### 新增
- **P5E.6 知识地图产品重置**: 将混合 Wiki 重置为以概念关系和原文定位为核心的知识地图。
  - 新增 `graph/concept_store.py`：SQLite 概念图谱后端（concepts、relationships、evidence、concept_candidates、concept_extraction_runs、concept_positions 六表），支持候选审查、位置持久化和图状态快照。
  - 新增 `wiki/extractor.py`：`ConceptExtractor` 从资料内容提取 3–8 个核心概念、≤12 个细节概念及关系；有效关系类型受约束（属于、前置知识、组成部分、对比、应用于、来源于）。
  - 新增 `service/concept_service.py`：`ConceptService` 封装概念图谱业务逻辑，确认候选自动创建概念和关系，reject 支持按天压制，extract_from_document 存储待审查候选。
  - 新增 `web/backend/routers/graph.py`：19 个 REST 端点，覆盖图状态、子图、概念 CRUD、关系 CRUD、候选操作（confirm/reject/label）、提取触发与恢复、位置保存和旧图谱迁移；`/api/graph` 纳入 library-scoped 中间件。
  - 新增 Web 前端知识地图页面：Sigma.js v3 + Graphology WebGL 渲染；三视图（地图 / 目录 / 来源）、概念侧栏（180ms 滑入、Esc 关闭）、候选审查面板（底部 sheet、键盘快捷键 Enter/L/X）；导航新增”知识地图”入口。
  - 新增 `tests/test_concept_store.py`、`tests/test_concept_service.py`：覆盖 DDL、CRUD、候选压制、图状态、子图邻居、服务层验证和 LLM 提取 mock（40+ 用例）。
- **P5E.5 Wiki 易用性、手写编辑与 AI 成本控制**: Library 增加”资料 → 整理 → 审查 → 使用与维护”流程；标准模式默认每次 5 份资料，开始前展示请求、Token 与耗时估算，达到预算后持久化暂停。
  - 新增零模型快速建档、标准整理和深度全库模式，取消与暂停保留精确草稿缓存。
  - “生成修复计划”改为持久化、可应用和可撤销的修复项列表，不再停留在无后续的成功提示。
  - 新增 `wiki_note`、Markdown 编辑/预览、revision 冲突保护及归档恢复；手写内容不会被后续 AI 计划静默覆盖。
  - 偏好升级到 schema v4，新增 Wiki 任务 Provider、预算和默认模式；增加通义、硅基流动、OpenRouter 兼容预设。
  - Provider 响应保留实际 Token、缓存与可用费用 usage，设置中心显示最近 7 / 30 天请求、错误、模型分布和缓存数据；Chat 与 Wiki 共用不保存提示词正文的本地用量账本。
  - 验证：Python `1148 passed`、Vitest `5 passed`、TypeScript 与生产构建通过、Playwright 桌面 / 窄屏 / 移动端 `75 passed`。
- **P5E.4 LLM Wiki 全库编排与覆盖系统**: 将单次选中文档摘要升级为可恢复的全库知识编排。
  - Chat 默认检索整个活动资料库，手动选择只作为优先资料；用户明确切换“仅这些”后才使用严格资料范围。
  - Library 主动作改为“整理未覆盖资料”，显示未整理、部分覆盖、已覆盖和原文变化状态，并支持筛选全选、课程批选与 Shift 连选。
  - Wiki 计划按每批最多 5 份资料读取全部有效章节；每份原始资料保证一个 `wiki_source` 摘要页，概念与实体跨批次规范化去重。
  - 新增持久化 Wiki run、覆盖扫描和恢复接口；长计划在后台生成，Chat 可轮询、取消并在刷新后恢复。
  - 大型现有页面和超长草稿进入拆分候选，不再用短草稿直接覆盖；写入仍需整轮确认并保留检查点。
  - 新增全库优先检索、覆盖重建、后台任务、批次规划及桌面 / 窄屏 / 移动端交互测试。
  - 真实资料验收以 5 份资料生成 5 个摘要页与 5 个知识页，74 个来源定位均有效；写入、覆盖重建、原文高亮跳转和整轮撤销通过。
  - 验证：Python `1135 passed`、Vitest `5 passed`、TypeScript 与生产构建通过、Playwright 多视口 `69 passed`。
- **P5F.1 个人学习知识库**: 在现有 `MemoryService` 上完成确定性学习事件、待确认候选和已确认长期知识三层体系。
  - 新增全局 `personal-knowledge.db` 与资料库内 `bobodan.db` 分层存储；全局偏好可跨资料库使用，课程知识、候选、事件和阅读进度保持资料库隔离。
  - 做题、练习完成、复习、阅读进度和 Chat 完成自动记录为幂等学习事件；阅读器可见满 10 秒后记录打开，进度按 10% 档位更新。
  - Chat 在 90 秒无新消息后通过持久化单并发任务整理最多 3 条候选，支持重启恢复和 `1m → 5m → 30m` 重试；候选确认前不会进入提示词。
  - 新增无写入副作用的 `request_memory_confirmation` 与 Chat 确认卡；Web Agent 不再获得 `memory_save`、`memory_daily_save` 或自动 promotion 权限，秘密信息始终拒绝保存。
  - Chat、Practice 和 Review 只使用已确认知识与确定性掌握度，并显示可展开的“个性化依据”；旧 daily Markdown 保持只读。
  - 设置中心“记忆与数据”新增个人知识管理浮层，支持已确认知识、待确认候选、学习记录和旧记忆迁移，以及搜索、编辑、置顶、删除和 Markdown 导出。
- 验证：Python `1118 passed`、Vitest `5 passed`、TypeScript 与生产构建通过、Playwright 桌面 / 窄屏 / 移动端 `63 passed`。

- **P5F 可信联网资料扩展**: 在本地资料不足时提供用户确认优先、来源可选择、证据可复现的普通网页研究流程。
  - 新增 Tavily / Exa SearchProvider 与 `auto` 有序降级；Exa 通过现有 MCP 客户端连接公共 MCP，不向 Web Agent 开放任意 MCP 或 HTTP 工具。
  - 新增直接网页读取、逐跳 SSRF 校验、响应与上下文上限，以及明确标注的 Jina Reader 后备；用户提供的 URL 可直接进入候选流程。
  - 每个资料库使用独立 `research.db` 保存搜索、候选和不可变证据快照；网页不会自动进入 `raw/`、RAG、Wiki 或个人知识库。
  - Chat 增加联网确认、候选来源和证据 artifact；候选默认不勾选，用户选择 1–4 个来源后才读取正文并继续回答。
  - Composer 增加一次性联网入口和 `/web search`；设置中心增加搜索 Provider、真实连接测试和 Jina 后备开关，偏好 schema 升级为 v2。
  - `SourceRef` 增加域名、访问时间、快照 ID 和读取方式；联网回答与基于回答生成的练习共用 `Attribution(kind="web")`。
  - 验证：Python `1095 passed`、Vitest `5 passed`、TypeScript 与生产构建通过、Playwright 多视口 `57 passed`；Exa 真实连接测试通过。

- **P5E.3 Web UI 系统体验与设置中心**: 在进入联网资料扩展前，补齐本地学习产品的用户偏好、模型与通用交互基础。
  - 新增用户级 `preferences.json`，使用 schema、revision 和原子写入保存助手、用户、阅读、Provider、记忆和 Web Skills 偏好；旧浏览器学习资料可一次性迁移。
  - 新增桌面居中 / 移动全屏设置中心，支持中文搜索、键盘选择、URL 深链接、阅读字体与字号、内容宽度、纸纹、会话密度和减少动效。
  - 新增 Provider 状态与最小连接测试；新会话继承默认 Provider，已有会话持久化自己的 Provider，流式回答期间可停止生成但不能切换模型。
  - Chat Composer 增加回答深度、正文流状态条、`@资料 / @会话`、可恢复引用 chip，以及按用户启用状态过滤的 Slash / Skills 菜单。
  - 新增低风险对话式设置确认卡，只允许回答深度、教学方式、反馈强度和记忆开关；Provider、密钥、权限与安全设置不能通过对话修改。
  - 后端断开时按 `2s → 5s → 10s → 30s` 重试并提供手动重连；正常连接状态不常驻，状态页不暴露密钥、绝对路径、Trace 或原始日志。
  - 更新 `docs/PROJECT_GUIDE.md` 与 `docs/DESIGN.md`，固化设置中心、Composer 三层状态、引用、Provider 和动效规则。
  - 验证：Python `1082 passed`、Vitest `4 passed`、TypeScript 与生产构建通过、Playwright 多视口 `42 passed`。

- **P5E.2 Wiki 可靠性增强**: 在不改变用户确认工作流的前提下，为持续更新和批量 Wiki 操作补齐写入保护、失败恢复与维护检查。
  - 新增 Wiki 写入预检，校验目标路径、页面类型、来源范围和结构文件保护；无效模型输出进入 `.bobodan/wiki/staging/`，不会污染正式 Wiki。
  - 页面更新确定性合并 `sources`、`source_refs`、`tags` 与 `related`，保留关键 frontmatter；多来源正文异常缩减时拒绝写入并恢复检查点。
  - 新增按资料库隔离的持久化 Wiki 任务状态，支持进程重启恢复、失败重试、取消和并发锁定；计划卡可显示 staging 失败原因。
  - `index.md` 改为从磁盘页面确定性重建并移除过期条目；正常生成不再自动归档重复页面。
  - 资料归档前新增 Wiki 依赖影响预览，区分单来源归档候选与多来源待更新页面，不执行静默级联删除。
  - 维护页区分程序结构检查和 AI 语义审查；重复页、矛盾、过时内容与知识缺口只形成候选，实际修复仍需先生成计划并由用户确认。
  - 新增 Wiki 任务、语义维护和资料影响 API，并补齐后端、Vitest、生产构建和 Playwright 多视口覆盖。
  - 验证：Python `1077 passed`、Vitest `3 passed`、TypeScript 与生产构建通过、Playwright 多视口 `39 passed`。

- **P5E.1 文件夹资料库与 LLM Wiki 工作流修正**: 将开发工作区知识库升级为可供不同本地用户使用的便携资料库模型。
  - 一个文件夹对应一个资料库；新增 `BOBODAN_LIBRARY.yaml`、`WIKI_SCHEMA.md`、`raw/`、五类 `wiki/` 页面目录及 `.bobodan/` 本地状态目录。
  - 新增用户级资料库注册表与创建、打开、切换、同步、取消注册 API；Chat、RAG、Quiz、Review、学习进度和会话按资料库请求上下文隔离。
  - 首次导入改为用户先选择资料；若尚无资料库，再在同一流程中确认名称和保存位置，创建后自动继续写入 `raw/inbox/` 并建立原文索引。
  - 原始资料对 AI 保持只读；用户删除改为归档到 `.bobodan/archive/raw/`，关联 Wiki 页面标记为 `needs_update`。
  - Wiki 扩展为资料摘要、实体、概念、综合分析、问题与发现五类页面，统一 frontmatter、表格索引、顶部操作日志和健康检查。
  - `/wiki plan`、重点调整、计划确认、执行结果与撤销状态改为会话 artifact 持久化；刷新、切换会话和重启后可恢复。
  - 旧 Wiki 支持“迁移预览 → 用户确认 → 检查点 → 机械升级”，只补 schema 元数据，不移动文件或改写正文。
  - 新增 `python agent.py library init|sync|list`，并通过 `BOBODAN_HOME` 隔离测试注册表。
  - 资料库页面顶部集中显示当前资料库、切换与管理入口；Chat 与资料库空状态共用“导入资料”流程，左下角不再承担新建资料库操作。
  - 资料库管理新增“接入现有资料文件夹”：先预览可索引资料、文件夹体积、现有 Wiki 和旧资料子目录，确认后原地初始化、同步并自动切换，不要求用户重新上传。
  - 便携资料库的额外课程目录改为库内相对路径；重新打开已移动的资料库时会自动修复旧绝对路径，避免资料显示为空。
  - 旧文件夹迁移改为同步成功后再激活；同步或激活失败会恢复迁移前的注册表和活动资料库，不留下半注册状态。
  - 验证：Python `1066 passed`、Vitest `3 passed`、TypeScript 与生产构建通过、Playwright 多视口 `39 passed`。

- **P5E 用户主动触发的 LLM Wiki 完成**: 将资料导入与 AI 整理彻底分离，只有用户明确发起并确认计划后才写入 Wiki。
  - 新增持久化 Wiki 计划，支持当前学习范围、指定资料、课程和已有 Wiki 主题；计划展示新增、更新、合并、冲突和跳过项。
  - Chat 新增 `/wiki plan`、`/wiki update`、`/wiki generate`，Library 新增“整理成 Wiki / 更新 Wiki”入口和可展开页面预览。
  - 生成概念页与实体页，保存结构化 `source_refs`、双向相关概念链接，以及 heading、PDF 页、PPT 页或 chunk 级原文定位。
  - 写入前创建本地检查点，支持显式撤销；写入失败自动恢复，用户手写同名页只标记冲突且不会覆盖。
  - 无指定资料范围时，检索顺序优先用 Wiki 理解概念结构，再以原始资料作为事实证据，并继续在引用中区分 Wiki 与本地资料。
  - 参考 OpenHanako 的资源卡、渐进披露和预览分栏逻辑，保留 Bobodan 暖纸、墨蓝、仓耳今楷与三花猫品牌体系。
  - 验证：Python `1049 passed`、Vitest `3 passed`、生产构建通过、Playwright `30 passed`。

- **P5D 最终可用性收尾**: 补齐 Wiki 维护和 Chat Slash 命令 / Skills 入口。
  - Wiki 分类新增健康检查、孤立页 / 断链 / 过期页统计与详情；“整理并重建索引”只归档 Bobodan 生成的重复页，不删除用户原始资料。
  - Chat 输入 `/` 弹出贴近 composer 的命令面板，支持文本筛选、方向键、Enter / Tab 选择和 Esc 关闭。
  - 提供 `/new`、`/library`、`/wiki`、`/practice`、`/review`、`/kb search`、`/learning today`、`/quiz generate` 等 Web 安全命令。
  - Skills 面板只开放当前 Web runtime 可完整执行的 `course-learning`、`exam-prep`、`study-loop`；显式选择后服务端按本轮临时指令加载对应 `SKILL.md`。
  - 验证：Python `1037 passed`、Vitest `3 passed`、生产构建通过、Playwright `27 passed`。

- **P5D 本地学习闭环 Web MVP 完成**: 在第二轮 Web UI 基础上补齐首次配置、资料范围约束和 Chat → Practice → Review 纵向闭环。
  - 新增四步首次配置，覆盖用户与目标、AI 连接、首批学习资料、记忆与联网边界；已有会话或资料的工作区自动兼容。
  - Library 可维护共享学习范围并选中文字带到 Chat；Chat 与 Practice 请求都会把资料 ID 传到后端，RAG 检索和出题按范围强制过滤。
  - Chat 回答支持渐进式过程摘要，不暴露原始思维链；生成练习会使用本轮返回的精确题目 ID，避免旧题混入。
  - Practice 的“问 AI”改为当前题目内的轻量辅导抽屉，桌面、窄屏和移动端均保持在做题流程内。
  - 验证：Python 全量测试 `1037 passed`，Vitest `3 passed`，生产构建通过，Playwright `27 passed`。

- **P5D Web UI 第二轮完善**: 按 OpenHanako 的字体与工作区交互作为参考，修复第一版的字体覆盖、资料混排、侧栏和会话命名问题。
  - 字体改为五套 token：Luo 仅用于品牌与固定展示标题，系统黑体用于高频 UI，Noto Serif SC Unicode Range 分片用于 AI 回答，仓耳今楷 W04/W05 用于资料与 Wiki 正文，等宽字体用于代码与路径；Noto 字体及 OFL 许可随项目分发。
  - Library 增加“学习资料 / Wiki”分类，隐藏 Wiki 结构文件，按 NFKC 与标点归一化去重；两份旧生成页已归档到 `.bobodan/archive/wiki/<timestamp>/`，规范索引重建为 6 页。
  - 左右栏可独立折叠并保存用户状态；内容不足 720px 时按右栏、左栏顺序自动收起，桌面支持 200ms 边缘悬停预览，移动端继续使用抽屉。
  - 首轮回答后异步生成短会话标题，15 秒超时或模型失败时使用首问本地回退；手动标题不会被覆盖，会话按今天、昨天、本周、更早分组并显示时间。
  - 默认提示收敛装饰 Emoji 与重复小猫自称；欢迎、思考、阅读、写作、等待、休息和回答反馈开始使用现有品牌状态图与表情图。
  - 新增资料分类、Wiki 归档、会话标题和多视口侧栏/字体测试；生产构建、Vitest、Python 聚焦测试和 Playwright 多视口用例通过。
  - 资料与 Wiki 阅读器进一步采用 Kami 同款仓耳今楷 W04/W05 双字重本地字体；AI 回答继续使用 Noto Serif SC，高频 UI 不受影响。

- **P5D Web UI 第一版**: 建立 React 19 + TypeScript + Vite + Tailwind 本地 Web 应用，并按 `docs/DESIGN.md` 落地 Bobodan 暖纸、墨蓝、Luo 字体和三花猫品牌资产。
  - 完成桌面三栏、窄屏上下文抽屉、移动端底部导航，以及 Chat / Library / Practice / Review 四个一级入口。
  - Chat 使用 OpenHanako 式居中起始状态和中央阅读流，普通桌面保持完整侧栏；支持会话恢复、重命名、删除、草稿保存、POST SSE 流式回答、状态摘要、来源标签、失败重试与生成练习入口。
  - Web 后端与 CLI 一致加载工作区 `.env`，修复已配置 Provider 在浏览器中错误返回 `503 provider_unavailable` 的问题。
  - Library 支持真实资料列表、详情阅读和 Markdown / PDF / DOCX / PPTX 导入；Practice 支持出题、未完成练习恢复、答题、批改、小结和放弃；Review 支持真实队列与针对性练习。
  - 本地打包品牌字体与许可证；新增 Vitest API / 组件测试和 Playwright 桌面、移动布局验收。

- **Bobodan 品牌与 Web 视觉参考资产**: 完成三花猫品牌角色规范、正式透明头像、四表情、六学习状态和 Chat 起始插图，并导出前端可直接使用的 PNG / WebP 尺寸。
  - 新增 `docs/assets/brand/BOBODAN_MASCOT.md`，明确品牌角色与用户可配置人设的边界、固定识别特征和后续图片接收规则。
  - 新增 `web/frontend/public/assets/brand/` 前端资源清单，以及 `docs/prototypes/bobodan-study-workspace.html` 静态视觉预览。
  - `docs/DESIGN.md` 补充品牌角色规范；`docs/PROJECT_GUIDE.md` 补充 OpenHanako 的布局、过程披露、设置、记忆、恢复、权限和扩展借鉴边界。

- **P5C Web UI 产品化前置工作完成**: 在不实现 React 页面之前，完成 Web MVP 所需的运行时、API、资料、来源和练习状态基础。
  - 新增共享 `RuntimeService / RuntimeContext`，CLI 与 Web 统一加载 provider、workspace、skills、memory 和 trace；quiz / learning LLM 调用使用同一份 config。
  - Chat API 增加 `run_id`、安全 SSE 事件适配、session list / detail / rename / delete；Web 运行时只开放 RAG、学习、练习和记忆工具白名单。
  - Web 错误统一为 `code / message / details`，流式异常、工具原始输出、secret 和本地绝对路径不再直接返回浏览器。
  - Library 增加托管文件上传、document list / detail 和 source roots；Markdown、PDF、DOCX、PPTX 可进入现有 RAG v2 同步链路。
  - Question 增加 `Attribution + SourceRef` 持久化及旧 SQLite 迁移；Practice 增加 active session、状态恢复、进度、掌握度变化和 abandon；Review 增加聚合队列。
  - 更新 `docs/PROJECT_GUIDE.md` 与 `docs/DESIGN.md`，明确下一阶段为 P5D 本地学习闭环 Web MVP，所有 UI 必须遵循设计 token 与交互边界。
  - 验证：Python 编译检查通过；全量测试 `1020 passed`，2 个既有 warning。

- **Bobodan 当前阶段收尾**: 完成产品定位、文档合并、设计规范补强和 FastAPI skeleton，Web UI 留到下一阶段实现。
  - `docs/PROJECT_GUIDE.md`（新）: 作为后续给人和 AI 看的唯一主入口，整理产品定位、当前阶段、下一步路线、练习系统、功能分层和架构边界。
  - `docs/DESIGN.md`: 补充 Bobodan Web UI 设计硬约束，包括轻纸面质感、Study / Workbench 分区、阅读优先的中等密度、移动端 Chat / Practice / Review 优先、Tailwind / shadcn 语义 token、核心组件规范、来源 chip、Practice 一题一卡、温和状态反馈、用户可配置人设和硬性反模式清单。
  - `web/backend/`（新）: FastAPI skeleton，包含 app/deps/sse 以及 chat、kb、quiz、learning、memory、settings 路由，先完成后端协议边界，不实现 Web UI。
  - `tests/test_web_backend.py`（新）: 覆盖 Web backend health、路由协议、SSE 包装和 service 委托边界。
  - 文档整理：收敛旧架构、旧计划和 archive 文档，更新 `CLAUDE.md`、`README.md`、`docs/README.md`、`docs/MCP.md`、`docs/tools/skills.md`，强调后续 UI / 设计必须先读 `docs/DESIGN.md`。
  - 验证：最近一次全量测试 `998 passed`，2 个既有 warning。

- **RAG v2 — Qdrant + SQLite + Hybrid Retrieval**: 知识库检索升级为完整 RAG 基础设施。
  - `rag/schema.py`（新）: `RetrievalHit`、`DocumentHit`、`RetrievalResult`、`HybridResult` 统一结果 schema。
  - `rag/sqlite_store.py`（新）: `KBSQLiteStore` — SQLite + FTS5 存储层（documents, chunks, chunks_fts, directory_entries, retrieval_runs）。FTS5 content-synced triggers 自动同步。
  - `rag/qdrant_store.py`（新）: `QdrantStore` — Qdrant local persistent 向量存储，支持 upsert/search/delete_by_filter。Point id 使用 UUID5 确定性转换。
  - `rag/embedding_service.py`（新）: `EmbeddingService` — Ollama embedding 包装器，graceful degradation。
  - `rag/source_section.py`（新）: `SourceSection` — 多格式解析统一中间结构。
  - `rag/parsers/`（新）: 多格式解析器 — Markdown heading-aware、PDF page-aware (PyMuPDF)、PPT slide-aware (python-pptx)、Word heading-style (python-docx)。
  - `rag/chunker_v2.py`（新）: heading-aware adaptive chunking — heading_path 继承、长 section 二次切分、短 section 合并、embedding text heading context 注入。
  - `rag/rrf.py`（新）: RRF (Reciprocal Rank Fusion) — vector + FTS5 排名融合。
  - `rag/hybrid.py`（新）: `HybridRetriever` — vector + FTS5 → RRF → chunk candidates。
  - `rag/directory.py`（新）: `DirectoryRetriever` — 文档级路由，metadata lexical + chunk aggregation。
  - `rag/grep_retriever.py`（新）: `GrepRetriever` — rg 优先 + Python fallback，intent-aware evidence thin 判断（exact_lookup vs coverage），扩展阶梯。
  - `rag/orchestrator.py`（新）: `RetrievalOrchestrator` — 三种检索模式调度（hybrid/directory/directory_grep），auto 模式规则路由 + hybrid 空结果 fallback。
  - `rag/query_router.py`（新）: 规则路由（directory_grep > directory > hybrid）。
  - `obsidian/sync.py`: 改用新 parsers + chunker_v2 + SQLite + Qdrant 写入，incremental sync 保留 manifest。
  - `service/kb_service.py`: `search()` 新增 `mode` 参数（auto|hybrid|directory|directory_grep）。
  - `tools/rag_search.py`: tool schema 新增 `mode` 参数。
  - `rag/retriever.py`: 优先走 Orchestrator，legacy JSON index fallback。
  - `rag/citations.py`: 支持 heading、page/slide、retriever 信息。
  - `config.yaml`: 扩展 `rag:` section（vector_db, chunking, retrieval 配置）。
  - `requirements.txt`: 新增 `qdrant-client`、`python-docx`、`python-pptx`、`pymupdf`。
  - 112 个新测试覆盖 SQLite store、Qdrant store、parsers、chunker v2、RRF、hybrid/directory/grep retriever、orchestrator、query router。994 测试全通过。

- **Bobodan base system prompt**: `core/agent_loop.py` 新增稳定的 Bobodan 基础 system prompt，用 marker 幂等注入。
  - 定位从通用 CLI assistant 收敛为 "local-first personal assistant with strong learning capabilities"。
  - 学习能力仍是核心强项，但允许普通聊天、陪伴、头脑风暴、轻娱乐和日常问题。
  - 人设和语气继续由 memory / persona 偏好提供，base prompt 只固定产品主线和事实边界。
  - 保留 `LEGACY_BASE_SYSTEM_PROMPT` 清理逻辑，旧 session 会移除旧提示词并注入新提示词。
  - `tests/test_agent_loop.py`: 覆盖 base prompt 注入、幂等、防重复和 legacy prompt 清理。

- **内置 skills 调整**: 删除与学习助手主线无关的 `weather` 示例 skill，新增并收敛 Bobodan 学习场景内置 skill。
  - `skills/study-loop/SKILL.md`: 学习闭环引导，负责知识库检查、学习计划、今日任务、练习、进度和导出。
  - `skills/exam-prep/SKILL.md`: 考前冲刺和薄弱点训练，基于 `learning_progress` / `learning_review` / `quiz_start` / `question_generate`，不再引用不存在的 `quiz_weak` / `quiz_wrong` / `quiz_stats` 工具。
  - `skills/obsidian-workspace/SKILL.md`: Obsidian / 本地知识库工作区管理，负责同步资料、知识库状态、导出学习计划/做题总结和 wiki 整理。
  - 当前内置 skill 集合：`aihot` / `course-learning` / `study-loop` / `exam-prep` / `obsidian-workspace`。

- **P5 Service 层抽取**: 5 个 service 模块提取完成，CLI 和 tools 统一委托 service 层，为 FastAPI/Web 前后端分离做准备。
  - `service/learning_service.py`（新）: `LearningService` — 学习计划、进度、复习、掌握度（9 个方法）。
  - `service/quiz_service.py`（新）: `QuizService` — 出题、做题、批改、错题本、薄弱点（6 个方法）。
  - `service/memory_service.py`（新）: `MemoryService` — 永久记忆、每日记忆、晋升（9 个方法）。
  - `service/kb_service.py`（新）: `KBService` — 知识库同步、状态、RAG 检索、图谱查询、重置（5 个方法）。`sync()` 内置 workspace 路径安全边界。
  - `service/agent_service.py`（新）: `AgentService` — provider 创建/列表、session 持久化、agent 事件流（6 个方法）。`create_provider` 返回 LLMProvider 实例，`list_providers` 包含 `configured` 状态但不暴露 API key。
  - 所有 service 方法返回 `{"ok": bool, ...}` dict，无 ANSI/HTML 格式。
  - `cli/repl.py`: `/learning`、`/quiz`、`/memory`、`/kb`、`/model`、`/session` 命令全部委托对应 service。删除 `normalize_session_id`、`get_session_path`、`resolve_session_id` 等已迁移方法。
  - `tools/learning_tools.py`、`tools/quiz_tools.py`、`tools/memory_tools.py`、`tools/rag_search.py`、`tools/graph_query.py`、`tools/knowledge_status.py`、`tools/obsidian_tool.py`: 全部委托对应 service，保留 ToolResult 包装。
  - `tests/test_learning_service.py`（新，27）、`tests/test_quiz_service.py`（新，16）、`tests/test_memory_service.py`（新，21）、`tests/test_kb_service.py`（新，17）、`tests/test_agent_service.py`（新，19）: 共 100 个新测试。
  - 869 测试全通过。

- **P2 Event Trace 轻量版**: 每次 Agent run 记录关键事件到 JSONL trace 文件，支持事后查看"做了什么、花了多久、哪步失败"。
  - `core/trace.py`（新）: `TraceWriter` 类写入 `.bobodan/traces/{session_id}_{timestamp}_{run_suffix}.jsonl`，只记录 `tool_start` / `tool_end` / `assistant_done` / `error` 事件（不含 `assistant_delta`）。Secret 字段自动 redact，content 超 500 字符截断。线程安全（`threading.Lock`）。
  - `core/agent_loop.py`: `assistant_done` 事件增加 `termination_reason` 字段（`final_answer` / `max_iter` / `error`）；`run_stream` 异常时 yield `assistant_done(termination_reason="error")` 再 re-raise；构造函数接受可选 `trace_writer` 参数，有则自动写入 trace。
  - `cli/repl.py`: 每次 run 创建 `TraceWriter` 并注入 `AgentLoop`；新增 `/trace` 命令（列出最近 run、查看 tool timeline）。
  - `core/trace.py`: 新增 `list_traces` / `read_trace` / `summarize_trace` 读取函数。
  - `tests/test_agent_loop.py`: 覆盖三种 `termination_reason`、`TraceWriter` 文件创建/唯一 run 路径/过滤/截断/redact/错误事件、`AgentLoop` trace 集成、trace 读取/汇总。

- **P3 Workflow Runtime**: 学习计划从"看一眼"变成"可以执行"——自动推断完成状态、追赶模式、手动标记、合并今日任务视图。
  - `learning/schema.py`: `LearningPlan` 增加 `status`（active/completed）和 `current_day` 字段。
  - `learning/store.py`: 新增 `plan_progress` 表（plan_id, day, task_index, source）+ 迁移逻辑 + CRUD 方法（`mark_task_done` / `mark_step_done` / `get_progress` / `get_active_plans` / `update_plan_status`）。
  - `learning/workflow.py`（新）: `PlanWorkflowTracker` — 自动推断 step 完成（所有 topics mastered → 标记完成）、plan 完成时自动 status=completed、进度查询、追赶模式今日任务。
  - `learning/progress.py`: `update_from_quiz` 在答对后自动调用 `check_plan_completion`。
  - `tools/learning_tools.py`: 新增 `learning_plan_progress` 工具（status / complete_task / complete_step / today）。
  - `cli/repl.py`: `/learning today` 合并显示未完成计划任务 + 到期复习清单。
  - `tests/test_workflow.py`（新）: 覆盖 plan_progress CRUD、自动推断、追赶模式、进度汇总、工具集成、ProgressTracker 联动、手动 mastery 标记联动和 SQLite 连接关闭。
  - 769 测试全通过。

- **P1 Obsidian 写回**: 学习计划和做题总结可导出为 Obsidian Markdown，兑现 README 承诺。
  - `tools/obsidian_export.py`（新）: `obsidian_export_plan` 从 LearningStore 读取计划，生成 YAML frontmatter + 按天 checkbox 任务 + `[[双链]]` 知识点引用的 Markdown，写入 `{vault}/学习计划/{title}.md`；`obsidian_export_quiz_summary` 从 QuizStore 读取错题和薄弱点分析，生成按概念分组错题本 + 薄弱点表格 + 掌握度概览的 Markdown，写入 `{vault}/做题总结/{date}.md`。
  - 路径安全检查：`_is_within_workspace` 防止写入 workspace 外路径。
  - `tests/test_obsidian_export.py`（新）: 16 个测试覆盖文件生成、frontmatter、checkbox、wikilink、错题分组、薄弱点表格、掌握度概览、空数据、路径越界、plan 不存在。
  - 716 测试全通过。

- **P0 学习闭环补全**: quiz_submit 自动写每日记忆 + 更新掌握度 + session 完成汇总，做题→记忆→掌握度链路真正跑通。
  - `learning/quiz_integration.py`（新）: `record_quiz_learning_effect` 做题后自动写每日记忆（tags: quiz + 概念）并更新掌握度；`record_quiz_session_summary` 全部答完后写汇总记忆并标记 session 完成。
  - `tools/quiz_tools.py`: `quiz_submit` 在 `store.record_attempt()` 后调用集成函数，失败只 warning 不阻塞返回。返回 data 新增 `session_completed` 字段。
  - `learning/__init__.py`: 导出 `record_quiz_learning_effect`、`record_quiz_session_summary`。
  - `tests/test_quiz_integration.py`（新）: 13 个测试覆盖正确/错误/连续答对→mastered/记忆写入/标签/独立调用/累积状态/未完成不触发汇总/完成触发汇总/弱概念/全对。
  - 掌握度规则：连续答对 2 次 → `mastered`，答对 1 次 → `learning`，答错 → `needs_review`。
  - 700 测试全通过。

- **CLI 轻量状态行收尾**: `Thinking` / `Checking` / `Working` / `Drafting` / `Polishing` 状态词按 Bobodan 设计语言分色显示，spinner 保持稳定强调色，elapsed 保持 dim，减少单色刷新疲劳；tool running 行统一为 clay/orange，success/error 继续使用 green/red。覆盖 `cli/tool_display.py`、`cli/repl.py` 和对应回归测试。
- **Bobodan 设计参考文档**: `docs/DESIGN.md` 作为后续 Web UI / TUI / 官网设计的长期视觉基准，收敛为 Warm Paper Knowledge Garden / Natural Editorial Zen 方向，并明确 ink blue、clay、sage、petal pink 等色彩角色。
- **CLI Tool Display UX (P0)**: 工具调用显示更清晰，specialist 内部 tool events 较多时不刷屏。详见 `docs/NEXT_STEPS_EXECUTION_PLAN.md` P0 节。
  - **B-lite single-active-line UI**: 同一时刻只动画一行 —— thinking line 或 tool spinner 占据光标位置，每 100ms tick 原地切换帧。
  - **工具参数摘要** (`cli/tool_display.py: summarize_tool_args`): `read_file` / `write_file` / `list_dir` / `stat_path` 取路径尾部；`rag_search` / `graph_query` 取 query/concept；`delegate_doc_reader` 取 source_paths 尾 + goal；`delegate_triage` 取 query；`delegate_planner` 取 goal；`change_dir` / `http_request` 走特殊规则；MCP 和其他内置工具走 60 字符 short JSON fallback。
  - **连续同名 tool call 合并** (`CoalescerStack`): 第 1-2 次正常显示，第 3 次触发 `✓ name ×3` inline marker，4+ 静默计数，turn 结束或 name 变化时 flush `✓ name ×N total {elapsed:.1f}s`。错误不计入成功合并组，立即显示 `✗ name: msg`。scope 隔离：主 agent 一套，每个 active specialist 一套。
  - **thinking 动词轮换** (`THINK_VERBS`): `["Thinking", "Checking", "Working", "Drafting", "Polishing"]`，2.5s 等距切换；不用 stage-specific 词（具体动作由 tool active line 表达）。
  - **`core/agent_loop.py`**: `tool_end` event 新增 `elapsed`（必填）和 `result_summary`（可选，仅白名单工具）字段，作为未来 trace 元数据。`_compute_result_summary` 为 `change_dir` 生成 `→ {cwd}`，为 `http_request` 生成 `status {code}`。
  - **`/ui tools on|off` 低噪音模式** (`_b_should_show`): off 时隐藏 tool_start / 成功 tool_end / 成功 coalesce summary / 成功 specialist_event，但**保留所有 ok=False 错误行**（包括 specialist 内部错误）—— errors 是安全网，不进低噪音模式。
  - **删除 specialist running 占位行** (`◐ doc_reader_specialist running...`): B-lite 下 delegate active line 已经表达 running 状态，额外 running 行是噪音；specialist scope 只用 4 空格缩进表达。
  - **`tests/test_repl_display.py`** (新): 42 个 L1（参数化摘要规则）+ L2（7 个 coalesce 状态机 case + flush without pending emits empty）单元测试。
  - **`tests/test_repl.py`** 扩 L3 结构测试：B-lite active line seal on assistant_delta / seal on new tool_start / in-place update / off mode 隐藏成功保留错误；并覆盖 coalesce wall-clock total、delegate parent scope 记账、thinking spinner tick。
  - **Streaming 文本输出修复**: assistant 正文开始后清除 thinking active line，避免 `Thinking` / `Checking` / `Working` 状态行被 seal 到正文中反复刷屏。
  - **Streaming 速度修复**: 移除 `_flush_stream_buffer()` 的逐字符 `sleep`，避免格式化整行输出时阻塞 UI loop，改善流式输出和 thinking spinner 的卡顿感。
  - **Partial preview 节流**: 短 token/chunk 先缓冲，攒到一小段再直接输出，避免当前行被频繁清除重写造成视觉疲劳。
  - **`agents/runner.py`**: specialist 内部 `display_events` 透传 `elapsed` / `result_summary`，避免内部 tool success 显示退化为 `(0.0s)`。
  - 完整测试 683 个通过（1 个既有 MCP coroutine warning）。

- **Learning Agent Orchestrator（多 agent 骨架 v1）**: 主 bobodan 派活给 specialist，不是 peer-to-peer。3 个 built-in specialist（doc_reader / triage / planner），每个配一个 `delegate_*` tool。详见 `docs/archive/agents_design.md`。
  - `agents/base.py`: `BaseSpecialist` ABC（name / system_prompt_template / data_to_content / defaults 契约）。
  - `agents/config.py`: `SpecialistConfig` Python defaults + YAML merge，未知 key 报错。
  - `agents/registry.py`: `SpecialistRegistry` + `last_invocations` deque(maxlen=10)。
  - `agents/runner.py`: `run_specialist()` — fresh session 隔离，工具过滤（hard deny `delegate_*`/`memory_*`），per-specialist timeout（非阻塞返回，provider request timeout cap 到 specialist budget），guarded catch（无自动重试），triage 窄合约校验。content cap 2000 chars，error cap 500 chars，centralized。
  - `agents/specialists/doc_reader.py` / `triage.py` / `planner.py`: 3 个 specialist 实现，documented return contracts。`doc_reader` 明确要求按 `source_paths` 原样调用 `read_file`，禁止缩短为 basename。
  - `agents/prompt.py`: system prompt 模板渲染。
  - `tools/agents.py`: `register_delegate_tools(registry, get_session, get_app_config)` 只为 enabled specialists 注册 `delegate_*` tool（每个独立 schema）；delegate wrapper 将结构化参数转换成 task text，并完整保留 `doc_reader.source_paths`。`delegate_doc_reader` description 明确要求读并总结文件时优先于 `read_file`。
  - `tools/file_ops.py`: `read_file` description 明确 raw-text 定位，并提示 read-and-summarize 任务优先使用 `delegate_doc_reader`。
  - `core/agent_loop.py`: 新增 `tools_schema` 和 `max_iterations` 可选构造参数（specialist runner 用）；支持 UI-only `specialist_event`，用于展示 specialist 内部 tool events，且不写入父 session。
  - `cli/repl.py`: 新增 `/specialists` 命令组（list / status / tools），启动时 `register_builtin_specialists()` + `register_delegate_tools()`。delegate tool 运行时显示 specialist running header 和缩进内部 tool events。
  - `config.yaml`: 新增 `specialists:` section（3 个 specialist 各自 timeout/iter/allowed_tools/allow_mcp）。
  - `tests/test_agents_*.py` + `tests/test_agent_loop.py`: 回归测试覆盖 7 条 runtime invariant、真实 `AgentLoop.run_stream(task)` 调用契约、非阻塞 timeout、disabled specialist 不暴露 delegate tool、triage `(none)` 契约、`doc_reader.source_paths` 路径保真、specialist display events 不污染父 session。
  - `docs/archive/agents_design.md`: 完整设计文档（14 决策 + 13 runtime invariant + 10 章）。

- **Runtime model switch (`/model` command)**: REPL 启动后可切换 active provider 不重启会话。`AgentLoop.set_provider()` + `REPL._make_active_provider()` helper。详见 `feature/model-switch` 分支。


- **MCP (Model Context Protocol) 客户端**: 接入外部 MCP server，把它们暴露的 tools 注入到 agent loop。
  - `mcp_client/event_loop.py`: `AsyncEventLoop` 单例，后台 daemon 线程跑 asyncio event loop，`run_sync(coro, timeout)` 桥接 sync→async。
  - `mcp_client/manager.py`: `MCPManager` 单例，per-server 状态（config/transport/connected/tools/last_error），懒连接，`reload()` diff 配置。
  - `mcp_client/config.py`: YAML 加载 + `${ENV_VAR}` 占位符替换（fail-fast 缺失）。`type` 字段作为 `transport` 的别名，兼容 Claude Desktop 配置格式。
  - `mcp_client/naming.py`: `build_safe_tool_name()` 按 OpenClaw 规则做 sanitization（替换特殊字符为 `-`，server 截断 30 字符，总长 64 字符，冲突加 `-2`/`-3` 后缀）。
  - `mcp_client/catalog.py`: 跨所有 enabled server 拉取 tool specs，连接失败隔离。
  - `mcp_client/tool_wrapper.py`: 把 MCP tool 包装成 Bobodan `ToolResult`，None kwargs 过滤，异常透传。
  - `mcp_client/prompt.py`: `build_mcp_status_prompt()` 生成 system prompt 段。
  - `mcp_client/transport_stdio.py` / `transport_sse.py` / `transport_http.py`: 三个 transport 真实实现，官方 SDK 1.19+ 驱动。stdio 子进程 stderr 走 DEBUG 日志。call_tool 用 `btype` 区分 text/image/resource block。
  - `tools/mcp.py`: `register_mcp_tools(config)` REPL 集成入口，per-server 失败隔离。
  - `core/agent_loop.py`: 新增 `mcp_prompt` 参数，`_inject_mcp_prompt()` 幂等注入 system message。
  - `cli/repl.py`: 新增 `/mcp` 命令组（list/status/restart/tools/reload）。启动面板增加 `mcp: ...` 行。
  - `tests/test_mcp_*.py`: 76 个测试覆盖 config、event loop、manager、naming、catalog、prompt、tool_wrapper、三个 transport、REPL 命令、agent_loop 注入。
  - `docs/MCP.md`: 用户文档（配置、命令、troubleshooting、架构图、限制）。

- **Ollama RAG 嵌入后端**: 接入本地 Ollama embedding 模型，提升 RAG 检索的语义匹配能力。
  - `rag/ollama.py`: `OllamaEmbeddingClient` Ollama embedding API 客户端。三层探测（服务可达→模型能力→真实 embed 请求），结果缓存，超时控制。
  - `rag/dense_store.py`: `DenseVectorStore` dense 向量索引，纯 Python cosine similarity，预存 norm 加速搜索。索引文件包含 model/dim 元数据，支持模型变化检测。
  - `rag/router.py`: `VectorStoreRouter` 路由层。auto 模式探测 Ollama 后自动选择后端，`/kb sync` 双写 dense + sparse 索引，搜索失败自动降级。
  - `config.yaml`: 新增 `rag:` section（`embedding_backend`、`ollama_url`、`ollama_model`、`probe_timeout`、`request_timeout`）。
  - `cli/repl.py`: 启动时探测 embedding 后端并打印状态。`/kb status` 增加 embedding 后端信息。
  - `tests/test_ollama_embedding.py`: 38 个测试覆盖 OllamaEmbeddingClient、DenseVectorStore、VectorStoreRouter、retriever 集成。

- **LLM Wiki 编译层**: 新增 `wiki/` 模块，基于 Karpathy LLM Wiki 模式，将源文档编译为结构化 wiki 页面写入 Obsidian vault。
  - `wiki/schema.py`: `WikiPage`、`CompileResult`、`WikiConfig` 数据模型。页面类型：`wiki_entity`（实体）、`wiki_concept`（概念）。来源追踪通过 `source_registry.json` 而非复制内容。
  - `wiki/compiler.py`: `WikiCompiler` LLM 编译引擎。读源文件 → LLM 提取实体/概念/摘要 → 生成 wiki 页面。支持增量更新（source hash 追踪，只编译变更文件）。
  - `wiki/index.py`: `WikiIndexer` 管理 `index.md`（内容目录）和 `log.md`（操作日志）。
  - `wiki/lint.py`: `WikiLinter` 健康检查——孤立页面、断链、缺失页面、过期页面。
  - `tools/wiki_tools.py`: 注册 `wiki_ingest`（编译源文件）、`wiki_lint`（健康检查）两个 Agent 工具。
  - `cli/repl.py`: 新增 `/wiki init`、`/wiki ingest`、`/wiki lint`、`/wiki status` 命令。
  - `tests/test_wiki.py`: 23 个测试覆盖 schema、index、lint、compiler、REPL 命令。

## [0.12.0] - 2026-05-20

### 新增
- **记忆系统升级**: 新增 `memory/` 模块，实现"每日记忆 → FTS5 检索 → 晋升机制"记忆生命周期。
  - `memory/store.py`: `MemoryIndexStore` SQLite 索引 + FTS5 全文检索虚拟表。支持 `chunks`（文本块索引）、`recall_log`（召回记录）、`promotion_log`（晋升记录）三张表。FTS5 triggers 自动同步 chunks 表变更。
  - `memory/daily.py`: `DailyMemoryManager` 每日记忆文件管理，存储在 `.bobodan/daily/YYYY-MM-DD.md`。支持 `append`（带时间戳追加）、`read`、`get_today`、`get_yesterday`、`list_recent`、`get_all_dates`。文件带 YAML frontmatter（date, tags）。
  - `memory/search.py`: `MemorySearcher` 混合检索，FTS5 为主、向量为辅。FTS5 无结果时自动降级到现有 `LocalVectorStore`。支持 `search`、`search_daily`、`search_permanent` 三种模式。
  - `memory/promotion.py`: `PromotionEngine` 每日记忆晋升引擎。评分公式：`0.4×frequency + 0.4×quiz + 0.2×recency`（30天半衰期）。晋升阈值：score ≥ 0.6 且 recall_count ≥ 2。`promote()` 将每日记忆写入永久记忆并记录晋升日志。
  - `tools/memory_tools.py`: 新增 `memory_daily_save`（写入每日记忆）、`memory_daily_read`（读取每日记忆）、`memory_promote`（检查并执行晋升）三个 Agent 工具。`memory_recall` 改为 FTS5 优先检索。
  - `core/memory.py`: `save()` 自动索引到 FTS5，`forget()` 自动清理 FTS5。`build_memory_prompt()` 注入今日+昨日每日记忆到 system prompt。`search()` 改为 FTS5 优先、向量降级。`get_stats()` 增加 FTS5 统计。
  - `cli/repl.py`: 新增 `/memory daily [content|YYYY-MM-DD]`（写入/查看每日记忆）、`/memory promote [--dry-run]`（晋升检查）、`/memory review`（今日复习清单，联动 learning 模块）。`/memory stats` 增加 FTS5 统计。
  - `tools/__init__.py`: 导出新增的三个工具。
  - `tests/test_memory_upgrade.py`: 34 个测试覆盖 store、daily、search、promotion、core 集成、REPL 命令、Agent 工具。

### 设计决策
- 每日记忆定位：缓冲 + 学习日志 + 晋升。做题结束后自动写入，用户也可手动写入。
- FTS5 与向量：FTS5 为主（零依赖、支持中文、比稀疏向量更准确），向量为降级兜底。
- 晋升评分：出现次数(0.4) + 做题关联(0.4) + 时间衰减(0.2)。利用学习助手独有的做题数据驱动晋升。
- 晋升调度：启动时轻量检查 + `/memory promote` 手动触发（CLI 工具无常驻进程）。
- 存储格式：Markdown 文件 + SQLite 只做索引，保持人可读、易备份。
- 记忆生命周期：每日缓冲 → 晋升评分 ≥ 0.6 且出现 ≥ 2 → 永久记忆。

## [0.11.0] - 2026-05-19

### 新增
- **学习路线系统**: 新增 `learning/` 模块，实现"学习计划 → 掌握度追踪 → 间隔复习"闭环。
  - `learning/schema.py`: `Mastery`（知识点掌握度）、`LearningPlan`（学习计划）数据模型。
  - `learning/store.py`: `LearningStore` SQLite 存储，新增 `mastery` 和 `learning_plans` 两张表。
  - `learning/scheduler.py`: `ReviewScheduler` 简单间隔重复算法（1/3/7/14天），做对推进、做错重置。支持手动覆盖（`mark_manual`）。
  - `learning/progress.py`: `ProgressTracker` 掌握度概览、薄弱/最强知识点排行、从做题记录自动推断。
  - `learning/path.py`: `LearningPathGenerator` 基于 LLM 的个性化学习计划生成。数据优先级：做题记录 > 用户目标 > 图谱关系 > 课程结构。无 LLM 时回退到基于薄弱点的简单计划。
  - `tools/learning_tools.py`: 注册 `learning_path`、`learning_progress`、`learning_review` 三个 Agent 工具。
  - `cli/repl.py`: 新增 `/learning` 命令集（`plan`/`progress`/`review`/`mark`/`plans`）。
  - `tests/test_learning.py`: 28 个测试覆盖 schema、store、scheduler、progress、path generator、tool 集成。

### 设计决策
- 模块划分：learning/ 管路线+调度+进度，quiz/review 管诊断，职责不重叠。
- 复习策略：先用简单间隔重复，遗忘曲线（Ebbinghaus）放后续计划。
- 进度追踪：混合模式——自动从做题记录推断 + 用户手动覆盖。
- 路线输出：结构化 JSON 存 SQLite，可选写回 Obsidian（待实现）。

## [0.10.0] - 2026-05-19

### 新增
- **知识库状态产品化**: 新增 `knowledge/` 模块，包含 DocumentRecord（按文件追踪导入状态）、manifest（知识库清单）、import_report（同步后导入报告）、library（课程/chunk/图谱聚合统计）。新增 `knowledge_status` Agent 工具。`/kb status` 增强为显示课程分组、图谱节点类型、同步错误。
  - `knowledge/documents.py`: `DocumentRecord` 数据类，`build_document_records()` 从 ScannedNote/SourceDocument 构建记录。
  - `knowledge/manifest.py`: `.knowledge/manifest.json` 读写。
  - `knowledge/import_report.py`: `ImportReport` 数据类，同步后错误和摘要报告。
  - `knowledge/library.py`: `CourseSummary`、`LibrarySummary` 聚合统计。
  - `tools/knowledge_status.py`: Agent 工具，返回知识库概览 JSON。
  - `tests/test_knowledge_status.py`: 13 个测试。

- **题库系统 MVP**: 新增 `quiz/` 模块，实现"生成题目 → 做题 → 批改 → 错题记录 → 薄弱点分析"学习闭环。
  - `quiz/schema.py`: `Question`、`QuizSession`、`QuizAttempt` 数据模型，支持 single_choice / true_false / short_answer 三种题型。
  - `quiz/store.py`: `QuizStore` SQLite CRUD（questions、quiz_sessions、quiz_attempts 三张表），每操作独立连接，WAL 模式。
  - `quiz/generator.py`: `QuestionGenerator` 基于 RAG 检索 + LLM 出题，Prompt 约束 JSON 输出 + 后处理解析。
  - `quiz/evaluator.py`: `QuizEvaluator` 选择/判断题自动批改，简答题 LLM 批改。支持中文答案归一化（对/错、是/否、√/×）。
  - `quiz/review.py`: `QuizReviewer` 错题本和按概念的薄弱点分析。
  - `tools/quiz_tools.py`: 注册 `question_generate`、`quiz_start`、`quiz_submit` 三个 Agent 工具。
  - `tests/test_quiz.py`: 36 个测试覆盖 schema、store、evaluator、generator、review、tool 集成。

- **Session 命名与恢复**: Session 新增 `name` 字段，支持给 session 起名字。
  - `core/session.py`: 新增 `name` 字段、`list_session_summaries()` 方法、旧格式向后兼容（缺 name 字段默认空字符串）。
  - `/session save [name]`: 保存时可选命名。
  - `/session resume`: 交互式选择恢复，显示序号列表。
  - `/session load <id|name>`: 支持按名称模糊匹配、ID 前缀匹配、精确匹配。
  - `/session list`: 显示名称、消息数、最后活跃时间。
  - 加载 session 后自动显示最近对话历史。
  - `tests/test_session.py`: 新增 4 个测试。

- 共新增 49 个测试（知识库 13 + 题库 36）。

### 变更
- **Quiz JSON 解析容错增强**: `quiz/generator.py` 的 `_parse_json_from_llm()` 改用括号深度追踪匹配 JSON 数组边界（替代 `rfind`），先尝试直接解析再做提取，增加尾逗号修复，解析失败时日志输出原始内容便于排查。
- **Quiz 错误信息改善**: `tools/quiz_tools.py` 出题失败时列出可能原因（知识库无资料 / 材料不足 / LLM 格式异常），并提示用 `/kb search` 验证。

### 修复
- **MiniMax 2013 错误**: `providers/minimax.py` 将所有 system message（base、skills、memory）合并为一条发送，MiniMax 只支持单条 system message。同时移除所有消息角色的 `name` 字段。
  - `tests/test_providers.py`: 更新断言，验证 system 消息合并和无 name 字段。

## [0.9.0] - 2026-05-13

### 变更
- **MiniMax Provider 重构**: `MiniMaxProvider` 改为继承 `OpenAICompatibleProvider`，复用通用 HTTP 请求、重试和流式解析逻辑，仅保留 MiniMax 特有的消息转换（`_convert_messages`）和 refusal 检测（`_parse_response`）。
- **工具路径解析收敛**: 将重复的 `_resolve_path()` 提取到 `tools/base.py`，`file_ops`、`dir_ops`、`obsidian_tool` 统一复用。

### 修复
- **RAG 文件读取句柄**: `rag/ingest.py` 的文本和 PDF 读取改为 `with open(...)`，避免文件句柄泄漏。
- **DeepSeek 空测试**: 为 `test_deepseek_provider_complete()` 增加实际 payload 断言，避免空测试误报通过。
- **Provider 导出**: `providers.__all__` 补充 `OpenAICompatibleProvider`。

## [0.8.0] - 2026-05-09

### 新增
- **持久化记忆系统**: Agent 能在会话间记住用户偏好、学习上下文和反馈，跨 session 持久化。
  - `core/memory.py`: `MemoryManager` 核心模块，支持 save/load/forget/search/build_memory_prompt。记忆以单独 Markdown 文件存储在 `.bobodan/memory/`，每个文件带 YAML frontmatter（name, description, type, created, updated）。自动维护 `MEMORY.md` 索引表。
  - `tools/memory_tools.py`: 新增 `memory_save` 和 `memory_recall` 两个 Agent 工具，LLM 可主动保存和检索记忆。
  - `rag/vector_store.py`: `LocalVectorStore` 新增 `upsert()` 增量更新和 `remove_by_source()` 按来源删除方法，支持记忆的增量向量索引。
  - `core/agent_loop.py`: 新增 `memory_prompt` 参数和 `_inject_memory_prompt()` 方法，使用 `MEMORY_MARKER` 防重复注入（与 skills 同模式）。
  - `cli/repl.py`: 新增 `/memory` 命令集（`list`/`show`/`search`/`forget`/`stats`），startup panel 显示 memories 计数。
  - `config.yaml`: 新增 `memory: { enabled: true, dir: ".bobodan" }` 配置节。
  - `graph/schema.py`: 新增 `Memory` 节点标签和 `REMEMBERS` 关系类型。
  - `tests/test_memory.py`: 33 个测试覆盖 frontmatter 解析、文件读写、向量搜索、工具调用、prompt 注入、REPL 命令。

## [0.7.0] - 2026-05-06

### 变更
- **CLI 流式 UI 重写**: 全面重写流式渲染，提升交互流畅度。
  - **打字机效果**: 文本逐字符输出（~12ms/字符），完整行带内联 Markdown 渲染（加粗、代码、列表、表格、引用、标题），部分行实时预览。
  - **Thinking 动画**: `⠋ thinking` 旋转 braille 字符，文字到来时无缝消失（`\r\033[2K` 清除），无内容时自动恢复。
  - **紧凑工具调用**: `⏺ tool_name(args)` 格式替代 Rich 标签，结果预览 `✓/✗` + 80 字符摘要，不打断文本流。
  - **简化用户消息**: `> 用户输入` 前缀替代 Rich Panel，移除 `> assistant` 标题。
  - `cli/markdown_render.py`: 移除 `print_user_message` 和 `print_assistant_header`。
  - `cli/repl.py`: 重写 `_flush_stream_buffer`（typewriter + markdown）、`run_agent_streaming`（thinking/工具/部分行状态机）、thinking 动画方法。
  - `tests/test_repl.py`: 断言从 `"THINK"` 更新为 `"thinking"`。
- **工具调用默认显示**: `show_tool_calls` 默认值改为 `True`。
- **REPL UI 开关命令**: `/ui`、`/ui tools on`、`/ui tools off` 可切换工具调用显示。

### 修复
- **MiniMax 兼容性**: 移除遗留基础 system prompt 注入，避免 MiniMax 请求触发 `invalid chat setting (2013)`。

## [0.6.0] - 2026-04-30

### 新增
- **Rich CLI 渲染**: Agent 回复中的常见 Markdown 会通过 Rich 渲染为更易读的终端格式，不再原样显示 `###` 标题、代码围栏和表格分隔行。`/kb status` 和 `/kb search` 改为 Rich 面板/表格展示，并保留内置轻量 fallback。
- **启动页 Rich 面板**: REPL 启动界面改为 Rich Panel + grid 表格，避免手写框线在中文、长路径或窄终端下错位，并提示输入 `/` 查看命令建议。
- **Slash-command 实时提示**: REPL 接入 `prompt_toolkit`，输入 `/` 时显示可用命令候选；如果终端不支持实时提示，输入 `/` 回车会显示精简命令面板。
- **`/kb` 知识库命令入口**: 新增 REPL 直连命令，不依赖模型猜工具即可同步、检索和查询图谱。
  - `/kb sync <vault> [course_dir] [--full]`: 同步 Obsidian vault 和可选课程资料目录。
  - `/kb status`: 查看 `.knowledge/` 文件数、chunk 数、节点数、关系数和图谱后端。
  - `/kb search <query> [--course name] [--top-k n]`: 直接检索本地 RAG 索引。
  - `/kb graph <concept> [--intent related] [--limit n]`: 直接查询知识图谱关系。
  - `/kb reset --yes`: 删除生成的 `.knowledge/` 索引，不删除原始笔记或资料。
- **RAG + 知识图谱学习助手 MVP**: 新增面向课程学习的本地知识库闭环。
  - `obsidian/`: 扫描 Obsidian vault，解析 Markdown frontmatter、标题、`[[双链]]`、alias、tag、文件 hash。
  - `rag/`: 支持 Markdown/TXT/PDF 文档导入、文本切块、本地轻量 sparse vector 检索、引用结果格式化。
  - `graph/`: 新增知识图谱 schema、本地 JSON 图谱存储，以及可选 Neo4j adapter。未配置 Neo4j 时自动回退到 `.knowledge/graph_store.json`。
  - `tools/obsidian_tool.py`: 新增 `obsidian_sync`，同步 Obsidian 笔记和可选课程资料目录到 `.knowledge/`。
  - `tools/rag_search.py`: 新增 `rag_search`，返回 `results[{text, source, score, metadata}]`。
  - `tools/graph_query.py`: 新增 `graph_query`，支持 `related`、`tags`、`mentions`、`course`、`prerequisites` 等查询意图。
  - `skills/course-learning/SKILL.md`: 新增课程学习助手 skill，引导 Agent 根据问题类型选择 RAG、图谱或组合查询。
  - `docs/RAG_KNOWLEDGE_GRAPH_ASSISTANT.md`: 新增完整设计文档。
  - `docs/RAG_KNOWLEDGE_GRAPH_MVP.md`: 新增 MVP 使用说明、数据流、工具接口和演示步骤。

### 变更
- **README**: 补充课程学习助手 MVP 的用途、项目结构、快速演示和工具说明。
- **CLAUDE.md**: 补充 `obsidian/`、`rag/`、`graph/`、`.knowledge/` 的目录约定和运行数据规则。
- `.gitignore`: 忽略 `.knowledge/` 本地索引目录。
- `requirements.txt`: 新增 `pypdf>=4.0`（PDF 文本抽取）、`prompt_toolkit>=3.0`（slash-command 提示）、`rich>=13.0`（Markdown 渲染）。

### 验证
- 全部 123 个测试通过。

## [0.5.0] - 2026-04-29

### 新增
- **Skills 系统**: 新增 skills 功能，仿照 OpenClaw 的 skills 架构。每个 skill 是 `skills/` 目录下的子文件夹，包含 `SKILL.md`（YAML frontmatter + Markdown 指令）。
  - `core/skills.py`: skill 加载、frontmatter 解析、XML prompt 格式化。
  - `cli/repl.py`: 新增 `/skill` 命令（`list` / `<name>` / `run <name>`）。
  - `core/agent_loop.py`: 支持 `skills_prompt` 参数，首次 LLM 调用前注入 system message。
  - `core/session.py`: `_trim_messages()` 保留首条 system message 不被裁剪。
  - `config.yaml`: 新增 `skills.enabled` 和 `skills.dir` 配置节。
  - `skills/weather/SKILL.md`: 示例天气查询 skill。
  - `tests/test_skills.py`: 18 个单元测试覆盖 frontmatter 解析、skill 加载、prompt 格式化。

### 修复
- **MiniMax tool_call id not found (2013)**: 根因是消息顺序问题——MiniMax 要求 `assistant(tool_calls)` 出现在 `tool` 消息之前。Session 存储顺序为 `tool → assistant(tool_calls)` 但 MiniMax 需要反过来。在 `providers/minimax.py` 中重新排序消息修复。

## [0.4.0] - 2026-04-27

### 新增
- **CLI 流式输出**: OpenAI-compatible 和 MiniMax provider 新增 SSE 流式响应，支持增量解析 tool call delta，并正确累积工具参数。
- **Agent 过程事件**: 新增 `AgentLoop.run_stream()`，输出 assistant delta、工具开始、工具结束和最终回复事件，让 CLI 能展示 agent 正在做什么，而不是静默等待。
- **REPL 工具调用可见**: Agent 运行过程中显示工具名、参数摘要和成功/失败状态。
- **Provider 重试逻辑**: `OpenAICompatibleProvider` 和 `MiniMaxProvider` 的 `complete()` 方法增加指数退避重试。覆盖连接错误、超时、5xx、429。4xx（除 429）不重试，直接抛出清晰错误。
- **CLI 超时控制**: `run_agent()` 增加 per-turn 超时（默认 300s，来自 `agent.timeout` 配置）。超时后打印提示，不写入不完整 session。线程设为 daemon，主进程可干净退出。
- **Provider 配置校验**: `_validate_provider_config()` 校验 provider 类型、`api_key_env` 字段、环境变量是否设置。错误信息包含支持的类型列表和修复建议。
- `requirements.txt` + `requirements-dev.txt`: 核心依赖 `httpx`、`PyYAML`、`python-dotenv`；开发依赖 `pytest`。

### 变更
- **REPL 回复渲染**: 流式阶段改为批量消费事件，并按完整行/长段落阈值增量写入，不再每个 delta 都重绘完整 Markdown 文档，减少长回复时的卡顿。
- **流式 Markdown 清洗**: 流式输出会轻量处理标题、粗体、行内代码、列表和 Markdown 表格，避免用户看到原始 `**`、表格分隔行等格式标记。
- **CLI 主题降噪**: 去掉高饱和橙色/紫色强调色，改用白色、灰色、青色和绿色，让输出更容易扫读。

### 修复
- **CLI 乱码 UI 文案**: prompt 和启动面板中的中文应用名改为英文 `bobodan`，工具状态图标和分隔线改为更适合 Windows 终端的 ASCII 文本。
- **回复和 prompt 重叠**: 流式输出结束后强制补齐换行，避免下一轮输入提示贴在回复末尾。

### 验证
- 全部 80 个测试通过。

## [0.3.0] - 2026-04-27

### 新增
- **`ToolResult` 结构化返回**: 新增 `ToolResult(ok, content, data)` 数据类。所有工具返回 `ToolResult`，程序逻辑用 `ok` 和 `data` 判断状态，给 LLM 的 tool message 仍用 `content` 字符串。
- **Workspace 安全边界**: `tools/base.py` 新增 `_is_within_workspace()` 路径校验，工具只能访问 workspace 根目录内路径。新增 `_is_denied_path()` 拒绝列表，默认拒绝 `.env`、`.git`、`.session`、`__pycache__`、`.venv`。
- **`read_file` 保护**: 增加文件大小限制（1 MB）、二进制文件检测、workspace 边界检查、deny list 检查。
- **`write_file` 覆盖保护**: 新增 `overwrite` 参数，默认 `false`。已有文件需传 `overwrite=true` 才能覆盖。
- `tests/test_file_ops.py`、`tests/test_dir_ops.py`、`tests/test_tool_base.py`: 新增 deny list、binary 检测、大小限制、覆盖保护、workspace 边界等测试。

### 变更
- `tools/base.py`: `execute_tool()` 返回 `ToolResult` 替代 `Any`。自动将非 `ToolResult` 返回值包装为 `ToolResult(ok=True, content=str(result))`。注入 `workspace` 参数。
- `tools/dir_ops.py`: `change_dir` 通过 `data["cwd"]` 返回新路径，`_sync_session_state` 直接读取。
- `core/agent_loop.py`: `_sync_session_state` 使用 `ToolResult.data["cwd"]` 替代中文前缀解析。

## [0.2.0] - 2026-04-27

### 新增
- **`providers/types.py`**: 新增统一内部类型 `ToolCall(id, name, arguments)` 和 `LLMResponse(content, tool_calls)`。所有 provider 返回同一类型，`AgentLoop` 不再依赖 duck typing。
- **`providers/openai_compat.py`**: 新增 `OpenAICompatibleProvider` 基类，封装 OpenAI 兼容 API 的消息转换、HTTP 请求和响应解析。Deepseek 和 OpenAI provider 均继承此类。
- `tests/test_providers.py`、`tests/test_agent_loop.py`: 覆盖类型转换、多 tool call、消息顺序等。

### 变更
- **`providers/deepseek.py`**: 从 LangChain wrapper 改为继承 `OpenAICompatibleProvider`，移除 `langchain_openai` 依赖。同时修复了多 tool call 丢失 bug（原代码只取 `tool_calls_data[0]`）。
- **`providers/minimax.py`**: 返回 `LLMResponse` 替代 ad-hoc `Response` 类。使用共享 `ToolCall` 类型。
- **`providers/factory.py`**: `openai` 分支使用 `OpenAICompatibleProvider` 替代 `DeepseekProvider`，职责清晰。
- **`core/agent_loop.py`**: 直接访问 `LLMResponse.tool_calls` 和 `ToolCall.id/name/arguments`，移除所有 `hasattr` 和 `isinstance(tc, dict)` duck typing。

## [0.1.0] - 2026-04-22

### 新增
- **`.gitignore`**: 排除 `.env`、`.session/`、`.venv/`、`__pycache__/`、`.pytest_cache/` 等运行产物，防止敏感文件和缓存进入版本库。

### 修复
- **Tool call 消息顺序修正**: `core/agent_loop.py` 原代码先执行工具、添加 `tool` 消息，最后才添加 `assistant(tool_calls)`，形成 `user → tool → assistant(tool_calls)` 的错误顺序。现在改为：先解析 tool calls → 添加 `assistant(tool_calls)` → 再执行工具并添加 `tool` 消息。顺序始终为 `user → assistant(tool_calls) → tool`。
- **Session 裁剪保护 tool call 组**: `core/session.py` 重写 `_trim_messages()`，新增 `_group_messages()` 方法。消息按"对话轮次"分组：`assistant(tool_calls)` 和对应 `tool` 消息作为原子单元，裁剪时要么一起保留要么一起移除。
- `tests/test_repl.py`: 更新断言匹配实际 REPL 输出。

### 验证
- 全部 50 个测试通过。
