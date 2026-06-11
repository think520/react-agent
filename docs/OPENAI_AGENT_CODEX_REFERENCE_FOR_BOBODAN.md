# Bobodan 对 OpenAI Agents SDK 与 Codex CLI 的借鉴建议

> 日期：2026-06-10  
> 目的：对照 OpenAI Agents SDK 与 Codex CLI 的公开文档，判断 Bobodan 哪些地方值得借鉴、哪些不应照搬，并给出可落地的改造顺序。

## 0. 结论

Bobodan 不建议迁移成 OpenAI Agents SDK 项目，也不建议复制 Codex CLI 的完整工程形态。

更合理的方向是：

> 保留 Bobodan 作为 local-first learning agent runtime 的定位，把 OpenAI Agents SDK 与 Codex CLI 中已经成熟的工程边界吸收进来：run state、event trace、handoff 协议、tool policy、skills 渐进加载、MCP 边界、配置与本地指令层级。

换句话说，Bobodan 应该学习它们的“运行时骨架”和“安全/可观测边界”，而不是学习它们的产品目标。

当前 Bobodan 已经有：

- `core/agent_loop.py`：ReAct agent loop、stream event、tool call 编排。
- `tools/base.py`：工具注册、schema 暴露、`ToolResult` 结构化返回。
- `core/skills.py`：本地 skill catalog 与按需读取提示。
- `mcp_client/`：stdio / SSE / streamable_http MCP client。
- `agents/runner.py` 与 `tools/agents.py`：specialist 子 agent 与 `delegate_*` 工具。
- `memory/`、`learning/`、`quiz/`、`rag/`、`wiki/`：学习闭环相关业务层。

因此，最有价值的借鉴不是“再加一个 agent 框架”，而是把这些已经存在的能力整理成更稳定的协议。

## 1. 官方文档要点

### 1.1 OpenAI Agents SDK

OpenAI Agents SDK 的核心抽象是：

| 能力 | 文档要点 | Bobodan 可借鉴点 |
|---|---|---|
| Agent | Agent 封装 instructions、model、tools、handoffs、guardrails 等。 | Bobodan 不需要照搬类名，但可以让每次 run 有清晰的 instructions、tool set、guardrail/policy、handoff 配置。 |
| Runner / Agent loop | Runner 执行 agent loop，自动处理模型输出、tool call、handoff，直到 final output。 | Bobodan 已有 `AgentLoop.run_stream()`，应补齐 run_id、termination_reason、result object、trace 写入。 |
| Tools | 支持 function tools、hosted tools、agents-as-tools、MCP servers。 | Bobodan 已有内置 tools + MCP tools + delegate tools，应统一工具元数据和风险分级。 |
| Handoffs | 适合把任务移交给另一个专业 agent；文档也区分 handoff 与 “agents as tools”。 | Bobodan specialist v1 已接近 agents-as-tools；v2 可补 handoff reason、scope、parent_run_id。 |
| Guardrails | 输入/输出 guardrail 可在 agent 运行前后做检查。 | Bobodan 可先做轻量 tool policy 与输出检查，不必上复杂安全框架。 |
| Tracing | SDK 内置 trace/span，用于调试、可视化、评估。 | Bobodan 应先落地本地 JSONL trace，再服务 CLI/Web UI。 |
| Sessions | SDK 有 session 概念，用于自动保存对话历史。 | Bobodan 已有 `.session/`，但需要把“对话 session”和“一次 run 的执行记录”分开。 |
| MCP | Agents SDK 可把 MCP server 作为工具源。 | Bobodan 已是 MCP client，下一步是把 MCP tool 与内置 tool 放进同一 policy/trace 模型。 |

### 1.2 Codex CLI

Codex CLI 的关键不是“会写代码”，而是它围绕本地工作区建立了一套操作边界：

| 能力 | 文档要点 | Bobodan 可借鉴点 |
|---|---|---|
| 本地工作区 + sandbox/approvals | Codex 按 workspace、sandbox、approval policy 控制文件和命令操作。 | Bobodan 当前是 trust-first，可先引入轻量 tool risk class，不必马上做完整 sandbox。 |
| `AGENTS.md` | 用 repo 内文档承载持久项目规则，且 closer/nested guidance 优先。 | Bobodan 可借鉴为课程/知识库级 instructions，例如 `BOBODAN.md` 或 `.bobodan/instructions.md`。 |
| Skills | Codex skills 通过 metadata 先暴露描述，触发时再读取正文。 | Bobodan `core/skills.py` 已经类似；建议增加 skill 使用 trace 与相对路径资源规则。 |
| MCP | Codex 可通过 MCP 接入外部系统和私有上下文。 | Bobodan MCP client 已有，建议先完善状态、错误、权限与 trace，而不是急着做 MCP server。 |
| Hooks | Codex 可在生命周期节点执行 hooks，用于检查或自动化。 | Bobodan 可在 workflow/run 层做最小 hook，先用于导出、审计、测试，不要进入主 loop。 |
| Subagents | Codex 用子 agent 分离上下文和任务。 | Bobodan specialist 已经做了隔离 session、工具过滤、timeout，很值得继续强化。 |
| 配置层级 | Codex 区分项目配置、全局配置、环境/权限等。 | Bobodan 当前 `config.yaml` 可继续保留，但应明确 project / user / runtime 三层配置边界。 |

## 2. Bobodan 当前相同点

### 2.1 Agent loop 已经具备 Runner 雏形

`core/agent_loop.py` 已经完成了 SDK Runner 的几个核心动作：

- 注入 skills、memory、MCP system prompt。
- 调 LLM provider。
- 解析 tool calls。
- 执行 tools。
- 把 tool result 写回 session。
- 通过 `run_stream()` 对 CLI 暴露 `assistant_delta`、`tool_start`、`tool_end`、`assistant_done`。

缺口在于：这些 event 还只是 UI-friendly dict，不是稳定协议。当前 `assistant_done` 也缺少结构化 `termination_reason`。这正好对应现有 `docs/NEXT_STEPS_EXECUTION_PLAN.md` 里的 Event Trace 轻量版方向。

建议：

```text
core/events.py
  AgentEvent
  RunStart
  AssistantDelta
  ToolStart
  ToolEnd
  SpecialistEvent
  AssistantDone
  ErrorEvent

core/run_result.py
  RunResult
  run_id
  session_id
  final_output
  termination_reason
  events_count
  tool_calls_count
  elapsed_ms
```

不要一开始引入复杂 span/tree，只要先让事件稳定、可序列化、可测试。

### 2.2 Tools 与 Agents SDK function tools 很接近

`tools/base.py` 已经有：

- `register_tool(name, description, params_schema, func)`
- `get_tools_schema()`
- `execute_tool(name, args, session)`
- `ToolResult(ok, content, data)`

这和 Agents SDK function tools 的思想很像：工具需要 schema，模型看到 schema 后选择调用，runtime 执行并返回结果。

缺口在于 tool metadata 不够：

```python
ToolMetadata(
    name: str,
    risk: Literal["read", "write", "external", "destructive"],
    origin: Literal["builtin", "mcp", "specialist"],
    requires_confirmation: bool,
    timeout_seconds: int | None,
    trace_content: Literal["full", "summary", "redacted"],
)
```

Bobodan 现在不必做 Codex 级 sandbox，但应该先知道“这个工具是什么风险”。否则后面 Web UI、Obsidian 写回、MCP 外部工具都会越来越难控。

### 2.3 Specialist 已经接近 handoff / agents-as-tools

Bobodan 的 `agents/runner.py` 已经有很多成熟边界：

- fresh session，不污染父 agent 上下文。
- tool allowlist。
- hard deny `delegate_*`、`memory_*`。
- 默认不开放 MCP。
- timeout。
- invocation record。
- output cap。
- triage contract validation。

这比很多早期 agent 项目更克制。可以借鉴 Agents SDK 的 handoff 语义继续补强：

```text
handoff_request:
  parent_run_id
  specialist_name
  reason
  task
  allowed_tools
  expected_output_schema

handoff_result:
  child_run_id
  ok
  output
  error_type
  elapsed_ms
  events_summary
```

但暂时不要开放递归 specialist、并行 specialist、specialist 默认 MCP。现有 v1 边界是对的。

### 2.4 Skills 已经采用渐进加载思想

`core/skills.py` 已经扫描 `skills/*/SKILL.md`，只把 name、description、location 注入 system prompt，并要求匹配任务时再读取正文。这和 Codex skills 的 progressive disclosure 很接近。

可以继续补：

- skill 使用事件：`skill_selected`、`skill_loaded`、`skill_skipped`。
- skill 资源边界：相对路径必须解析到 skill 目录下。
- skill 版本/来源：方便未来同步个人技能库。
- skill 测试：每个高价值 skill 至少有一个 smoke prompt 或 fixture。

不建议现在做 skill marketplace。Bobodan 的主线是个人学习闭环，不是扩展市场。

### 2.5 MCP client 已经够先进，下一步是治理

`mcp_client/` 已支持：

- stdio
- SSE
- streamable_http
- lazy connect
- per-server state
- reload diff
- tool wrapper
- prompt injection

这和 Agents SDK / Codex CLI 的 MCP 使用方向一致。

下一步重点不是“支持更多 MCP 功能”，而是：

- MCP tool 进入统一 tool metadata。
- MCP tool call 写 trace。
- MCP server status 进入 `/status` 或 Web UI。
- MCP 错误不要只返回文本，要有 `error_type`、server、tool、transport。
- 远程 MCP 默认 risk = `external`。

暂时不建议把 Bobodan 暴露成 MCP server。只有当 `kb_search`、`wiki_lookup`、`quiz_status` 等能力稳定后，再考虑让其他 agent 调 Bobodan。

## 3. 值得借鉴的设计

### 3.1 Run state：把“一次运行”变成一等对象

Agents SDK 和 Codex 都强调 run 过程可追踪。Bobodan 当前 session 是长期对话概念，但一次 agent run 的结构还不够明确。

建议新增最小 run state：

```text
run_id
session_id
started_at
ended_at
status: running | completed | failed | cancelled | max_iter
termination_reason: final_answer | max_iter | error | cancelled
provider
model
tool_calls_count
specialist_calls_count
trace_path
final_output
```

落地位置：

```text
core/run_state.py
core/trace.py
.bobodan/runs/
.bobodan/traces/
```

收益：

- CLI 可以显示“上次做了什么”。
- Web UI 可以复用。
- workflow runtime 有执行记录。
- 出错时能定位是 provider、tool、MCP、specialist 还是 max_iter。

### 3.2 Event trace：先本地 JSONL，不急着做复杂 UI

Agents SDK 有 tracing，Codex 也有围绕操作过程的可观测能力。Bobodan 最应该先做的是本地 JSONL：

```json
{"type":"run_start","run_id":"...","session_id":"...","ts":"..."}
{"type":"tool_start","run_id":"...","tool_name":"rag_search","args_summary":"..."}
{"type":"tool_end","run_id":"...","tool_name":"rag_search","ok":true,"elapsed_ms":120}
{"type":"assistant_done","run_id":"...","termination_reason":"final_answer"}
```

注意：

- 不写 API key。
- 默认不写完整 assistant token delta。
- tool args 默认 summary/redacted。
- MCP headers/env 永远不写 trace。
- trace writer 必须可选，不注入时行为不变。

这比一开始做 Web trace panel 更稳。

### 3.3 Tool policy：从 metadata 开始，不从拦截器开始

Codex 的 sandbox/approval 很成熟，但 Bobodan 是单用户本地学习工具，直接照搬会过重。

建议第一阶段只做 metadata + audit：

```text
read_file          risk=read
write_file         risk=write
http_request       risk=external
obsidian_sync      risk=write
memory_save        risk=write
mcp:*              risk=external
delegate_*         risk=specialist
```

第二阶段再做最小确认：

- `destructive` 必须确认。
- remote MCP 写操作必须确认。
- workspace 外写入必须拒绝或确认。
- Obsidian 导出要显示目标路径。

不要把所有 write tool 都变成确认，否则本地学习体验会变笨。

### 3.4 Handoff 协议：保留 specialist，但让移交可解释

Agents SDK 的 handoff 适合多专业 agent。Bobodan 的 specialist v1 已经方向正确，但 parent agent 现在看到的主要是工具调用结果。

建议补三件事：

1. `handoff_reason`：为什么交给 specialist。
2. `expected_output_schema`：希望 specialist 返回什么结构。
3. `child_run_id`：可在 trace 中追踪子运行。

示例：

```json
{
  "type": "specialist_start",
  "parent_run_id": "run_1",
  "child_run_id": "run_1_doc_reader_1",
  "specialist": "doc_reader",
  "reason": "long document summarization",
  "allowed_tools": ["read_file"]
}
```

这样 Bobodan 的 specialist 就能从“隐藏工具调用”升级成“可观测的任务移交”。

### 3.5 Guardrails：优先保护学习质量，而不只是保护系统

Agents SDK 的 guardrails 通常用于输入/输出检查。Bobodan 可以把 guardrails 用在自己的学习产品主线上：

输入 guardrails：

- quiz 题目必须绑定 source / concept。
- learning plan 必须有目标、天数、可执行任务。
- wiki ingest 不允许把生成内容当 truth source。

输出 guardrails：

- 题目答案必须有解释。
- wiki 页面必须带 source paths / hashes。
- 学习计划不能只给空泛建议。
- RAG answer 必须标明依据不足时的不确定性。

这比泛泛做安全过滤更符合 Bobodan。

### 3.6 指令层级：借鉴 `AGENTS.md`，但命名服务 Bobodan

Codex 的 `AGENTS.md` 很适合 repo 规则。Bobodan 面向个人知识库和课程，可以借鉴为：

```text
.bobodan/instructions.md             # 用户全局学习偏好
课程目录/BOBODAN.md                  # 某门课/某个 vault 的规则
课程目录/子主题/BOBODAN.md           # 更近的规则优先
skills/*/SKILL.md                    # 任务型流程
```

优先级建议：

```text
用户当前输入 > 当前目录 BOBODAN.md > 上级目录 BOBODAN.md > .bobodan/instructions.md > skill instructions > 默认 system prompt
```

注意：这不需要和 Codex 一样叫 `AGENTS.md`。Bobodan 的目标不是 coding repo，`BOBODAN.md` 或 `.bobodan/instructions.md` 更贴合。

### 3.7 配置层级：拆开 user / project / runtime

Codex 文档很重视配置边界。Bobodan 当前主要是 `config.yaml`，后面功能多了之后建议分三层：

```text
user config:
  用户默认 provider、模型、UI 偏好、默认 vault

project config:
  当前知识库、课程、MCP server、RAG backend、Obsidian vault

runtime config:
  本次 run 的 max_iterations、allowed_tools、trace 开关、approval policy
```

先不急着拆文件，可以先在文档和 dataclass 上拆概念，避免所有东西继续塞进一个全局 config。

### 3.8 Hooks：只在 workflow 边界做，不进 agent loop 内核

Codex hooks 用于生命周期自动化。Bobodan 可以借鉴，但要克制。

适合的 hook：

- `after_quiz_submit`：写 daily memory、更新 mastery。
- `after_learning_plan_created`：可选导出 Obsidian。
- `after_kb_sync`：写 import report。
- `after_run_end`：写 trace summary。

不适合的 hook：

- 每个 token delta hook。
- 每个 LLM call 前后都执行复杂逻辑。
- 让 hook 修改 prompt 或工具列表。

Bobodan 先做 domain hook，不要做通用 hook 平台。

## 4. 不建议照搬的地方

### 4.1 不建议直接引入 OpenAI Agents SDK 作为核心 runtime

原因：

- Bobodan 已有 provider 抽象，支持 MiniMax / DeepSeek / OpenAI-compatible / local 方向。
- Bobodan 的主线是本地学习闭环，不是 OpenAI-only agent app。
- 迁移 SDK 会把已有 tools、memory、MCP、specialist、session 改成适配层，收益不明显。

可以借鉴概念，不迁移依赖。

### 4.2 不建议做 Codex 级 sandbox

Bobodan 不是 coding agent，主要写 `.bobodan/`、`.knowledge/`、Obsidian vault 和 workspace 文件。

建议先做：

- workspace path boundary。
- write target preview。
- destructive operation confirmation。
- MCP remote tool 标记。

不要一开始做命令 sandbox、网络 sandbox、复杂 approval matrix。

### 4.3 不建议现在做完整 plugin marketplace

Bobodan 已经有 skills、tools、MCP、specialists。真正缺的是稳定协议，不是 marketplace。

优先级：

```text
tool metadata
event schema
trace
workflow runtime
skill usage trace
MCP governance
```

plugin marketplace 至少应该排在 Web UI 稳定之后。

### 4.4 不建议把 specialist 做成无限多 agent

Agents SDK 可以组织多个 agent，但 Bobodan 的 specialist 应该服务学习任务。

当前 3 个 specialist：

- `doc_reader`
- `triage`
- `planner`

已经足够验证机制。下一步应提高它们的 contract 和 trace，而不是继续新增一堆名字。

## 5. 建议落地顺序

### P0：Run / Event / Trace 最小闭环

目标：让 Bobodan 每次运行都可解释、可恢复、可调试。

改动：

- `assistant_done` 增加 `termination_reason`。
- 新增 `core/trace.py`，写 `.bobodan/traces/*.jsonl`。
- 每次 run 生成 `run_id`。
- tool event 统一 `elapsed_ms`、`ok`、`error_type`。
- specialist event 带 `parent_run_id` / `child_run_id`。

验收：

- 普通聊天、tool call、max_iter、tool error 都有 trace。
- trace 不含 API key、MCP headers、完整 token stream。
- 不启用 trace writer 时现有行为不变。

### P1：Tool metadata 与轻量 policy

目标：先知道每个工具的来源和风险。

改动：

- `register_tool()` 支持可选 metadata。
- MCP wrapper 自动加 `origin=mcp`、`risk=external`。
- delegate tools 自动加 `origin=specialist`。
- file/memory/obsidian tools 标记 read/write。
- `/tools` 或 `/status` 能显示 tool origin/risk。

验收：

- 内置 tool、MCP tool、delegate tool 都能看到 origin。
- trace 里记录 tool origin/risk。
- 暂不强制 approval，只做 audit。

### P2：Specialist handoff v2

目标：让 specialist 调用成为清晰的 handoff，而不是普通工具黑箱。

改动：

- delegate tool 参数增加 `reason` 或在 task 中结构化记录 reason。
- `run_specialist()` 生成 child run。
- specialist result 返回 `handoff_result`。
- triage/planner/doc_reader 输出 schema 更稳定。

验收：

- 父 trace 能看到子 agent 的开始、结束、耗时、错误类型。
- 子 agent 仍不能调用 `delegate_*`、`memory_*`。
- 默认仍不允许 MCP。

### P3：学习产品 guardrails

目标：把 guardrails 用在 Bobodan 的学习质量上。

改动：

- quiz 题目生成必须有 concept/source。
- learning plan 必须有可执行任务。
- wiki ingest 输出必须带 source metadata。
- RAG answer 在证据不足时明确说明不足。

验收：

- 不合格输出返回结构化错误或要求重试。
- guardrail failure 写入 trace。
- 不把 guardrail 写死在 CLI。

### P4：Bobodan instructions 层级

目标：让不同课程、vault、项目有持久规则。

改动：

- 支持 `.bobodan/instructions.md`。
- 支持就近读取 `BOBODAN.md`。
- 注入 prompt 时标明来源和优先级。
- 文档说明与 skills 的关系。

验收：

- 同一 workspace 不同子目录可以有不同学习规则。
- 当前用户输入优先级最高。
- skill 仍然是任务流程，不被长期项目规则替代。

### P5：Workflow hooks

目标：让学习闭环自动发生，但不污染 agent loop。

改动：

- `after_quiz_submit`
- `after_learning_plan_created`
- `after_kb_sync`
- `after_run_end`

验收：

- hook 可测试、可禁用。
- hook 不修改 prompt。
- hook failure 不破坏主流程，写 trace。

## 6. 和现有执行计划的关系

当前 `docs/NEXT_STEPS_EXECUTION_PLAN.md` 把下一步放在学习闭环 P0：`quiz_submit` 写 daily memory + 更新 mastery。这仍然是产品价值上的第一优先级。

本文建议的 OpenAI/Codex 借鉴项，不应该打断这个顺序。更合理的合并方式是：

```text
产品主线：
  quiz_submit -> daily memory -> mastery -> review -> Obsidian export

工程底座：
  termination_reason -> trace -> tool metadata -> specialist handoff
```

也就是说：

- 如果正在做学习闭环，就继续做。
- 但在改 `quiz_submit`、memory、mastery 时，顺手按 trace/event/policy 的方向留接口。
- 不要因为研究 Agents SDK / Codex CLI 就突然转向“通用 agent 平台”。

## 7. 推荐的第一个小 PR

如果只做一个最小 PR，建议是：

```text
feat(agent): add run termination reason and local trace writer
```

范围：

- `core/agent_loop.py`
  - `assistant_done` 增加 `termination_reason`。
  - tool error / max_iter / final_answer 区分。
- `core/trace.py`
  - 新增可选 JSONL trace writer。
- `cli/repl.py`
  - 创建 trace writer 并注入 AgentLoop。
- tests
  - final_answer
  - max_iter
  - tool_start/tool_end JSONL
  - trace redaction

为什么先做它：

- 改动小。
- 不改变产品交互。
- 对 Web UI、workflow、specialist、MCP governance 都有帮助。
- 和 Agents SDK tracing、Codex 可观测思路一致。

## 8. 官方资料来源

本建议基于以下官方/公开文档与当前 Bobodan 代码阅读：

- OpenAI Agents SDK 文档：https://openai.github.io/openai-agents-python/
- Agents SDK - Running agents：https://openai.github.io/openai-agents-python/running_agents/
- Agents SDK - Tools：https://openai.github.io/openai-agents-python/tools/
- Agents SDK - Handoffs：https://openai.github.io/openai-agents-python/handoffs/
- Agents SDK - Guardrails：https://openai.github.io/openai-agents-python/guardrails/
- Agents SDK - Tracing：https://openai.github.io/openai-agents-python/tracing/
- Agents SDK - Sessions：https://openai.github.io/openai-agents-python/sessions/
- Agents SDK - MCP：https://openai.github.io/openai-agents-python/mcp/
- Codex CLI 文档入口：https://developers.openai.com/codex/cli
- Codex customization / AGENTS.md / skills / MCP：https://developers.openai.com/codex/concepts/customization
- Codex approvals and security：https://developers.openai.com/codex/agent-approvals-security
- Codex subagents：https://developers.openai.com/codex/subagents
- Codex advanced config / hooks：https://developers.openai.com/codex/config-advanced

说明：本次尝试使用本地 `openai-docs` helper 拉取 `https://developers.openai.com/codex/codex-manual.md` 时，开发者站点对 HEAD 请求返回 HTTP 403；因此 Codex 部分改用 `developers.openai.com/codex/*` 官方页面直接核对。

## 9. 最后判断

Bobodan 和 OpenAI Agents SDK / Codex CLI 最大的共同点是：

```text
LLM 不应该直接等于产品。
真正重要的是：工具边界、运行状态、事件、trace、权限、handoff、配置和持久指令。
```

Bobodan 现在已经有足够多的“能力模块”。下一阶段最重要的不是继续堆功能，而是把现有能力变成可观测、可治理、可复用的本地学习 agent runtime。

