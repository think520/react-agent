# Bobodan Library 重构 + 图谱编辑任务书

> 交付对象：执行 agent（DeepSeek harness 或同等能力）
> 版本：v1.0（2026-08-11）
> 已确认决策：布局方案 A（列表页/阅读页分离）+ openhanako 三件套；编辑方案 A（入口快修）+ B（图谱编辑）；C（AI 协作图谱）后置，本轮不做

## 0. 任务总览

1. **布局方案 A**：Library 拆成列表页与阅读页两个路由，解决"列表与正文固定分屏打架"。
2. **openhanako 三件套**：多文档 tab、章节导轨、选中文字浮出动作，带进阅读页。
3. **编辑入口（方案 A）**：列表行内 + 阅读页顶部的"编辑"按钮（Markdown/文本类资料）。
4. **图谱编辑（方案 B）**：概念编辑（改名/定义/别名/笔记）、关系删除、关系添加，后端 API + 前端 UI + 测试。

## 1. 必读文档（按顺序）

- `CLAUDE.md`：项目工作规则、架构边界、编码纪律。所有改动必须遵守。
- `docs/PROJECT_GUIDE.md`：产品定位、数据边界（原始资料是 truth source、知识地图只含已审查概念）、阶段纪律。
- `docs/DESIGN.md`：视觉硬约束。**注意反模式清单明确排除 "Linear/Raycast 式极客工具风"**，方案只借交互不借视觉。颜色 token 不得新增，动效遵守 160-220ms 规范。
- MiaoYan 参考：https://github.com/tw93/MiaoYan （分栏编辑预览 + 60fps 双向滚动同步 + `⌘\` 切换；极简密度原则：导航窄、界面状态切换快捷键化；仓耳今楷与 Bobodan 审美同源）

参考实现（openhanako 源码，本地目录 `F:\claude projects\openhanako-reference`）：

- 多文档 tab：`desktop/src/react/components/chat/TabBar.tsx`（点击切换 / 双击关闭 / 滚轮横滑 / 整体折叠按钮）
- 章节导轨：openhanako 的 ChapterRail（右缘 64px 悬停热区 `CHAPTER_RAIL_HOVER_ZONE_PX = 64`，平时隐身，hover 弹出目录）
- 选中文字浮出动作：`SelectionQuoteActionSurface` + selection-actions（选中正文文字浮出"引用"动作，带到输入框）
- 预览面板结构：`PreviewPanel.tsx` + `Preview.module.css`（`--preview-panel-width` 可拖拽调宽、折叠后 `width: 0`）

现状代码（必须精读再动手）：

- `web/frontend/src/pages/LibraryPage.tsx`（约 1000 行单体页面：列表 + 阅读 + Wiki 维护 + 概念提取全在里面；已有 `selectionQuote` 雏形、`readingOpenedRef` 阅读计时、`relatedNotes` 联动）
- `web/frontend/src/App.tsx`（路由：`<Route path="library" element={page(<LibraryPage />)} />`）
- `web/frontend/src/components/DocumentEditor.tsx`（已有编辑弹窗：检查点 / 10 版历史 / 哈希冲突三选项 / 回滚，直接复用）
- `web/frontend/src/components/ConceptSidebar.tsx`（概念详情侧栏：信息 / 关系 / 原文摘录 / 个人笔记，加编辑能力）
- `web/frontend/src/pages/KnowledgeMapPage.tsx`（图谱页，已有 CandidateReviewPanel 候选审查、`loadGraph()` 重载机制）
- `graph/concept_store.py`（表结构见下，已有 `delete_concept` / `delete_relationship`，**缺 update_concept 与 create_relationship**）
- `web/backend/routers/kb.py`（已有文档编辑端点 `PATCH /documents/{id}`、版本回滚、提案端点，图谱端点加在这里）

## 2. 任务 1：布局方案 A（列表页 / 阅读页分离）

### 路由

- `/library`：资料列表页（书架）。
- `/library/read/:id`：阅读页（书桌）。阅读页顶部细条：`← 返回资料库`（恢复列表滚动位置）｜上一份 / 下一份｜`编辑`（md/txt 时显示）｜章节位置。
- 浏览器前进 / 后退天然支持列表 ↔ 阅读切换。

### 列表页（/library）

- 保留现有能力：搜索、collection 切换（material/wiki）、索引状态（提取状态 / 待审查数 / 内容已更新）、概念数、整理时间、删除（归档）、提取概念入口、导入、资料库管理。
- 每行加"编辑"按钮（`kind` 为 md/txt/markdown 时显示），点击直接打开 DocumentEditor。
- 点击文档行 → 整页切换到阅读页（路由跳转），不再并排。

### 阅读页（/library/read/:id）

- 正文：复用现有 sections 渲染（`reader-prose` + ReactMarkdown + remarkGfm、chunk 高亮、`captureSelection`），正文居中限宽 720-760px，符合暖纸面排版。
- 顶部细条：返回 / 上一份 / 下一份（同 collection 内顺序循环，`Shift+J/K` 或 `Alt+←/→`）/ 编辑按钮 / 概念提取状态快捷入口（保留现有 "提取概念 / 审查概念 / 查看图谱" 按钮组）。
- 选中文字浮出动作条（任务 2 第三件套），复用并增强现有 `selectionQuote` + `selection-toolbar`。
- 相关笔记（relatedNotes）平移到阅读页。
- 阅读计时 `readingOpenedRef` 逻辑平移。
- 滚动位置：返回列表时恢复列表滚动位置；切换文档时各自保留滚动位置（多 tab 见任务 2）。

### 键盘

- 列表页：`J/K` 上下移动选中、`Enter` 打开。
- 阅读页：`Esc` 返回列表、`Shift+J/K` 切上一份/下一份、`[`/`]` 开关章节导轨。

### 移动端

- 路由切换天然兼容窄屏，不需要分屏；阅读页顶栏在窄屏下压缩为：返回 + 标题 + 编辑。

## 3. 任务 2：openhanako 三件套（阅读页增强）

### 3.1 多文档 tab

- 阅读页顶部（顶栏下方）一条 tab 栏：打开过的文档各占一个 tab，点击切换、双击关闭、滚轮横滑、右侧整体折叠按钮（折叠后只留当前文档，展开恢复）。
- **每个 tab 保留自己的滚动位置**（切换不丢进度）。
- 参考 openhanako `TabBar.tsx` 的交互；视觉按 DESIGN.md 重画（纸面 tab，不是极客风）。
- tab 状态可放前端 store（zustand）或本地组件状态 + URL 参数（`/library/read/:id?open=a,b,c&active=c`），推荐 store + URL 双写，刷新不丢。

### 3.2 章节导轨

- 阅读页右缘 64px 悬停热区：指针靠近右缘弹出章节导轨（该文档所有 heading 列表，点击跳转到对应 chunk，高亮闪烁），平时完全隐身不占宽度。
- 参考 openhanako ChapterRail；跳转复用现有 chunk 高亮机制（`setHighlightedChunk`）。

### 3.3 选中文字浮出动作

- 正文选中文字 → 浮出动作条：`带到对话`（携带引用跳到 Chat，复用现有 `selectionQuote` + `askAboutSelection`）/ `基于此出题`（带上下文创建练习，复用现有 practice 创建链路）/ `高亮`（可选，先做前两个）。
- 参考 openhanako `SelectionQuoteActionSurface`（`scheduleCaptureSelection` / `getSelectionCommitAnchorRect` 的定位逻辑），视觉按 DESIGN.md。

## 4. 任务 3：编辑入口 + 分栏编辑器升级（方案 A + MiaoYan 借鉴）

> 借鉴来源：MiaoYan（https://github.com/tw93/MiaoYan）的分栏编辑预览：编辑区/预览区并排，60fps 双向滚动同步，`⌘\` 快速切换分栏。它明确不做 Typora 式即时预览（追求纯粹的 Markdown 编辑体验），这个产品决策直接采用：编辑就是编辑，预览并排但分离。

### 4.1 编辑入口

- 列表页：文档行内"编辑"按钮（md/txt/markdown 才显示）。
- 阅读页：顶栏"编辑"按钮（同条件显示）。
- 两处都打开现有 `DocumentEditor` 组件（含 expected_hash 冲突检测、三选项：覆盖外部修改 / 放弃 / 另存为新文件）。

### 4.2 分栏编辑器升级（DocumentEditor 重构）

现有 `DocumentEditor.tsx` 是纯 textarea，升级为分栏编辑预览：

- **布局**：左编辑区（textarea 保留，或按需升级为轻量 CodeMirror）+ 右预览区（复用现有 ReactMarkdown + remarkGfm 渲染，样式与阅读页正文一致：暖纸面、居中限宽）。
- **双向滚动同步**：60fps（rAF 节流）scroll 事件映射，按滚动比例双向同步（编辑区滚动 → 预览区对应位置，反之亦然）；同步可临时暂停（用户正在主动滚动一侧时不强拉）。
- **模式切换**：`Ctrl+\`（Web 端对应 MiaoYan 的 `⌘\`）在"分栏 / 纯编辑"间切换，预览可隐藏。
- **保留**：检查点 / 最近 10 版历史 / 回滚 / 哈希冲突三选项 / 保存后刷新。
- **视觉**：分栏分隔线细、可拖拽调宽（参考 openhanako PreviewPanel 的 `--preview-panel-width` 模式）；整体符合 DESIGN.md 纸面风格，不做玻璃拟态。

### 4.3 保存后行为

- 保存成功后：刷新当前文档 sections（重新拉取 `api.document(id)`），提示"资料已更新，索引将同步"。

## 5. 任务 4：图谱编辑（方案 B）

### 5.1 后端

`graph/concept_store.py` 新增：

- `update_concept(concept_id, *, name=None, definition=None, aliases=None, note=None) -> dict`：改名时校验 UNIQUE(name COLLATE NOCASE) 冲突（冲突返回明确错误）；`concept_id` 不变，证据 / 关系 / 位置全部保留；更新 `updated_at`。
- `create_relationship(from_id, to_id, rel_type, note="") -> dict`：校验两个概念都存在、`from_id != to_id`（禁自环）、同向同类型重复时返回"已存在"错误（不静默跳过）；`rel_type` 限定枚举 `属于|前置知识|组成部分|对比|应用于|来源于|user:custom`；`evidence_level='user'`（用户手动作的关系，区别于 source/cross/ai）；返回新 rel_id。
- `delete_relationship(rel_id) -> bool`：已有实现，确认级联删除 evidence 的行为即可复用。

`web/backend/routers/kb.py` 新增端点（与文档编辑端点同文件，风格一致，`unwrap_service_result` 信封）：

- `PATCH /api/kb/concepts/{concept_id}`：body `{name?, definition?, aliases?, note?}`（至少一项）。
- `POST /api/kb/relationships`：body `{from_id, to_id, rel_type, note?}`。
- `DELETE /api/kb/relationships/{rel_id}`。
- 错误码：`concept_not_found` / `concept_name_conflict` / `relationship_exists` / `self_relationship` / `invalid_rel_type`。

### 5.2 前端

`KnowledgeMapPage.tsx` + `ConceptSidebar.tsx`：

- **编辑概念**：ConceptSidebar 顶部或信息区加"编辑"按钮 → 打开编辑表单（name / definition / aliases / note），保存调 `PATCH` 后刷新侧栏与图谱（复用 `loadGraph()` 与详情刷新）。
- **删除关系**：ConceptSidebar 关系列表每项加删除按钮（二次确认），调 `DELETE` 后刷新。
- **添加关系**：ConceptSidebar 关系区底部"添加关系"按钮 → 表单（选择目标概念：搜索已有概念下拉 + 关系类型下拉 + 可选备注），调 `POST` 后刷新。
- 所有写操作后同步刷新图谱与候选状态；错误提示使用现有 toast/notice 机制。

### 5.3 测试

- 后端单元测试（新文件或追加 `tests/test_concept_store_edit.py`）：
  - update_concept 改名成功、改名唯一冲突、definition/aliases 更新、concept_id 不变且证据关系保留。
  - create_relationship 成功、自环拒绝、重复关系拒绝、非法 rel_type 拒绝、缺失端点概念拒绝。
  - delete_relationship 级联删除 evidence。
- 前端：新增组件若有逻辑可测则补 vitest；至少保证现有测试不回归。
- 端点测试：PATCH / POST / DELETE 三端点 happy path + 错误码各一条。

## 6. 验收标准

1. `/library` 与 `/library/read/:id` 路由分离；返回列表恢复滚动位置；移动端可用。
2. 多文档 tab 切换不丢滚动位置；章节导轨悬停弹出可跳转；选中文字浮出动作可带到对话 / 出题。
3. 列表行内与阅读页顶部编辑入口可见可用；保存后文档内容刷新。
4. DocumentEditor 分栏编辑预览：编辑/预览并排、双向滚动同步、`Ctrl+\` 切换、检查点与版本回滚保留。
5. 图谱：概念改名 / 加关系 / 删关系全链路可用，数据落库正确，图谱与侧栏即时刷新。
6. 测试全绿：`pytest`（基线 1343 passed）+ vitest + `npm run lint` + `npm run build`。
7. DESIGN.md 合规：不新增颜色 token、不引入 Linear 风、动效遵守规范；`web/backend/events.py` 对外 SSE 事件契约不变。

## 7. 编码纪律

- 只做与任务相关的最小改动，不顺手重构邻近代码。
- 修改前先写回归测试复现目标行为。
- 不删除用户数据；`.bobodan/`、`.knowledge/` 历史数据不动。
- 文件编辑保留用户已有未提交改动。
- 本机环境：`.venv\Scripts\python.exe`（Python）、`web/frontend` 下 `npm`（前端）。
- 涉及图谱写入必须遵守"知识地图只包含用户已审查的概念和关系"：用户手动编辑即视为用户级确认，写入 `evidence_level='user'`，不得静默修改 AI 提取内容，所有编辑走显式用户操作。

## 8. Git 流程

1. 从当前分支（`feat/optimization-plan`）分出新分支：`feat/library-rework`。
2. 按任务拆分 commit，英文 conventional prefix（如 `feat(web): split library list and reader routes`、`feat(core): concept update and relationship create APIs`、`test(core): concept edit unit tests`）。
3. 不提交 API key、个人配置、`.knowledge/`、构建产物。
4. 完成后提交到本地分支。**推送需要用户明确授权**：用户说"推送"再执行 `git push -u origin feat/library-rework`。

## 9. 最终报告格式

- 每个任务（1-4）完成状态与验收证据（测试数、关键测试名）。
- 新增/修改文件清单。
- 分支与 commit 列表。
- 遗留事项与建议。
