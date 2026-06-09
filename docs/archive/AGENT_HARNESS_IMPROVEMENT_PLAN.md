# Agent Harness 改进计划

> 基于 [DenisSergeevitch/agents-best-practices](https://github.com/DenisSergeevitch/agents-best-practices) 的参考模式
> 创建时间：2026-05-21
> 状态：待执行

## 1. 背景

`agents-best-practices` 是一个提供商中立的 Agent harness 设计参考，提供 15 份 reference 文档，涵盖 Agent 运行时设计的全部关键领域。

核心哲学：**"The model proposes; the harness validates, authorizes, executes, and records."**

Bobodan 已经是完整的 ReAct 学习助手，但对照该参考，有几个明显的盲区可以补齐。

## 2. 现状对比

| 主题 | Bobodan 现状 | 该仓库建议 | 差距 |
|------|--------------|------------|------|
| **agentic-loop** | max 8 iter + 300s 超时 | 加预算 + 终止原因 + event trace | ❌ 没有 termination_reason、step/cost 预算、event log |
| **tools-and-permissions** | workspace 边界 + DENY 列表 | 加 risk class + approval gate | ❌ 所有工具同风险等级 |
| **planning-and-goals** | 纯 ReAct | plan 模式 + checkpoint | ❌ 复杂任务没显式 plan |
| **context-memory-compaction** | session trim + FTS5 + 每日记忆 | compaction 保留 active state | ⚠️ auto-compaction 会丢 active state |
| **prompt-caching-and-cost** | skills + memory 注入 | 稳定前缀 + 动态后缀 | ❌ 没用 prompt cache 优化布局 |
| **security-evals-observability** | DENY 列表 + workspace 边界 | event trace + eval suite | ❌ 没有 trace replay、没有 evals |
| **skills-and-connectors** | skills 系统 | ✅ 已有 | 完整 |
| **provider-api-patterns** | OpenAI/DeepSeek/MiniMax | ✅ 已有 | 完整 |
| **mvp-agent-blueprint** | 学习助手蓝图 | 已有 | 完整 |

## 3. 优先改进项（按依赖顺序）

### 改进 1: Termination reason + event trace

**目标**：让每次 Agent run 可观测、可回放、可调试

**变更**：
- `core/agent_loop.py`: `run_stream()` 每次循环结束输出 `termination_reason`（`max_iter` / `timeout` / `stop_token` / `final_answer` / `error`）
- `core/agent_loop.py`: 新增 event writer，把 `assistant_delta` / `tool_start` / `tool_end` / `assistant_done` 写入 `.bobodan/traces/<session_id>_<turn>.jsonl`
- `core/agent_loop.py`: 把 `termination_reason` 传给 REPL，REPL 在响应末尾显示
- 新增 `tools/trace_view.py` Agent 工具：`trace_view(session_id, turn)` 回放指定 turn

**复用**：
- 现有的 `run_stream()` 事件流（`assistant_delta`, `tool_start`, `tool_end`）
- 现有的 `Session` 持久化（`.session/`）

**测试**：
- `tests/test_termination_reason.py`: 不同终止路径（max iter、timeout、final answer）
- `tests/test_event_trace.py`: trace 文件写入、格式、回放

**验证**：
- 运行一次复杂 turn，查看 `.bobodan/traces/` 下的 jsonl
- 模拟 max iter，看 trace 包含完整 8 轮循环
- `trace_view` 工具能回放 turn

---

### 改进 2: Tool risk class + approval gate

**目标**：高风险工具执行前必须用户确认

**变更**：
- `tools/base.py`: `register_tool()` 新增 `risk_class` 参数，可选 `read` / `draft` / `write` / `external` / `destructive` / `privileged`，默认 `write`
- `tools/base.py`: `execute_tool()` 在 risk ≥ `external` 时返回需要 approval 的 `ToolResult(ok=False, data={"approval_required": True, "reason": "..."})`
- `core/agent_loop.py`: 处理 approval_required，emit `approval_request` 事件给 REPL
- `cli/repl.py`: 收到 approval_request 事件时打印风险提示和工具调用，询问用户确认/拒绝
- `core/agent_loop.py`: 用户拒绝时构造 `tool` message 包含拒绝原因，让 LLM 调整

**哪些工具需要 approval**：

| 工具 | 当前 | 建议 |
|------|------|------|
| `read_file` | 自动 | `read` |
| `list_dir` | 自动 | `read` |
| `rag_search` | 自动 | `read` |
| `graph_query` | 自动 | `read` |
| `memory_recall` | 自动 | `read` |
| `write_file` | 自动 | `write`（默认还是自动，记录） |
| `write_file overwrite=true` | 自动 | `destructive`（要 approval） |
| `change_dir` | 自动 | `write` |
| `http_request GET` | 自动 | `read` |
| `http_request POST/PUT/DELETE` | 自动 | `external`（要 approval） |
| `memory_save` | 自动 | `write` |
| `memory_forget` | 自动 | `destructive`（要 approval） |
| `obsidian_sync` | 自动 | `write`（记录） |
| `wiki_ingest` | 自动 | `write`（记录） |
| `http_request` | 自动 | 看 method |

**复用**：
- 现有 `ToolResult` 结构（`ok`, `content`, `data`）
- 现有 `execute_tool()` 入口
- 现有 `run_stream()` 事件流（新增 `approval_request` 事件类型）

**测试**：
- `tests/test_tool_risk.py`: risk class 注册、查询
- `tests/test_approval_gate.py`: 模拟 approval 流程（确认、拒绝、超时）

**验证**：
- 触发 `write_file overwrite=true`，REPL 打印风险提示等待确认
- 拒绝后 LLM 收到拒绝信息调整行为

---

### 改进 3: Prompt cache 优化

**目标**：稳定前缀放在 system prompt 头部，动态内容放尾部，让 prompt cache 高效命中

**变更**：
- `core/agent_loop.py`: 重组 system prompt 顺序为 `[base_identity, skills_catalog, memory_static, user_context, daily_memory]`
  - 稳定部分（base + skills + 静态记忆）：几乎不变
  - 动态部分（user context + 每日记忆）：每天变
- `core/memory.py`: `build_memory_prompt()` 拆分永久记忆（静态）vs 每日记忆（动态）
- `providers/factory.py`: 标注 prompt cache 边界（Anthropic 用 `cache_control: ephemeral`，OpenAI 自动）
- 监控 `core/agent_loop.py` 的 token usage 变化

**复用**：
- 现有 `build_memory_prompt()`（拆分静态/动态）
- 现有 `build_skills_system_prompt()`（放稳定前缀）
- 现有 providers（增加 cache_control 标记）

**测试**：
- `tests/test_prompt_cache.py`: 验证 system prompt 顺序、cache_control 标记
- 监控 token 消耗（手动）

**验证**：
- 跑同一 session 的连续 turn，对比 cache hit rate
- 看 provider 返回的 `cache_creation_input_tokens` / `cache_read_input_tokens`

---

### 改进 4: Plan mode

**目标**：复杂任务先规划再执行，用户可审核计划

**变更**：
- `core/plan_mode.py`: 新增 `PlanMode` 状态机（`idle` → `planning` → `awaiting_approval` → `executing` → `done`）
- `core/agent_loop.py`: 加 `_plan_mode` 参数，进入 plan 模式时先调一次 LLM 输出结构化计划（JSON：`{steps: [{action, tool, args, risk, depends_on}]}`）
- `cli/repl.py`: `/plan <task>` 命令进入 plan 模式
- `cli/repl.py`: 计划展示用 Rich 表格，含步骤、工具、风险等级
- `core/agent_loop.py`: 用户确认后按计划步骤执行，每步关联到改进 2 的 approval gate

**复用**：
- 现有 `run_stream()` 事件流
- 现有 `ToolResult` 结构
- 改进 1 的 event trace
- 改进 2 的 approval gate

**测试**：
- `tests/test_plan_mode.py`: 计划生成、用户确认、步骤执行
- `tests/test_plan_dependencies.py`: 步骤依赖关系处理

**验证**：
- `/plan "写一个学习 python 装饰器的学习计划"`，LLM 输出步骤列表
- 用户确认后逐步执行，遇到 risk ≥ external 的步骤走 approval gate
- 计划存进 trace，方便回放

---

## 4. 依赖关系

```
1. Termination reason + event trace  (基础)
   ↓
2. Tool risk class + approval gate   (安全)
   ↓
3. Prompt cache 优化                  (成本)
   ↓
4. Plan mode                         (体验)
```

1 是基础设施，所有后续改进都依赖 event trace。2 解决安全问题，跟 4 的 plan mode 配合。3 独立可做。4 是最高层 UX 改进，依赖 1+2。

## 5. 关键文件

| 操作 | 文件 |
|------|------|
| 修改 | `core/agent_loop.py` — 改进 1+2+4 |
| 修改 | `tools/base.py` — 改进 2 |
| 修改 | `cli/repl.py` — 改进 1+2+4 |
| 修改 | `core/memory.py` — 改进 3 |
| 修改 | `providers/factory.py` — 改进 3 |
| 新建 | `core/plan_mode.py` — 改进 4 |
| 新建 | `tools/trace_view.py` — 改进 1 |
| 新建 | `tests/test_termination_reason.py` |
| 新建 | `tests/test_event_trace.py` |
| 新建 | `tests/test_tool_risk.py` |
| 新建 | `tests/test_approval_gate.py` |
| 新建 | `tests/test_prompt_cache.py` |
| 新建 | `tests/test_plan_mode.py` |

## 6. 复用的现有模块

| 模块 | 用途 |
|------|------|
| `core/agent_loop.py` | `run_stream()` 事件流、`_complete_with_events()` |
| `core/session.py` | Session 持久化、消息裁剪 |
| `core/memory.py` | `MemoryManager`、`build_memory_prompt()` |
| `core/skills.py` | `build_skills_system_prompt()` |
| `tools/base.py` | `ToolResult`、`register_tool()`、`execute_tool()` |
| `tools/obsidian_tool.py` | approval gate 集成示例 |
| `cli/repl.py` | `run_agent_streaming()`、tool display |

## 7. 验收标准

每项改进完成后验证：

**改进 1**：
- [ ] `termination_reason` 出现在所有 run 输出
- [ ] `.bobodan/traces/<id>_<turn>.jsonl` 文件存在且格式正确
- [ ] `trace_view` 工具能回放 turn
- [ ] 模拟 max iter 终止，trace 包含完整 8 轮

**改进 2**：
- [ ] `register_tool()` 支持 `risk_class` 参数
- [ ] 高风险工具执行前 REPL 打印风险提示
- [ ] 用户拒绝后 LLM 收到拒绝信息
- [ ] 所有 346+ 测试无回归

**改进 3**：
- [ ] System prompt 顺序按 `[base, skills, static_memory, dynamic_memory]` 组织
- [ ] Provider 标记 cache_control
- [ ] 连续 turn 的 cache hit rate > 50%

**改进 4**：
- [ ] `/plan <task>` 命令进入 plan 模式
- [ ] LLM 输出结构化计划
- [ ] 用户确认后逐步执行
- [ ] Plan 存进 trace
- [ ] 风险步骤走 approval gate

## 8. 执行顺序

按依赖图推进，每项独立可测试：

1. **改进 1**（1-2 天）— 先做 event trace，所有后续改进都依赖它
2. **改进 2**（2-3 天）— 风险门禁，安全性提升
3. **改进 3**（1 天）— 独立可做，成本优化
4. **改进 4**（2-3 天）— 体验改进，依赖 1+2

预计总工作量 6-9 天。
