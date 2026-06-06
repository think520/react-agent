# Learning Agent Orchestrator — v1 Design

> 实现版本：v1 骨架
> 协议/参考：MCP 集成（`mcp_client/`）+ skills + tools 体系
> 配套文档：[`MCP.md`](MCP.md)

## 1. Background & Goals

Bobodan 当前是**单 AgentLoop** —— 一个 ReAct 循环跑完所有任务，~25 个内置工具加 MCP 工具。这条路径在"主线任务"上工作良好，但**没有覆盖**多 agent 体系可以提供的几个价值：

- **上下文隔离**：长任务跑完不污染主 session
- **权限沙箱**：给某段工作"小房间"，限制工具集
- **模型替换**：便宜/快模型干特定活
- **专注**：系统提示针对任务类型优化

这些价值 v1 **不需要全部实现**，但要**留下清晰的扩展点**。

**v1 目标**：搭建骨架 + 留边界 + 证明一个 specialist 真正比主 agent 自己做某件事强。命名 **Learning Agent Orchestrator** —— 强调是"按任务派活给 specialist"，**不**是 peer-to-peer 自由聊天，也不叫 "multi-agent framework"。

**v2 才会做**：递归 delegation、并行 specialist、跨失败转移、完整 trace 系统。

## 2. Vocabulary

| 术语 | 含义 |
|------|------|
| **Orchestrator** | 主 AgentLoop。它**就是** orchestrator，不是一个独立类 |
| **Specialist** | 一个 sub-AgentLoop 实例，按 specialist config 跑独立任务 |
| **Delegate tool** | 父 LLM 调用的入口 tool：`delegate_doc_reader` / `delegate_triage` / `delegate_planner` |
| **Fresh session** | specialist 启动的空 `Session`，继承 parent `cwd` 和 `workspace_root`，不继承 `messages` |
| **sub-AgentLoop** | runner 用 specialist config 创建的 `AgentLoop` 实例（独立 model / tools / max_iterations） |
| **`data_to_content()`** | specialist 自己的 helper，把 `data.result` 序列化成可读字符串塞进 `content` |
| **allow_mcp / allowed_tools** | specialist config 的工具白名单两道门（见 Decision 13） |

## 3. Architecture Overview

```
                            ┌─────────────────────────────────────────────┐
                            │  REPL / main bobodan AgentLoop              │
                            │  tools_schema = builtin + mcp + delegates   │
                            │  session = parent_session (live)            │
                            └────────────────────┬────────────────────────┘
                                                 │ parent LLM emits tool_call
                                                 │ name = "delegate_doc_reader"
                                                 ▼
                            ┌─────────────────────────────────────────────┐
                            │  delegate_doc_reader(...) tool wrapper      │
                            │  validates schema → calls runner            │
                            └────────────────────┬────────────────────────┘
                                                 │ runner.run("doc_reader", task_text)
                                                 ▼
                            ┌─────────────────────────────────────────────┐
                            │  agents/runner.py                           │
                            │  • fresh = Session.new(parent.cwd)          │
                            │  • fresh.workspace_root = parent.workspace  │
                            │  • inject specialist system_prompt          │
                            │  • pass task to sub_loop.run_stream(task)   │
                            │  • build tools: filter delegate_/memory_    │
                            │                  apply allow_mcp/allowlist │
                            │  • create sub-provider (capped timeout)     │
                            │  • executor.submit(run_stream, timeout=cfg) │
                            │  • catch all → ToolResult(ok, content, data)│
                            └────────────────────┬────────────────────────┘
                                                 │
                                                 ▼
                            ┌─────────────────────────────────────────────┐
                            │  sub-AgentLoop (isolated)                   │
                            │  • its own session (fresh, no parent msgs)  │
                            │  • its own model (per cfg.provider/model)    │
                            │  • its own tool set (filtered)              │
                            │  • its own max_iterations                    │
                            │  • its own timeout_seconds (30/60/120)      │
                            │  Returns: final_response + display_events   │
                            └────────────────────┬────────────────────────┘
                                                 │
                                                 ▼
                            runner formats → ToolResult(content, data)
                                                 │
                                                 ▼
                            parent LLM sees tool message (content only)
                            specialist internals are NOT in parent session
```

**关键观察**：
- 主 AgentLoop 不知道 specialist 内部发生了什么
- specialist 不知道父 session 发生过什么
- 唯一决策数据流：`task_text` 进去，`content` 出来
- delegate wrapper 负责把 tool schema 参数转成 specialist task；`doc_reader` 必须把 `source_paths` 原样列出，禁止缩短为 basename
- v1 的自动触发是 LLM tool selection，不是硬编码路由；`delegate_doc_reader` 和 `read_file` 的 tool description 必须明确：读并总结文件时优先用 `delegate_doc_reader`

## 4. Module Layout

```
agents/                              # 新顶层包
  __init__.py
  base.py                            # BaseSpecialist ABC
  config.py                          # Python defaults + YAML merge，schema 校验
  registry.py                        # SpecialistRegistry + last_invocations deque
  runner.py                          # run(name, task, parent_session) → ToolResult
  prompt.py                          # system_prompt 模板（含 "no memory / no delegation" 提示）
  specialists/
    __init__.py
    doc_reader.py                    # DocReaderSpecialist
    triage.py                        # TriageSpecialist（窄合约）
    planner.py                       # PlannerSpecialist

tools/
  agents.py                          # 注册 3 个 delegate tool

config.yaml                          # 新增 specialists: 段
```

**职责分工**：
- `base.py`：定义 specialist 必须实现的契约
- `config.py`：解析 YAML + Python default merge
- `registry.py`：管"有哪些" specialist + 最近调用状态
- `runner.py`：管"怎么跑"（registry 不知道执行细节）
- `prompt.py`：渲染 system prompt（v1 用固定模板，v2 动态化）

## 5. Decision Summary

| # | 决策 | 核心点 |
|---|------|-------|
| 1 | 3 个 delegate tool（`delegate_doc_reader` / `delegate_triage` / `delegate_planner`），**主 bobodan 派活给 specialist，不是 peer-to-peer** | 跟主 ReAct 零摩擦 |
| 2 | v1 specialist：doc_reader / triage / planner | triage 窄合约（5 字段） |
| 3 | 混合 Python + YAML 注册 | v1 YAML 不开"纯 YAML 新建 specialist" |
| 4 | 每个 specialist 跑在 fresh session | parent.messages 永远不变 |
| 5 | 每个 tool 自己的 schema（user_goal / source_paths / ...） | delegate wrapper 把结构化参数转成 task_text；`doc_reader.source_paths` 必须完整保真 |
| 6 | 硬禁递归（code-level filter） | specialist 工具集永远无 `delegate_*` |
| 7 | per-specialist wall-clock timeout（30/60/120s） | provider request timeout 也被 cap 到 `min(base, cfg)` |
| 8 | ToolResult 双层（content 给 LLM / data 给 trace） | **父 LLM 只看到 content；结构化结果如果会影响决策，必须经 `data_to_content()` 放进 content** |
| 9 | REPL 显示 A2 + B2-lite + C2 | delegate 开始时显示 running；内部 tool events 作为 UI-only event 缩进显示；无倒计时 + 错误 header |
| 10 | guarded catch + no automatic retry | Triage 校验 `recommended_specialist`；content ≤ 500 chars |
| 11 | `/specialists` 3 命令 + in-memory deque(maxlen=10) | 不写盘；query/task 只存 preview/hash |
| 12 | specialist 零 memory 访问（hard filter `memory_*`） | 父 LLM 想让 specialist 知道 memory 必须显式 recall → 塞 task |
| 13 | MCP 默认排除 + **两道门**：`allow_mcp: true` + `allowed_tools` 精确列名；`all` / `*` **不**自动包含 MCP | metadata 优先判定 MCP 来源 |
| 14 | boundary-first unit tests + mock sub-AgentLoop | 7 条 runtime invariant 必须测 |

## 6. Runtime Invariants

以下 13 条**全部由代码 enforce**，不是配置建议。v1 测试**必须**覆盖每一条。

1. **specialist 工具集永远没有 `delegate_*` 工具**（无论 `allowed_tools` 怎么写）
2. **specialist 工具集永远没有 `memory_*` 工具**（无论 `allowed_tools` 怎么写）
3. **`allow_mcp: false`（默认）时 specialist 工具集永远没有 MCP 工具**
4. **`allow_mcp: true` 时 MCP 工具必须显式列在 `allowed_tools`**（`all` / `*` 不算）
5. **`timeout_seconds` 超时 → `ToolResult(ok=False, error_type=timeout)`**
6. **sub-AgentLoop 抛异常 → `ToolResult(ok=False, error_type=crash)`**
7. **triage 返回 `recommended_specialist` 不在 registry → `ToolResult(ok=False, error_type=contract_violation)`**
8. **`content` 字段 ≤ 2000 chars**（specialist 返回），超长截断并提示 "full result in data"
9. **错误路径 `content` ≤ 500 chars**（不含 traceback / secrets）
10. **parent_session.messages 永远不被 specialist runner 改写**
11. **specialist 内部消息**（tool calls / assistant messages）**永远不进父 session**
12. **specialist 内部 tool events 可以显示在 REPL**（`ToolResult.data.display_events` → `specialist_event`）但**不**进 parent context
13. **specialist 不递归调用 specialist**（v1 max delegation depth = 1，hardcoded）

## 7. Configuration Schema

```yaml
specialists:
  doc_reader:
    enabled: true                       # 默认 true
    provider: minimax                   # 可选，覆盖主 agent provider
    model: MiniMax-M2.7                 # 可选
    timeout_seconds: 60                 # 默认 60
    max_iterations: 5                   # 默认 5
    allow_mcp: false                    # 默认 false
    allowed_tools:                      # 白名单（精确列名，不支持通配）
      - read_file
      - rag_search
      - knowledge_status

  triage:
    enabled: true
    provider: deepseek
    model: deepseek-v4-flash
    timeout_seconds: 30
    max_iterations: 2
    allow_mcp: false
    allowed_tools:
      - read_file
      - knowledge_status

  planner:
    enabled: true
    timeout_seconds: 120
    max_iterations: 8
    allow_mcp: false
    allowed_tools:
      - learning_path
      - learning_progress
```

**v1 限制**（写进 doc）：

- v1 不允许"纯 YAML 新增 specialist" —— 必须有 Python 类
- `allowed_tools: ["all"]` 或 `["*"]` **不**自动包含 MCP 工具
- `provider` / `model` 缺省时**不**继承主 agent —— specialist 必须显式配或接受 default

## 8. REPL Command Surface

```
/specialists                              # 列出所有 specialist（enabled + config）
/specialists status                       # 最近 3 次调用（REPL runtime state，in-memory）
/specialists tools <name>                 # 该 specialist 的 effective tool set
```

**`/specialists` 输出形状**（不带 ★ —— v1 没有 "default" 概念）：

```
Configured specialists (3/3 enabled):
  doc_reader   enabled   provider=minimax   model=MiniMax-M2.7         timeout=60s   iter=5
  triage       enabled   provider=deepseek  model=deepseek-v4-flash     timeout=30s   iter=2
  planner      enabled   provider=minimax   model=MiniMax-M2.7         timeout=120s  iter=8
```

**`/specialists status`**：deque(maxlen=10)，重启 REPL 清空。存：`{specialist, ok, error_type, duration_ms, content_preview, model, ts}`。query / task 只存短 preview 或 hash，**不**存原内容。

**delegate 运行时显示**：

```text
▸ delegate_doc_reader(...)
  ◐ doc_reader_specialist running...
    ▸ read_file(...)
      ✓ read 10 chars
    ▸ rag_search(...)
      ✓ 5 matches
  ✓ 4 key points, 850 chars summarized
```

内部 `read_file` / `rag_search` 行来自 specialist sub-loop 的 display events。它们只给 REPL 展示，不写入父 session；父 LLM 仍只看到 delegate tool 的 `content`。

## 9. Testing Strategy

v1 用 **boundary-first unit tests**，mock sub-AgentLoop，不测 LLM 智能质量。

**必测的 7 条 invariant**（每条至少 1 个测试）：

| Invariant | 测试文件 |
|-----------|---------|
| 1: 无 `delegate_*` | `test_agents_tool_filter.py` |
| 2: 无 `memory_*` | `test_agents_tool_filter.py` |
| 3: `allow_mcp=false` 排除 MCP | `test_agents_tool_filter.py` |
| 4: `allow_mcp=true` 需显式列名 | `test_agents_tool_filter.py` |
| 5: timeout → `error_type=timeout` | `test_agents_runner.py` |
| 6: crash → `error_type=crash` | `test_agents_runner.py` |
| 7: triage 校验失败 → `error_type=contract_violation` | `test_agents_triage.py` |

**mock 策略**：
- mock 整个 sub-AgentLoop，return canned `LLMResponse`
- mock specialist 内部 tool calls
- **不**接真 LLM / 真 MCP

**测什么**：
- Registry CRUD（add / disable / get / list）
- Config 解析（Python defaults + YAML merge）
- 3 个 specialist 的 `data_to_content()` 输出
- system prompt 能 render，含 specialist name / role / 输出契约提示
- content cap（集中测一次）
- REPL 命令组（`/specialists` 三命令）
- 真实 `AgentLoop.run_stream(task)` 调用契约
- specialist display events 透传但不污染父 session
- `delegate_doc_reader` 完整保留 `source_paths`，并提示 specialist 用 exact path 调 `read_file`

**不测什么**：
- LLM 生成 prose 质量（用 mock response）
- 真实 MCP server 连接（mock transport）
- 并发 / 真实 LLM streaming / 跨 specialist 调用链
- 端到端 routing（manual REPL smoke test 覆盖）

## 10. Non-Goals & v2 Extensions

**v1 不做**（每条都对应一个 v2 留口）：

| v1 不做 | v2 怎么开 |
|--------|----------|
| 递归 delegation | 加 `max_delegation_depth: 1` 配在 AgentLoop；v1 硬禁 |
| 并行 specialist | runner 改用 `ThreadPoolExecutor` + 父 LLM 调多次 |
| specialist 自动重试 | runner 接 `error_type=transient` → 重试 |
| 跨失败转移 | runner 检测 specialist 失败 → 派 fallback specialist |
| 完整 trace event 流 | 在 UI-only `specialist_event` 之外，增加可重放、可断言的 trace 协议 |
| 持久化 trace | `last_invocations` 写盘到 `.bobodan/agents/trace/` |
| metrics 聚合 | 加 `agents/metrics.py` 跑 P50/P99 |
| 用户自定义 specialist | 开放 `from_path()` loader 接受 `.py` specialist 文件 |
| 多轮交互式 specialist | 改 runner 暴露 `resume(specialist_id, user_message)` |
| per-turn 累积 budget | runner 累计 `elapsed_ms`，超阈值 break |
| token budget | 先有 token counting 基础设施 |
| specialist 调 specialist | Decision 6 永不变 —— 改 v2 design doc 单独评审 |

**v1 范围总览**：

- ✅ 3 个 specialist，每个 1 个 delegate tool
- ✅ 跑在 fresh session，独立 model / tools / timeout
- ✅ 错误兜底，triage 路由契约校验
- ✅ REPL 显示 + 错误 header + 3 个 inspection 命令
- ✅ boundary-first 测试覆盖 7 条 invariant
- ❌ 上述 v1 不做的 11 项
