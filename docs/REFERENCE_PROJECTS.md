# 参考项目（本地克隆）

> 版本：v1.0（2026-09-10）
> 定位：**遇到 bug 或设计问题时，先在这里找同构实现，再决定怎么做。**
> 本文不是路线图，不产生排期；排期只看 [`ROADMAP.md`](ROADMAP.md)。
> 机制精讲见 [`Bobodan参考项目调研报告.md`](Bobodan参考项目调研报告.md)；本文是**索引与使用说明**。

---

## 0. 本地克隆

| 项目 | 本地路径 | 版本 | 最后提交 | 许可证 | 一句话定位 |
|---|---|---|---|---|---|
| **DeepTutor** | `F:\claude projects\DeepTutor` | HEAD `6e6e56a` | 2026-09-02 | Apache-2.0 | 与 Bobodan 最同构的学习 Agent：Agent 循环契约、暂停/恢复、掌握度引擎、出题管线、题库 |
| **OpenMAIC** | `F:\claude projects\OpenMAIC` | `1.0.0`，HEAD `f760f58` | 2026-09-02 | MIT | 教育 Agent 系统：前端流式与过程可视化、交互卡、技能系统、e2e 纪律 |
| **openhanako-reference** | `F:\claude projects\openhanako-reference` | `0.450.0`，HEAD `1d3ef308` | 2026-08-22 | Apache-2.0 | 审美与工程外围的标杆：事件总线、会话恢复、记忆编译、权限与配置、桌面壳 |

> 三份都是本地克隆，**可能不是最新版本**。引用时请带上本表的 HEAD，结论要按读到的代码为准。

---

## 1. 遇到问题时怎么用

1. **先搜同构实现**（不要先自己想）：

   ```powershell
   rg -n "<关键词>" "F:\claude projects\DeepTutor" -g "!node_modules"
   rg -n "<关键词>" "F:\claude projects\OpenMAIC" -g "!node_modules"
   rg -n "<关键词>" "F:\claude projects\openhanako-reference" -g "!node_modules"
   ```

2. **读它的机制，重点看失败/降级/恢复路径**，不只看 happy path。
3. **映射到 Bobodan 的架构**（Python + FastAPI + SQLite + React/SSE），不照搬技术栈。
4. **落一条案例**到本文第 3 节：问题 → 参考做法 → Bobodan 结论。

---

## 2. 各自的强项（按问题类型找）

| 问题类型 | 优先看 | 已知入口 |
|---|---|---|
| Agent 循环契约、暂停/恢复、交互协议 | DeepTutor | `deeptutor/core/tool_protocol.py`、`deeptutor/agents/chat/agent_loop.py`、`deeptutor/api/contracts/turn_protocol.py` |
| 出题管线、题库/错题库、掌握度引擎 | DeepTutor | `deeptutor/capabilities/mastery/`、`deeptutor/learning/` |
| RAG 索引版本化、心跳守卫、评测 | DeepTutor | `deeptutor/services/rag/`、`deeptutor/pipelines/` |
| 前端流式渲染、过程折叠、工具卡 | OpenMAIC / openhanako | `OpenMAIC/` 前端、`openhanako-reference/desktop/src/react/components/chat/` |
| 交互卡（选项卡/多题/自由文本） | DeepTutor + OpenMAIC | `deeptutor/tools/ask_user.py`、`web/lib/ask-user-state.ts`、`OpenMAIC/lib/server/agent-runtime/ask-user.ts` |
| 会话恢复、事件总线、断线续流 | openhanako | `openhanako-reference/hub/`、`server/`、`lib/pi-sdk/stream-guard.ts` |
| 记忆编译、个人知识分层 | openhanako | `openhanako-reference/lib/memory/` |
| 权限、沙盒、确认卡（含超时） | openhanako | `lib/approval-gateway.ts`、`lib/tools/session-permission-wrapper.ts`、`core/mcp/manager.ts`（`confirmStore`） |
| 配置、Provider、设置搜索 | openhanako | `lib/config.example.yaml`、`desktop/src/react/settings/` |

---

## 3. 已确认的同构案例

### 案例 1：agent 提问 → 用户作答 → agent 继续（2026-09-10）

背景：Bobodan 的 `ask_user` 交互卡需要决定「用户作答后如何回到 agent」。三份参考给出了**三种结构不同的答案**，而 Bobodan 当时的实现（把答案当作新用户消息、或只记录不续跑）都不在其中。

| 项目 | 机制 | 关键代价 |
|---|---|---|
| **OpenMAIC** | `ask_user` 发出问题信封后**直接结束本轮 run**；用户的**下一条普通消息**就是这个答案（`lib/server/agent-runtime/ask-user.ts`） | 回合边界清晰、实现最省；但答案会以真实用户消息进入 transcript |
| **DeepTutor** | `ToolResult.pause_for_user` → 循环 `await` 一个 **reply queue** → 把答案**回填进对应的 `role=tool` 消息** → `continue` **同一轮**（`core/tool_protocol.py:137-153`、`agents/chat/agent_loop.py:541-553`） | 语义最准：不产生假用户消息，保留 `assistant → user → assistant` 时序；代价是要有 turn 注册表 + `subscribe_turn` / `resume_from` 重放（`api/contracts/turn_protocol.py`） |
| **openhanako** | `confirmStore.create(kind, payload, sessionPath, TIMEOUT)` 返回 `{confirmId, promise}`，工具**await 这个 promise**；通过事件流发 `session_confirmation`（`status: pending`）给 UI，UI 作答后 resolve（`core/mcp/manager.ts:1892-1920`） | 天然带**超时**与 `confirmId`；但是**进程内 promise** 模型，适合桌面；跨进程/可重启的 Web 后端要改成持久化 + 唤醒 |

**共同结论（Bobodan 可借鉴的三条）**：

1. 答案应该是**对那个工具调用的回填（tool result）**，不是一条新的用户消息；
2. 「暂停」需要一个**持久化的挂起记录 + 可恢复的续跑**，不能只靠一个开着的 HTTP 连接；
3. 每个挂起交互都必须有**超时**与**放弃语义**（DeepTutor 的 `completed=False`、openhanako 的 `TIMEOUT`）。

**Bobodan 结论**：待定（正在与维护者确认落地方案）。

---

### 案例 2：资料库文件树 + 分栏阅读（2026-09-24）

背景：Bobodan 的 Library 是一张平铺列表（看不出文件夹层级、生成页与资料混排、同一份文件被重复索引两次）。要决定「树 + 阅读区」的形态、写操作范围与撤销语义。

| 议题 | DeepTutor | openhanako | OpenMAIC |
|---|---|---|---|
| 树在哪里 | 主区左栏，220px ↔ 44px 图标条，折叠态进 localStorage（`web/hooks/useCollapsiblePanel.ts:12-59`） | **最右栏** 260px（200–600 可拖），阅读栏夹在聊天与树之间（`desktop/src/react/hooks/use-sidebar-resize.ts:29-32`） | 最左 rail 252px（200–360，`lib/workbench/workspace-navigation.ts:51-54`） |
| 点文件 | 单击即内联预览、**不跳页**（`KbFilesTab.tsx:28-30`） | **双击**开进标签页，单击只选中（`desk/DeskTree.tsx:384-402`） | 点课程 = 加 tab + 展开右栏 + push `?course=`（`WorkspaceShell.tsx:457-466`） |
| 多开 | 无 | tabs + 关最后一个自动收起 + 每篇记阅读位置 + contentHash 校验（`stores/preview-actions.ts:157-204`） | tabs 无上限、最小宽 86px、超出横向滚动（`WorkspaceCourseTabs.tsx:3-46`） |
| 文件状态 | 文件行**零状态**，状态只在库级且挂着修复动作（`lib/knowledge-helpers.ts:311-356`） | 文件行零状态（它不建索引）；文件消失 → `missing` 占位（`preview-file-refresh.ts:76-99`） | 逐项失败 + 重试（`stage/scene-sidebar.tsx:340-433`） |
| 范围选择 | sticky chip + 一次性引用两层，**不能选文件夹**（`chat/home/KnowledgeSelector.tsx:8-22`） | **没有范围对象**，多选只用于批量操作与拖拽；限范围靠拖成附件（≤9） | 只有消息级 pill（`compose-extras.tsx:325-415`） |
| 搜索 | 树里**没有**搜索框 | 树上方名字搜索 180ms 防抖，点结果展开祖先（`desk/DeskToolbar.tsx:209-278`） | 树上方过滤 + **搜索时打平层级**（`WorkspaceRail.tsx:1034-1043`） |
| 重命名/移动 | 只能建文件夹，**无重命名** | 内联重命名 + 拖拽移动 + 系统回收站删除（`desk-actions.ts:1149-1188`） | 内联重命名 + 拖拽归档 + **删文件夹默认 ungroup 保留内容**（`workspace-folder-seam.ts:49-65`） |
| AI 整理 | 无（只输出只读 Markdown） | 无（但有"可编辑草稿卡 + 确认/取消"范式，`chat/AssistantMessage.tsx:1067-1160`） | 有，但 **agent 直接写库、无提议/确认/撤销**（`agent-runtime/curriculum-tools.ts:88-121`） |

**共同结论（可借鉴）**：① 树 + 右栏阅读的主从结构是通用解，但**打开方式要显式**（单击选中、双击打开），否则单击就替换会丢失阅读位置；② **「文档内目录」必须独立成层**，不能复用资料库树（DeepTutor 的警告 + openhanako 的 `ChapterRail`）；③ 阅读区状态要版本化：tabs + 每篇阅读位置 + 内容哈希校验 + "文件被移走"的占位；④ 破坏性操作要"明说后果 + 可恢复"（OpenMAIC 的 ungroup 默认、openhanako 的按文件版本历史）。

**不一致处的取舍**：范围对象三家都没有做成"树里选文件夹"（DeepTutor 有 sticky chip 但不能选文件夹，openhanako 干脆没有，OpenMAIC 只有消息级）——**Bobodan 两者都要，且把选择动作放进树里（支持文件夹级）**，因为我们的资料天然按课程/章节分文件夹。

**不要照搬**：DeepTutor 的"文件夹不影响检索"（我们的文件夹参与范围）；openhanako 的"删除交给系统回收站、应用内无撤销"与无面包屑的单列树；OpenMAIC 的"agent 直接写库、不等确认、无撤销"。

**Bobodan 结论**：22 项定案写进 [`LIBRARY_TREE_DESIGN.md`](LIBRARY_TREE_DESIGN.md)，按 ①→⑤ 实施。

---

## 4. 使用纪律与边界

- **默认只参考机制，不复制代码**。三份克隆的许可证为 Apache-2.0 / MIT；若确需复制代码，必须先做许可证评估，并把声明补进 `THIRD_PARTY_NOTICES.md`（`scripts/check_licenses.py` 会拦截 GPL/AGPL 依赖）。
- **不复用品牌与角色资产**（例如 openhanako 的角色形象）；Bobodan 的品牌形象固定为三花猫。
- **不照搬技术栈**：openhanako 是 Electron + Hono，OpenMAIC 是 Next.js，DeepTutor 是 Python + 自研 Web；Bobodan 保持 Python + FastAPI + SQLite + React + SSE。
- **版本会漂移**：本表 HEAD 是 2026-09-10 读到的状态；与上游不一致时以实际代码为准。
- **参考不等于排期**：本文的任何发现都必须先回到 `ROADMAP.md` 的批次与门禁，才可能变成工作项。
