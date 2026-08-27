# Bobodan 体验优化轮（分支 refactor/perf-2026-08，轻后端）

## 审查结论摘要

三路探索发现的核心问题（按影响排序）：
1. **弹窗层是最大交互缺陷**：11 个浮层各自手写 backdrop（5 种视觉配方），一半不支持 Esc、全部无焦点陷阱；ProviderManager 嵌套在 Settings 里时两层 window keydown 监听互相竞态——按一次 Esc 两层同时关。
2. **动效无体系**：9 种时长、3 条贝塞尔曲线、4 种入场机制并存；`Collapse/SlideIn/AnimatedList` 是零消费的死代码；应用内「减少动效」开关实际只覆盖 4 个选择器，与 OS 级语义不一致（JS 只在挂载时读一次 matchMedia）。
3. **品牌资产大量闲置**：hero 图完全未接线（MASCOT.md 本就指定给 Chat 首页）；`friendly` 表情从未使用；部分空状态退化成 SearchX 图标；失败消息仍是中性脸；两套 Loading 反馈不统一（品牌插画版 vs 通用转圈）。
4. **流畅度断崖**：Chat 有 StreamBuffer/贴底滚动全套，Practice 问 AI 却是裸字符串拼接无缓冲无 Markdown；Library/Reader 切换文档整个区域闪成转圈再重建；KnowledgeMapPage 每次 graphRevision 变更都整建 Sigma 渲染器并重放 500ms 入场 + 相机复位。
5. **可发现性**：Ctrl+N 在 UI 上展示但从未实现；Reader Shift+J/K、KM +/- 快捷键无处可见；破坏性操作全用原生 window.confirm。

## 实施包（每包独立提交、独立可验证）

**A. ui/Modal 公共基元 + 全部浮层迁移**
- 新建 `ui/Modal.tsx`：单一 backdrop 配方、220ms 入场（DESIGN.md §11）、Esc 关闭带层级栈（只关最顶层，修嵌套竞态）、焦点陷阱 + 关闭后焦点归还、`prefers-reduced-motion` 降级。
- 迁移：SettingsDialog / MemoryManagerDialog / ProviderManagerDialog / OnboardingDialog（保持不可 Esc，但补显式"跳过"出口）/ LibrarySetupDialog / KnowledgeMapPage 两个 Add 弹窗 / CandidateReviewPanel / wiki-editor / DocumentEditor 遮罩。删除 5 种 backdrop 配方。

**B. 动效体系收敛**
- 定义 `--dur-fast/base/slow`(120/160/220ms) 并替换浮层/按钮字面量；复用既有两条 easing token，消灭第三条曲线和 `transition: all`；去重 `spin` keyframes；slash/mention palette 与 Modal 统一入场机制（去掉 @starting-style 的浏览器兼容悬崖）。
- 删除零消费的 `SlideIn/Collapse/AnimatedList`；BobodanProcess 状态图切换不再 `key={state}` 重挂载（160ms opacity 交叉淡入，消除微闪烁）。

**C. 应用内减少动效 = OS 级语义**
- `[data-motion="reduced"]` 下施加与全局媒体查询一致的装饰性动画停用（保留必要透明度反馈）；GraphCanvas/useChatStream 改为监听 matchMedia change 事件实时生效。

**D. 品牌形象全面接入**
- Chat 欢迎/Today 视图改用 hero 双分辨率 `<picture>`（MASCOT.md §4 的指定用途与官方代码片段）；
- `friendly` 表情接入欢迎语/引导完成态；失败消息用 `curious` 表情区分于成功；
- 补齐缺品牌状态的空状态（Library 片段空、Reader 不存在等）并让 NotesPage 复用共享 EmptyState；
- LoadingState 增加插画变体，ReviewPage/NotesPage/KnowledgeMap 加载态统一为品牌版本（尺寸稳定、骨架先行）。

**E. 流程清晰与可发现性**
- 实现 Ctrl+N 新建对话；Reader 顶栏与 KM 工具栏加 kbd 快捷键提示；
- 新增 ShortcutsDialog（基于新 Modal，汇总现有 4 套快捷键词汇表）从设置页可达。

**F. 加载平滑**
- Library 列表/详情与 Reader 文档切换改为 stale-while-revalidate（保留旧内容 + 轻遮罩），消除空白闪烁；
- Practice「问 AI」接入 StreamBuffer + ReactMarkdown，与 Chat 同观感；
- GraphCanvas 数据更新改为增量刷新：保留相机状态与节点位置、只在首次挂载播放入场动画（graphRevision 审查流程不再整卡）；
- Practice 生成/批改等待态保持表单尺寸稳定（DESIGN.md §9 要求核对）。

**G. 体验审查遗留快赢（前端 2 + 后端 1）**
- ReviewPage 使用后端已返回但被丢弃的 `mastery_changes` 掌握度数据（2026-08-01 审查 P1-5）；停止生成后显示「已停止」标记（P1-7，若 termination_reason 事件已携带则纯前端）；
- 后端：概念提取孤儿 `running` 运行的启动恢复扫描标记为 interrupted（P0-4，含测试）。

## 验证

每包：vitest 相关单测 + lint + build。收尾全量：pytest（基线 1365）、vitest、`npm run test:e2e` 冒烟、真实启动走查关键浮层/流式/图谱刷新路径。DESIGN.md 动效 token 小节同步补充，CHANGELOG 记录。

## 明确不做（本轮）

wiki 端点去重、kb_service/kb.py 拆分、FE-2 流式 reconcile、FE-4 配方4/5 与 forceAtlas2 worker、导入进度条/拖拽、og/manifest 元数据——均已记录，留给后续功能窗口或 P5G.2 Electron 主线（本分支完成后我的建议即回主线）。