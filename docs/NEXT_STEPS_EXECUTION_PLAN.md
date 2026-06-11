# Bobodan 下一步执行计划

> **目的**：把现有 docs 中的多个功能方向收敛成一个执行入口，明确"下一步先做什么、为什么、做到什么算完成"。
>
> **当前结论**：**P0-P3 全部完成**。下一步做 **P4 文档统一**，远期方向 **P5 Web UI / 前后端分离**。

## 1. 当前状态判断

已具备：

- ReAct AgentLoop + 多 Provider + 多模型切换
- tools / skills / memory（永久 + 每日 + FTS5 + 晋升）
- RAG + 知识图谱 + Ollama embedding
- quiz / learning / review / mastery + workflow runtime
- Obsidian 写回（学习计划 + 做题总结）
- Event Trace（JSONL trace + `/trace` 命令）
- MCP client（stdio / SSE / streamable_http）
- Learning Agent Orchestrator v1：`doc_reader` / `triage` / `planner`
- CLI Tool Display UX（B-lite 单活动行 UI）
- 759 个测试，47 个测试文件

**所有核心断点已修复。**

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
2. **兑现已有承诺** — README 和 CHANGELOG 白纸黑字写了的功能，不做就是产品债。
3. **Workflow 是产品核心** — 学习计划的"执行"和"跟踪"需要 workflow，不是 runtime 优化。
4. **Event trace / approval gate / prompt cache / plan mode** 低于学习闭环优先级。

## 4. 总优先级

```text
P0. 学习闭环补全（已完成）
P1. Obsidian 写回（已完成）
P2. Event Trace（已完成）
P3. Workflow Runtime（已完成）
P4. 文档统一（下一步）
P5. Web UI / 前后端分离（远期）
```

## 5. 已完成摘要

### P0 学习闭环补全

- `learning/quiz_integration.py`：`record_quiz_learning_effect` + `record_quiz_session_summary`
- `quiz_submit` 自动写每日记忆 + 更新掌握度 + session 完成汇总
- 掌握度规则：连续答对 2 次 → mastered，答错 → needs_review

### P1 Obsidian 写回

- `tools/obsidian_export.py`：`obsidian_export_plan` + `obsidian_export_quiz_summary`
- 学习计划导出：YAML frontmatter + checkbox 任务 + `[[双链]]`
- 做题总结导出：错题本 + 薄弱点分析 + 掌握度概览

### P2 Event Trace

- `core/agent_loop.py`：`assistant_done` 事件增加 `termination_reason`（`final_answer` / `max_iter` / `error`）
- `core/trace.py`：`TraceWriter` 写入 `.bobodan/traces/`，secret redact + content 截断 + 线程安全
- `/trace` 命令：列出最近 run、查看 tool timeline
- `run_stream` 异常时 yield `assistant_done(error)` 再 re-raise

### P3 Workflow Runtime

- `learning/schema.py`：`LearningPlan` 增加 `status`（active/completed）和 `current_day`
- `learning/store.py`：`plan_progress` 表（plan_id, day, task_index, source）
- `learning/workflow.py`：`PlanWorkflowTracker` — 自动推断 step 完成 + 进度查询 + 追赶模式
- `tools/learning_tools.py`：`learning_plan_progress` 工具（status / complete_task / complete_step / today）
- `cli/repl.py`：`/learning today` 合并显示计划任务 + 到期复习
- 自动推断：`update_from_quiz` → 检查 step topics mastery → 自动标记完成 → plan 完成时自动 status=completed

### CLI Tool Display UX

- B-lite 单活动行 UI：thinking line 和 tool spinner 只占用当前 active line
- 工具参数摘要、连续同名 tool call 合并、thinking 动词轮换
- specialist 内部 tool events 分 visual scope

## 6. P4：文档统一

**目标**：让 `docs/DESIGN.md`（600 行设计系统）成为后续 UI 相关工作的参考基准。

**具体任务**：

- 在本文件的文档定位表中加入 DESIGN.md（已完成）
- 在 README.md 中引用 DESIGN.md 作为视觉设计参考

**工作量**：0.5 小时

## 7. P5 远期方向：Web UI / 前后端分离

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

- **SSE 优先** — Bobodan 的主要流是"后端向前端持续吐事件"，SSE 更简单更稳定。
- **复用现有 runtime** — `core/` / `tools/` / `learning/` / `memory/` 不重写。
- **service 层是核心** — CLI `repl.py` 和 FastAPI routers 都调 service，不让业务逻辑长在任何 UI 层里。
- **按 docs/DESIGN.md 做视觉** — Natural Editorial Zen，暖米色/墨蓝/植物绿。

**前提条件**：P3 Workflow Runtime 已完成。Web 需要稳定的后端事件流、任务状态、workflow 状态、可恢复 run。

## 8. 暂缓事项

| 方向 | 暂缓原因 |
|------|----------|
| Tool risk class / Approval gate | 单用户本地工具，write_file 已有 overwrite 保护，够用 |
| Plan mode | LLM 在 ReAct 循环内可自行规划，不需要独立 plan mode |
| Prompt cache 优化 | 取决于 provider 是否返回 cache 字段，投入产出比低 |
| Usage plumbing / Footer | 等 provider 统一返回 usage 数据后再做 |
| 完整 TUI / long-lived Application | 当前 REPL + B-lite 已经够用 |
| Web UI | 需要 service 层抽取后再考虑 |
| 递归 specialist | 违反 v1 边界，需要 v2 设计 |
| specialist 并行 | 需要 budget / trace / cancellation 基础 |
| MCP specialist 默认开放 | v1 已明确默认关闭 |
| 新增更多 specialist | 先证明现有 3 个 specialist 的价值 |
| Ebbinghaus 遗忘曲线 | 当前简单间隔重复（1/3/7/14 天）够用 |

## 9. 判断规则

新增功能提案时，先问三件事：

1. 它是否直接改善学习闭环（做题→记忆→掌握度→复习→导出）？
2. 它是否需要 workflow runtime 支持？
3. 它是否破坏 v1 specialist 边界？

如果答案是：

- 不改善学习闭环：不做。
- 需要 workflow：P3 已完成，可直接做。
- 破坏 v1 边界：写 v2 设计，不直接改代码。

## 10. 立即行动

**下一步：P4 文档统一。**

- 在 README.md 中引用 DESIGN.md 作为视觉设计参考
- 工作量：0.5 小时
