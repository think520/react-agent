# MCP (Model Context Protocol) 用户文档

> 实现版本：v0.1（feature/mcp-client 分支）
> 协议规范：https://modelcontextprotocol.io/

## 1. 什么是 MCP

MCP 是一个让 LLM agent 接入外部工具的开放协议。MCP server 暴露一组可调用的 tools，agent 可以像调用内置函数一样调用它们。

Bobodan 作为 MCP **客户端**（不支持作为 server），把配置的 MCP server 暴露的 tools 注入到自己的 agent loop 中，跟 23 个内置工具无缝集成。

## 2. 快速开始

### 2.1 在 config.yaml 中启用

```yaml
mcp:
  enabled: true                    # 默认 false，必须显式开启
  connection_timeout: 30          # server 连接超时（秒）
  tool_call_timeout: 60           # 单个 tool call 超时（秒）
  servers:
    # stdio 类型（最常见）
    context7:
      command: uvx
      args: ["context7-mcp"]
      env: {FOO: "bar"}            # 可选
      cwd: "/path/to/work"         # 可选

    # streamable_http 类型（现代 HTTP）
    amap-maps:
      transport: streamable_http
      url: "https://mcp.example.com/mcp"
      headers:
        Authorization: "Bearer ${AMAP_TOKEN}"   # 支持 ${ENV_VAR}

    # SSE 类型（传统 HTTP）
    legacy:
      transport: sse
      url: "https://mcp.example.com/sse"
```

### 2.2 启动 REPL

```bash
.venv\Scripts\python.exe agent.py
```

启动面板会显示：

```
mcp           1/1 connected, 12 tools
```

### 2.3 自然语言调用

直接在 REPL 里问：

```
> 帮我查成都锦城学院到昆明的自驾路线
> 北京天安门在哪儿？
> 用 GitHub MCP 工具列出我所有的 PR
```

LLM 会看到 `amap-maps__maps_geo` 等工具名（格式 `server__tool`），自主决定调用哪个。

## 3. 三种传输协议

| 协议 | 适用场景 | 配置字段 |
|------|----------|----------|
| **stdio** | 本地 MCP server（最常见，80%+ 用例） | `command`, `args`, `env`, `cwd` |
| **streamable_http** | 现代 HTTP MCP server | `url`, `headers`, `transport: streamable_http` |
| **sse** | 传统 HTTP+SSE MCP server | `url`, `headers`, `transport: sse` |

省略 `transport` 时自动推断：
- 有 `command` → stdio
- 有 `url` → sse（默认）

## 4. 配置字段详解

### 4.1 server 级别

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `command` | str | stdio 必填 | 可执行文件路径或命令名 |
| `args` | list[str] | 否 | 命令行参数 |
| `env` | dict[str, str] | 否 | 传给子进程的环境变量 |
| `cwd` | str | 否 | 子进程工作目录 |
| `url` | str | http 必填 | http/https URL |
| `transport` | str | 否 | `stdio` / `sse` / `streamable_http`（可省略） |
| `headers` | dict | 否 | HTTP headers，支持 `${ENV_VAR}` 占位符 |
| `connection_timeout` | int | 否 | 覆盖全局 connection_timeout（秒） |
| `enabled` | bool | 否 | 单 server 开关，默认 true |

### 4.2 字段别名

`transport` 和 `type` 是同一个字段的两种写法。两者都出现时，`transport` 优先。这是为了兼容标准 MCP config 格式（Claude Desktop / Cursor 用 `type`）。

```yaml
# 两种写法等价
github: { type: streamable_http, url: "..." }
github: { transport: streamable_http, url: "..." }
```

### 4.3 环境变量占位符

任何 string 字段都可以用 `${ENV_VAR}` 占位符，启动时替换为环境变量的值。缺失时报错，fail-fast。

```yaml
headers:
  Authorization: "Bearer ${GITHUB_TOKEN}"
```

## 5. REPL 命令

```
/mcp                       列出所有 server 状态
/mcp status                详细状态（错误/重试时间/transport 信息）
/mcp restart [name]        重连 server（无 name = 全部）
/mcp tools <name>          列出该 server 暴露的 tools
/mcp reload                重新读 config.yaml（diff + 重连）
```

## 6. 安全模型

Bobodan 用的是 **trust-first** 模型：
- 用户在 config.yaml 里配置的 server = 完全信任
- 所有 MCP tools 自动可用，跟内置工具一样调度
- 失败隔离：单个 server 出问题不影响其他 server 和内置功能
- 不做 per-tool approval gate

如果需要更严格的权限控制，参见 [harness 改进计划](AGENT_HARNESS_IMPROVEMENT_PLAN.md) — 那里有 approval gate 设计。

## 7. 故障排查

### "MCP not initialized"

`mcp.enabled` 没开或没有 server。检查 config.yaml：

```yaml
mcp:
  enabled: true      # ← 这个
  servers: { ... }
```

### "stdio transport requires 'command'"

stdio server 缺 `command` 字段。检查：

```yaml
servers:
  my-server:
    command: /path/to/binary   # ← 这个
```

### "unavailable (Connection refused)"

MCP server 没起来或网络不可达。检查：
1. 手动启动 server 进程看是否能跑
2. 验证 URL/端口正确
3. 跑 `/mcp restart` 重连

### Token 泄漏风险

把 token 放在 `${ENV_VAR}` 占位符里（推荐）而不是明文写在 config.yaml：

```yaml
headers:
  Authorization: "Bearer ${MY_TOKEN}"   # 推荐
```

config.yaml **会**进入 git（不像 .env），所以不要把 token 写明文。

### 改 config 后不生效

改完 config.yaml 后要 `/mcp reload` 才会重新读（但 tool schema 要等下次 REPL 启动才更新，因为 AgentLoop 在启动时快照 tools）。

## 8. 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│  Bobodan REPL / AgentLoop                                   │
│  tools_schema = static_tools + mcp_tools    ← 每 turn 拉取  │
│  mcp_prompt = "## MCP Servers\n- ..."        ← 注入 system prompt
│  execute_tool("amap-maps__maps_geo", args)                  │
│         ↓                                                    │
│  ┌─────────────────────────────────────────────┐            │
│  │  MCPManager (singleton)                      │            │
│  │  - per-server state (config/transport/tools)│            │
│  │  - lazy connect (first tool call)            │            │
│  │  - reload() diff config                      │            │
│  └─────────────────────────────────────────────┘            │
│         ↓                                                    │
│  ┌─────────────────────────────────────────────┐            │
│  │  AsyncEventLoop (daemon thread)              │            │
│  │  - run_coroutine_threadsafe                  │            │
│  └─────────────────────────────────────────────┘            │
│         ↓                                                    │
│  3 transports (stdio / SSE / streamable_http)               │
│  all backed by official `mcp` Python SDK 1.19+             │
└─────────────────────────────────────────────────────────────┘
```

## 9. 已知限制

- **只支持 tools 原语**：resources 和 prompts 是 Phase 2
- **Trust-first 安全模型**：per-tool approval gate 是 Phase 2
- **tools_schema 启动时快照**：改 config 加新 tool 后要 `/exit` 重新启动 REPL 才生效
- **不支持作为 MCP server**：只做 client，不暴露 Bobodan 给外部 client
- **stdio 子进程 stderr**：被捕获到 Python logger（DEBUG 级别），不直接展示给用户

## 10. 相关文件

| 文件 | 职责 |
|------|------|
| `mcp_client/manager.py` | MCPManager 单例，per-server 状态 |
| `mcp_client/event_loop.py` | 跨线程 async event loop bridge |
| `mcp_client/config.py` | config 加载 + `${ENV_VAR}` 替换 |
| `mcp_client/naming.py` | `server__tool` 命名 sanitization |
| `mcp_client/catalog.py` | 从 MCPManager 拉取 tool specs |
| `mcp_client/tool_wrapper.py` | 把 MCP tool 包装成 Bobodan tool |
| `mcp_client/prompt.py` | system prompt 软提示段 |
| `mcp_client/transport_*.py` | 三种 transport 实现 |
| `tools/mcp.py` | REPL 集成入口（register_mcp_tools） |
| `tests/test_mcp_*.py` | 54 个测试 |
| `docs/mcp_design.md` | 详细设计文档（18 章节） |
