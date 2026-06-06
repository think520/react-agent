# Bobodan 下一步执行计划

> **目的**：把现有 docs 中的多个功能方向收敛成一个执行入口，明确“下一步先做什么、为什么、做到什么算完成”。
>
> **当前结论**：**CLI Tool Display UX（P0）已完成**。下一步做 **Termination reason + Event trace（P1）**。不要先做 Web UI、完整 TUI、Plan mode、递归 specialist 或新的大型学习功能。

## 1. 当前状态判断

Bobodan 现在已经不是“缺功能”的阶段，而是进入了“需要稳定 runtime 和执行体验”的阶段。

已具备：

- ReAct AgentLoop
- 多 Provider
- tools / skills / memory
- RAG + 知识图谱
- quiz / learning
- MCP client
- Learning Agent Orchestrator v1：`doc_reader` / `triage` / `planner`
- `/specialists` inspection 命令

当前主要问题：

- Agent run 没有统一 termination reason。
- 没有可回放 event trace。
- 工具风险等级和 approval gate 还没落地。
- 多个 docs 都在提后续功能，但没有一个明确执行顺序。

## 2. 文档定位

| 文档 | 当前用途 | 执行判断 |
|------|----------|----------|
| `docs/NEXT_STEPS_EXECUTION_PLAN.md` | 当前执行入口 | **以后先看这个** |
| `docs/archive/agents_design.md` | Learning Agent Orchestrator v1 边界 | 已实现，后续只按 v2 扩展点增量推进 |
| `docs/archive/AGENT_HARNESS_IMPROVEMENT_PLAN.md` | runtime 可观测性、安全、plan mode 路线 | 历史详细设计；当前执行顺序以本文为准 |
| `docs/BOBODAN_AGENT_FRAMEWORK_ARCHITECTURE.md` | 模块边界规范 | 长期有效 |
| `docs/LOCAL_KNOWLEDGE_LEARNING_AGENT_PLAN.md` | 学习助手主线愿景 | 作为产品方向，不直接当下一步任务 |
| `docs/RAG_KNOWLEDGE_GRAPH_MVP.md` | 当前 RAG + 图谱使用说明 | 保留为使用文档 |
| `docs/archive/OLLAMA_RAG_EMBEDDING_PLAN.md` | Ollama embedding 接入方案 | 已实现，不再作为下一步 |
| `docs/MCP.md` / `docs/archive/mcp_design.md` | MCP 使用与设计 | MCP 方向暂不继续扩展 |

## 3. 参考 OpenSquilla 后的判断

OpenSquilla 的 CLI/TUI 值得借鉴，但不能整体照搬。

可吸收：

- thinking 动词轮换和 elapsed time
- tool args 摘要
- 连续同名 tool call 合并
- tool error 显示工具名
- 大块 paste 折叠
- renderer adapter 作为未来多 UI 入口的参考

暂不吸收：

- long-lived prompt-toolkit Application
- 完整 TerminalRenderer 抽象
- Web UI / chat channel 共用 turn loop
- token/cost footer，除非 provider usage 数据已统一

原因：

- Bobodan 当前 REPL 已经有 streaming/typewriter/thinking/specialist event，先做显示层小改收益最高。
- 完整 TUI 会牵扯输入循环、取消语义、output lock、approval surface，应该等 event trace / approval gate 之后再考虑。

## 4. 总优先级

```text
P0. CLI Tool Display UX（已完成）
    ↓
P1. Termination reason + Event trace（当前下一步）
    ↓
P2. Tool risk class + Approval gate
    ↓
P3. Prompt cache / usage plumbing / footer
    ↓
P4. Plan mode
    ↓
P5. Workflow runtime / Web UI / full TUI
```

核心理由：

- P0 已经直接改善 specialist 工具调用显示，作为后续 trace UI 的显示样板。
- P1 是后续 approval、plan mode、cost footer、debug 的基础。
- P2 需要 P1 的事件面，否则 CLI 审批会继续堆在 `repl.py` 里。
- P4 依赖 P1/P2，否则 plan mode 只是“更复杂的 ReAct”，不可控。

## 5. 已完成：P0 CLI Tool Display UX

### 当前状态

P0 已落地到 `codex/cli-tool-display-ux` 分支：

- B-lite single-active-line UI：thinking line 和 tool spinner 只占用当前 active line。
- 工具参数摘要：高频工具走专门摘要，其他内置工具和 MCP 工具走短 JSON fallback。
- 连续同名 tool call 合并：第 1-2 次正常显示，第 3 次显示 `×3`，4+ 静默计数，flush 时显示 `×N total`。
- specialist 内部 tool events 和主 agent tool events 分 visual scope。
- `/ui tools off` 保留错误行，隐藏成功 tool 噪音。
- `tool_end` event 增加 `elapsed` 和可选 `result_summary`。

### 已修复的 P0 细节

- coalesce summary 使用 wall-clock，不再把 per-tool elapsed 当 absolute timestamp。
- `delegate_*` 外层成功记在父 scope，不污染 specialist 内部工具统计。
- specialist 内部 display events 透传 `elapsed` / `result_summary`。
- thinking line spinner 和 tool spinner 都按 tick 切帧。

### 目标

让 Bobodan 的工具调用显示更清晰，尤其是 specialist 内部 tool event 较多时不刷屏、不丢关键信息。

### 不改变的行为

- 不改变 AgentLoop 语义。
- 不改变 ToolResult。
- 不改变 session 写入规则。
- 不改变 specialist 的隔离边界。
- 不新增完整 renderer 抽象。

### 建议文件

| 文件 | 操作 |
|------|------|
| `cli/repl.py` | 最小改动：thinking 文案、tool display、specialist event display |
| `tests/test_repl.py` 或新增 `tests/test_repl_display.py` | 测格式化函数 |
| `README.md` | 如输出形态变化明显，补一句说明 |
| `CHANGELOG.md` | 记录 CLI UX 改进 |

### 具体任务

1. 新增工具参数摘要函数

   建议接口：

   ```python
   def _summarize_tool_args(self, tool_name: str, args: dict, limit: int = 60) -> str:
       ...
   ```

   行为：

   | tool | 显示 |
   |------|------|
   | `read_file` / `write_file` / `list_dir` | path 尾部 |
   | `rag_search` / `graph_query` | query / concept |
   | `delegate_doc_reader` | `source_paths` 尾部 + goal 摘要 |
   | `delegate_triage` | query 摘要 |
   | `delegate_planner` | goal 摘要 |
   | MCP tool | 保留短 JSON，最多 60 字符 |

2. 调整 tool start 显示

   当前形态：

   ```text
   ▸ read_file({"path":"F:\\...long..."})
   ```

   目标形态：

   ```text
   ▸ read_file ...\docs\NEXT_STEPS_EXECUTION_PLAN.md
   ▸ rag_search transformer attention
   ▸ delegate_doc_reader ...\NEXT_STEPS_EXECUTION_PLAN.md
   ```

3. 连续同名 tool call 合并

   只在显示层合并，不影响真实事件。

   规则：

   ```text
   第 1 次：正常显示
   第 2 次：正常显示
   第 3 次：显示 read_file ×3
   第 4 次以后：静默计数
   tool name 变化或 turn 结束：如 count > 3，显示 read_file ×8 total 3.4s
   ```

   注意：

   - 未来 event trace 必须记录所有真实 tool events。
   - 合并只影响 REPL 输出。

4. 错误显示带工具名

   当前 specialist 内部错误可能只显示内容摘要。

   目标：

   ```text
   ✗ read_file: File not found: docs\missing.md
   ```

5. thinking 动效改为动词轮换

   建议词表：

   ```python
   THINK_VERBS = ["thinking", "reading", "searching", "planning", "summarizing"]
   ```

   规则：

   - spinner frame 仍然 0.1s 切换。
   - verb 每 2.5s 切换。
   - 可以显示 elapsed time。
   - 暂时不要写 `Ctrl+C cancels`，除非真正实现取消语义。

### 验收标准

手动验证：

```text
请阅读 docs\NEXT_STEPS_EXECUTION_PLAN.md 并总结当前下一步。
```

预期：

```text
▸ delegate_doc_reader ...\docs\NEXT_STEPS_EXECUTION_PLAN.md
  ◐ doc_reader_specialist running...
    ▸ read_file ...\docs\NEXT_STEPS_EXECUTION_PLAN.md
    ✓ ...
```

连续 tool 场景预期：

```text
▸ read_file ...\chapter1.md
▸ read_file ...\chapter2.md
▸ read_file ×3
▸ read_file ×8 total 3.4s
```

最终测试：

```powershell
.venv\Scripts\python.exe -m pytest tests/test_repl_display.py tests/test_repl.py tests/test_agents_repl.py tests/test_agent_loop.py tests/test_agents_runner.py
```

提交建议：

```text
fix(cli): improve tool call display
```

## 6. 当前下一步：P1 Termination reason + Event trace

### 目标

让每次 Agent run 都能回答：

- 为什么结束？
- 跑了几轮？
- 调了哪些工具？
- 哪一步失败？
- 后续能否回放？

### 依赖

- P0 已完成，显示层已经有可复用的 tool event 表达。
- P1 完成后，P0 的显示事件应该尽量复用 trace event schema。

### 建议文件

| 文件 | 操作 |
|------|------|
| `core/agent_loop.py` | 输出 termination reason 和标准事件 |
| `core/trace.py` | 新增 trace writer / event schema |
| `tools/trace_view.py` | 新增 trace 回放工具 |
| `cli/repl.py` | turn 结束显示 termination reason |
| `tests/test_termination_reason.py` | 新增 |
| `tests/test_event_trace.py` | 新增 |

### 最小事件类型

```text
turn_start
assistant_delta
tool_start
tool_end
specialist_event
assistant_done
turn_end
error
```

### termination reason

```text
final_answer
max_iter
timeout
error
cancelled
```

### 验收标准

- 每个 turn 结束都有 `termination_reason`。
- `.bobodan/traces/` 下生成 jsonl。
- trace 不写 secrets。
- trace 能包含 specialist display events，但不改变 parent session。
- 单元测试覆盖 final / max_iter / timeout / error。

提交建议：

```text
feat(agent): add termination reason and event trace
```

## 7. P2：Tool risk class + Approval gate

### 目标

高风险工具执行前必须用户确认。

### 为什么不能先做

approval gate 需要稳定的事件面，否则 REPL 交互会变成特殊分支堆叠。

### 建议 risk class

```text
read
draft
write
external
destructive
privileged
```

### 初始策略

| 工具 | 风险 |
|------|------|
| `read_file` / `list_dir` / `rag_search` / `graph_query` | `read` |
| `write_file overwrite=false` | `write` |
| `write_file overwrite=true` | `destructive` |
| `http_request GET` | `read` 或 `external`，按配置决定 |
| `http_request POST/PUT/DELETE` | `external` |
| `memory_forget` | `destructive` |

### 验收标准

- 风险等级进入 tool registry。
- REPL 收到 approval request 事件并询问用户。
- 用户拒绝后，LLM 收到拒绝原因。
- 拒绝不写入危险操作。

提交建议：

```text
feat(tools): add risk class and approval gate
```

## 8. P3：Prompt cache / Usage plumbing / Footer

### 目标

为成本透明和 prompt cache 优化打基础。

### 为什么排在 P2 后

footer 需要稳定 usage 数据；prompt cache 需要 provider 返回 usage 或 cache fields，否则只能做“看起来像优化”的改动。

### 范围

- provider 统一 usage 字段
- system prompt 稳定前缀整理
- turn footer 显示 model / elapsed / tokens / cached / cost

### 验收标准

- provider response 有统一 usage 结构。
- 没有 usage 的 provider 不显示假数据。
- footer 在 80-100 列中文终端不明显换行。

提交建议：

```text
feat(runtime): add usage summary plumbing
```

## 9. P4：Plan mode

### 目标

复杂任务先生成计划，用户确认后执行。

### 为什么不能提前做

Plan mode 会放大两个问题：

- 没 trace：不知道执行到哪一步。
- 没 approval：高风险步骤无法拦截。

### 最小版本

```text
/plan <task>
  -> LLM 生成 steps
  -> REPL 展示
  -> 用户确认
  -> 按步骤执行
  -> 每步写 trace
```

### 验收标准

- `/plan` 不影响普通 ReAct。
- 计划可拒绝。
- 每步有 trace。
- 高风险步骤走 approval gate。

提交建议：

```text
feat(agent): add plan mode
```

## 10. 暂缓事项

这些方向不是不要做，而是现在不要先做：

| 方向 | 暂缓原因 |
|------|----------|
| 完整 TUI / long-lived Application | 牵扯输入循环、取消、approval surface，当前收益不如 P0/P1 |
| Web UI | 需要稳定 event stream 和 workflow runtime |
| 递归 specialist | 明确违反 v1 边界 |
| specialist 并行 | 需要 budget / trace / cancellation 基础 |
| Workflow runtime | 应该等 event trace 基础完成后再抽 |
| Wiki 编译层继续扩展 | 当前更缺 runtime 可观测性和执行体验 |
| MCP specialist 默认开放 | v1 已明确默认关闭 |
| 新增更多 specialist | 先证明 3 个现有 specialist 的 UX 和 trace 稳定 |

## 11. 立即行动清单

从这里开始：

1. 开一个新分支：

   ```powershell
   git checkout -b codex/cli-tool-display-ux
   ```

2. 只做 P0：

   ```text
   CLI Tool Display UX
   ```

3. 不碰：

   ```text
   Event trace
   Approval gate
   Plan mode
   Web UI
   Full TUI
   New specialist
   ```

4. 验证：

   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_repl.py tests/test_agents_repl.py
   .venv\Scripts\python.exe -m pytest
   ```

5. 手动 REPL 验证：

   ```text
   请阅读 docs\NEXT_STEPS_EXECUTION_PLAN.md 并总结当前下一步。
   帮我读一下 docs\RAG_KNOWLEDGE_GRAPH_MVP.md，并输出 5 个要点。
    直接读取 docs\MCP.md 的原文前 200 字。
    ```

## 12. 判断规则

以后新增 docs 或功能提案时，先问三件事：

1. 它是否改善当前学习助手主线？
2. 它是否依赖 event trace / approval gate / usage plumbing？
3. 它是否会破坏 `archive/agents_design.md` 里的 v1 边界？

如果答案是：

- 不改善主线：不做。
- 依赖基础设施：先做基础设施。
- 破坏 v1 边界：写 v2 design，不直接改代码。

## 13. 当前唯一下一步

**下一步只做：P1 Termination reason + Event trace。**

P0 已经完成。现在继续做 P1，因为它是后续 approval gate、plan mode、usage footer、debug 回放的基础：

- 给每次 run 明确 termination reason。
- 让 tool_start / tool_end / specialist_event 有统一事件 schema。
- 写入 `.bobodan/traces/*.jsonl`，支持回放和调试。
- 为 P2 approval gate 提供可靠事件面。
