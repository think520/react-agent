# Bobodan 下一步执行计划

> **目的**：把现有 docs 中的多个功能方向收敛成一个执行入口，明确"下一步先做什么、为什么、做到什么算完成"。
>
> **当前结论**：**CLI Tool Display UX 已完成**，**P0 学习闭环补全已完成**。下一步做 **P1 Obsidian 写回**——学习计划和做题总结导出为 Obsidian Markdown。

## 1. 当前状态判断

Bobodan 已经具备完整的功能骨架，但核心学习链路存在断点。

已具备：

- ReAct AgentLoop + 多 Provider
- tools / skills / memory（永久 + 每日 + FTS5 + 晋升）
- RAG + 知识图谱 + Ollama embedding
- quiz / learning / review / mastery
- MCP client（stdio / SSE / streamable_http）
- Learning Agent Orchestrator v1：`doc_reader` / `triage` / `planner`
- CLI Tool Display UX（B-lite 单活动行 UI）
- 687 个测试，44 个测试文件

**核心断点**：

1. ~~**quiz_submit 不写记忆、不更新掌握度**~~ — **已修复 (P0)**
2. **Obsidian 写回不存在** — README 承诺"学习计划可导出为 Obsidian Markdown"，无任何实现。
3. **Workflow runtime 不存在** — 学习计划只存 SQLite、只返回纯文本，无法执行和跟踪进度。
4. **Agent loop 无 termination reason** — `assistant_done` 事件无结构化终止原因。

## 2. 文档定位

| 文档 | 用途 |
|------|------|
| `docs/NEXT_STEPS_EXECUTION_PLAN.md` | **当前执行入口**（本文件） |
| `docs/DESIGN.md` | 长期视觉设计参考（Web UI / TUI / 官网） |
| `docs/BOBODAN_AGENT_FRAMEWORK_ARCHITECTURE.md` | 模块边界规范 |
| `docs/LOCAL_KNOWLEDGE_LEARNING_AGENT_PLAN.md` | 学习助手主线愿景 |
| `docs/RAG_KNOWLEDGE_GRAPH_MVP.md` | RAG + 图谱使用文档 |
| `docs/MCP.md` | MCP 使用文档 |
| `docs/archive/*` | 历史设计文档，仅供参考 |

## 3. 设计原则

1. **学习闭环完整性是第一优先级** — 做题→记忆→掌握度→复习的链路断了，其他都是空的。
2. **兑现已有承诺** — README 和 CHANGELOG 白纸黑字写了 Obsidian 写回和 quiz 自动写记忆，不做就是产品债。
3. **Workflow 是产品核心** — 学习计划的"执行"和"跟踪"需要 workflow，不是 runtime 优化。
4. **Event trace / approval gate / prompt cache / plan mode** 低于学习闭环优先级；其中 Event Trace 是后续 Web UI、调试和 workflow 可视化的基础，保留为 P2 轻量版。

## 4. 总优先级

```text
P0. 学习闭环补全（当前下一步）
    ↓
P1. Obsidian 写回
    ↓
P2. Event Trace 轻量版
    ↓
P3. Workflow Runtime 最小版
    ↓
P4. 文档统一
```

## 5. 已完成：CLI Tool Display UX

已落地，包含：

- B-lite 单活动行 UI：thinking line 和 tool spinner 只占用当前 active line
- 工具参数摘要：高频工具走专门摘要，其他走短 JSON fallback
- 连续同名 tool call 合并：1-2 次正常，第 3 次显示 `×3`，4+ 静默计数
- specialist 内部 tool events 和主 agent tool events 分 visual scope
- thinking 动词轮换：`Thinking` / `Checking` / `Working` / `Drafting` / `Polishing`

## 5b. 已完成：P0 学习闭环补全

已落地，包含：

- `learning/quiz_integration.py`：`record_quiz_learning_effect` + `record_quiz_session_summary`
- `quiz_submit` 每次提交自动写每日记忆 + 更新掌握度
- 全部答完自动写汇总记忆 + 标记 session 完成
- 掌握度规则：连续答对 2 次 → mastered，答错 → needs_review
- 13 个测试覆盖，700 测试全通过

## 6. 当前下一步：P1 Obsidian 写回

### 目标

让"做题→写记忆→更新掌握度→晋升评分"这条链路真正跑通。

### 为什么最优先

这是学习助手的核心价值闭环。现在用户做 100 道题，记忆系统和掌握度追踪是空的，晋升评分永远是 0。产品承诺的功能实际不工作。

### 任务 P0-1：quiz_submit 自动写每日记忆 + 更新掌握度

**新增文件**：`learning/quiz_integration.py`

**修改文件**：`tools/quiz_tools.py`

**当前断点**：`tools/quiz_tools.py` 第 187 行 `store.record_attempt(attempt_record)` 之后，直接跳到格式化返回。既不写每日记忆，也不更新掌握度。

**设计**：业务逻辑不直接写在 tool 里，抽到 `learning/quiz_integration.py` 以便 CLI、Web API、workflow runtime 都能复用。

`learning/quiz_integration.py` 新增函数：

```python
def record_quiz_learning_effect(
    workspace: str,
    question_concepts: list[str],
    is_correct: bool,
    feedback: str,
) -> list[Mastery]:
    """做题后自动写每日记忆 + 更新掌握度。

    1. 写入 daily memory（tags: quiz + concepts）
    2. 调用 ProgressTracker.update_from_quiz 更新掌握度
    3. 返回更新后的 mastery 列表
    """
```

`tools/quiz_tools.py` 改动：在 `store.record_attempt()` 之后调用 `record_quiz_learning_effect(workspace, question.concepts, is_correct, feedback)`。

**验收标准**：

- 做题后 `.bobodan/daily/` 下出现当日记忆文件，包含做题记录
- 做题后 `ProgressTracker.get_overview()` 返回非空掌握度数据
- 连续答对 2 次同一概念，掌握度变为 `mastered`
- 答错后掌握度变为 `needs_review`
- `record_quiz_learning_effect` 可独立调用，不依赖 Agent tool 上下文
- 现有 687 个测试全部通过

**工作量**：0.5 天

**提交建议**：`feat(quiz): auto-write daily memory and update mastery on submit`

### 任务 P0-2：批量做题汇总写入每日记忆

**修改文件**：`tools/quiz_tools.py`、`learning/quiz_integration.py`

**依赖**：P0-1

**具体改动**：在 `quiz_submit` 中检测 session 是否所有题目都已作答：

```python
attempts = store.get_attempts_for_session(session_id)
answered_ids = {a.question_id for a in attempts}
completed = set(session.question_ids).issubset(answered_ids)
```

如果 `completed`，追加汇总记忆并调用 `store.complete_session(session_id)`：

```text
练习完成: {session_id}，共 {n} 题，正确 {m} 题，正确率 {rate}
薄弱点: {weak_concepts}
```

**注意**：`QuizSession` 没有 `current_index` 字段，必须通过 `get_attempts_for_session` 反推已答题数。

**验收标准**：一轮 5 题练习结束后，每日记忆中有逐题记录和一条汇总，session 状态变为 completed。

**工作量**：0.5 天

**提交建议**：`feat(quiz): add session summary to daily memory`

## 7. P1：Obsidian 写回

### 目标

学习计划、做题总结、薄弱点分析可导出为 Obsidian Markdown 文件。

### 为什么第二优先

README 已经承诺了这个功能。Obsidian 是学习者的核心工具，写回能力让 Bobodan 真正融入学习工作流。

### 任务 P1-1：学习计划导出为 Obsidian Markdown

**新增文件**：`tools/obsidian_export.py`

**具体改动**：

1. 新增 `obsidian_export_plan(plan_id, vault_path, session)` 工具函数：
   - 从 `LearningStore` 读取 `LearningPlan`
   - 生成 Obsidian 格式 Markdown：YAML frontmatter + 按天拆分的 checkbox 任务列表 + `[[双链]]` 知识点引用
   - 写入 `{vault_path}/学习计划/{plan.title}.md`
   - 路径安全检查参照 `tools/obsidian_tool.py` 的 `_is_within_workspace`

2. 注册为 Agent 工具 `obsidian_export_plan`

**验收标准**：

- 生成的 Markdown 有正确的 frontmatter
- 知识点用 `[[concept]]` 双链格式
- 任务用 checkbox 格式，可在 Obsidian 中勾选
- 文件写入路径在 workspace 内
- 现有测试通过

**工作量**：1 天

**提交建议**：`feat(export): learning plan to Obsidian markdown`

### 任务 P1-2：做题总结导出

**修改文件**：`tools/obsidian_export.py`（同 P1-1）

**具体改动**：新增 `obsidian_export_quiz_summary(course, vault_path, session)` 工具函数：

- 从 `QuizStore` 读取做题记录和薄弱点分析
- 生成包含错题本（按知识点分组）+ 薄弱点分析（错误率排序）+ 掌握度概览的 Markdown
- 写入 `{vault_path}/做题总结/{date}.md`

**验收标准**：按知识点分组的错题本、错误率统计、正确的 frontmatter。

**工作量**：0.5 天

**提交建议**：`feat(export): quiz summary to Obsidian markdown`

## 8. P2：Event Trace 轻量版

### 目标

每次 Agent run 记录关键事件，支持事后查看"做了什么、花了多久、哪步失败"。

### 为什么排第三

trace 是调试和改进的基础，但不影响核心学习功能。做好 P0/P1 后，用户的学习闭环已经完整，trace 是锦上添花。

### 任务 P2-1：结构化 termination reason

**修改文件**：`core/agent_loop.py`

**当前断点**：第 204 行和第 210 行的 `assistant_done` 事件无 `termination_reason` 字段。

**具体改动**：在 `assistant_done` 事件中增加 `termination_reason` 字段：

- 正常回答（第 204 行）：`final_answer`
- 达到 max_iterations（第 210 行）：`max_iter`
- 异常：`error`

**验收标准**：

- 每个 `assistant_done` 事件都有 `termination_reason` 字段
- 单元测试覆盖 `final_answer`、`max_iter`、`error` 三种情况

**工作量**：0.5 天

**提交建议**：`feat(agent): add structured termination reason`

### 任务 P2-2：JSONL trace 写入

**新增文件**：`core/trace.py`

**修改文件**：`core/agent_loop.py`（可选注入 trace writer）

**具体改动**：

1. `core/trace.py`：`TraceWriter` 类
   - 写入 `.bobodan/traces/{session_id}_{timestamp}.jsonl`
   - 每个事件一行 JSON
   - 不写 secrets（过滤 api_key 等字段）
   - 只写 tool_start / tool_end / assistant_done / error（不写 assistant_delta 的逐 token 流）

2. `core/agent_loop.py`：构造函数增加可选 `trace_writer` 参数，有则同时写入 trace

3. `cli/repl.py`：启动时创建 TraceWriter，注入 AgentLoop

**验收标准**：

- `.bobodan/traces/` 下生成 jsonl 文件
- 每行是合法 JSON
- 不包含 api_key 等敏感信息
- 不注入 trace_writer 时行为不变

**工作量**：1 天

**提交建议**：`feat(agent): add JSONL trace writer`

## 9. P3：Workflow Runtime 最小版

### 目标

学习计划不只是"看一下"，而是可以"执行"——按天推进、跟踪完成状态、到期提醒。

### 为什么排第四

这是产品核心差异化功能。没有 workflow，学习计划只是一段文本；有了 workflow，Bobodan 才是真正的"学习助手"而不是"学习文档生成器"。

### 任务 P3-1：学习计划执行状态追踪

**修改文件**：`learning/schema.py`、`learning/store.py`、`tools/learning_tools.py`

**具体改动**：

1. `learning/schema.py`：`LearningPlan` 增加 `status`（`active` / `completed` / `paused`）和 `current_day` 字段
2. `learning/store.py`：增加 `update_plan_progress(plan_id, day, status)` 方法
3. `tools/learning_tools.py`：新增 `learning_plan_progress(plan_id, day, completed_tasks)` 工具
4. `cli/repl.py`：新增 `/learning progress <plan_id>` 命令

**验收标准**：

- 可以标记某天的任务为完成
- 进度百分比显示
- 计划状态正确更新

**工作量**：1 天

**提交建议**：`feat(learning): plan execution progress tracking`

### 任务 P3-2：到期提醒与复习调度集成

**修改文件**：`cli/repl.py`

**具体改动**：

- REPL 启动时检查：是否有到期的学习计划天数、是否有到期的复习知识点
- 如果有，在启动面板显示一行提醒（不阻塞）
- 新增 `/learning today` 命令：合并显示今天的学习计划 + 复习清单

**验收标准**：

- 启动时如果有到期任务，显示一行提醒
- `/learning today` 显示合并后的今日任务清单

**工作量**：0.5 天

**提交建议**：`feat(learning): daily reminder and /learning today`

## 10. P4：文档统一

**目标**：让 `docs/DESIGN.md`（600 行设计系统）成为后续 UI 相关工作的参考基准。

**具体任务**：

- 在本文件的文档定位表中加入 DESIGN.md（已完成）
- 在 README.md 中引用 DESIGN.md 作为视觉设计参考

**工作量**：0.5 小时

## 11. P5 远期方向：Web UI / 前后端分离

P0-P3 完成后，Bobodan 具备稳定的学习闭环、Obsidian 导出、event trace 和 workflow runtime，届时可以做前后端分离。

### 技术栈（已定）

| 层 | 选型 |
|----|------|
| 后端 | FastAPI |
| 前端 | React + Vite + TypeScript + Tailwind + shadcn/ui |
| AI UI 组件 | assistant-ui 可评估，不强依赖 Vercel AI SDK 协议 |
| 通信 | SSE 优先，WebSocket 后置 |

### 架构顺序（关键）

**先抽 app service，再上 FastAPI，再上 Web。** 不直接在 FastAPI 里写业务逻辑。

```text
第一步：app service 层
  service/
    quiz_service.py       # 封装 quiz 相关业务（已在 P0 的 quiz_integration.py 开始）
    learning_service.py   # 封装 learning 相关业务
    memory_service.py     # 封装 memory 相关业务
    kb_service.py         # 封装知识库相关业务
    agent_service.py      # 封装 agent run 相关业务
  ↓ CLI 和 Web API 都调用 service，不直接调 tool/store

第二步：FastAPI 层
  web/backend/
    routers/chat.py       # /api/chat/runs, /api/chat/runs/{id}/events (SSE)
    routers/quiz.py       # /api/quiz/*
    routers/learning.py   # /api/learning/*
    routers/memory.py     # /api/memory/*
    routers/kb.py         # /api/kb/*
    routers/settings.py   # /api/settings/*
  ↓ FastAPI 路由只做 HTTP 协议转换，业务全在 service

第三步：React 前端
  web/frontend/
    src/
      components/         # shadcn/ui + DESIGN.md 定制
      pages/
      hooks/              # SSE streaming、agent events
  ↓ 按 DESIGN.md 做视觉，Natural Editorial Zen
```

### 关键约束

- **SSE 优先** — Bobodan 的主要流是"后端向前端持续吐事件"，SSE 更简单更稳定。只有需要浏览器实时取消、多用户协作时再上 WebSocket。
- **复用现有 runtime** — `core/` / `tools/` / `learning/` / `memory/` 不重写。
- **service 层是核心** — CLI `repl.py` 和 FastAPI routers 都调 service，不让业务逻辑长在任何 UI 层里。
- **assistant-ui 评估但不绑定** — 如果它的协议跟 Bobodan 的 event schema 不兼容，自己写 SSE consumer 也行。
- **按 docs/DESIGN.md 做视觉** — Natural Editorial Zen，暖米色/墨蓝/植物绿。

**前提条件**：P3 Workflow Runtime 完成后再做。Web 需要稳定的后端事件流、任务状态、workflow 状态、可恢复 run。

## 12. 暂缓事项

| 方向 | 暂缓原因 |
|------|----------|
| Tool risk class / Approval gate | 单用户本地工具，write_file 已有 overwrite 保护，够用 |
| Plan mode | LLM 在 ReAct 循环内可自行规划，不需要独立 plan mode |
| Prompt cache 优化 | 取决于 provider 是否返回 cache 字段，投入产出比低 |
| Usage plumbing / Footer | 等 provider 统一返回 usage 数据后再做 |
| 完整 TUI / long-lived Application | 当前 REPL + B-lite 已经够用 |
| Web UI | 需要 workflow runtime 稳定后再考虑 |
| 递归 specialist | 违反 v1 边界，需要 v2 设计 |
| specialist 并行 | 需要 budget / trace / cancellation 基础 |
| MCP specialist 默认开放 | v1 已明确默认关闭 |
| 新增更多 specialist | 先证明现有 3 个 specialist 的价值 |
| Ebbinghaus 遗忘曲线 | 当前简单间隔重复（1/3/7/14 天）够用 |

## 13. 执行顺序与工作量

```text
P0-1 (quiz_submit 写记忆+掌握度)  ──┐
                                     ├── P0-2 (批量做题汇总)
                                     │
P1-1 (学习计划导出 Obsidian)  ───────┤
                                     ├── P1-2 (做题总结导出)
                                     │
P2-1 (termination reason)  ─────────┤
                                     ├── P2-2 (JSONL trace)
                                     │
P3-1 (计划执行状态追踪)  ───────────┤
                                     └── P3-2 (到期提醒)
```

| 阶段 | 任务数 | 估计工作量 |
|------|--------|-----------|
| P0 学习闭环补全 | 2 | 1 天 |
| P1 Obsidian 写回 | 2 | 1.5 天 |
| P2 Event Trace | 2 | 1.5 天 |
| P3 Workflow Runtime | 2 | 1.5 天 |
| P4 文档统一 | 1 | 0.5 小时 |
| **总计** | **9** | **~5.5 天** |

## 14. 判断规则

新增功能提案时，先问三件事：

1. 它是否直接改善学习闭环（做题→记忆→掌握度→复习→导出）？
2. 它是否需要 workflow runtime 支持？
3. 它是否破坏 v1 specialist 边界？

如果答案是：

- 不改善学习闭环：不做。
- 需要 workflow：先做 P3。
- 破坏 v1 边界：写 v2 设计，不直接改代码。

## 15. 立即行动

**下一步只做：P0-1 quiz_submit 自动写每日记忆 + 更新掌握度。**

开分支：

```powershell
git checkout -b feature/learning-loop-close
```

新增文件：`learning/quiz_integration.py`

修改文件：`tools/quiz_tools.py`

关键依赖：`memory/daily.py`（DailyMemoryManager）、`learning/progress.py`（ProgressTracker.update_from_quiz）

验证：

```powershell
.venv\Scripts\python.exe -m pytest
```

手动验证：做题后检查 `.bobodan/daily/` 有当日记忆，`/learning progress` 显示掌握度数据。
