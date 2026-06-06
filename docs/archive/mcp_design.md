# Bobodan MCP 客户端设计文档

> 创建时间：2026-05-21
> 状态：待实施
> 参考：[DenisSergeevitch/agents-best-practices](https://github.com/DenisSergeevitch/agents-best-practices)、[Model Context Protocol](https://modelcontextprotocol.io/)

## 1. 目标

把 Model Context Protocol (MCP) 客户端能力集成到 Bobodan，让 agent 能消费外部 MCP server 暴露的 tools（如 GitHub、context7、filesystem 等），扩展现有 23 个内置工具的边界。

**核心原则**：
- 不破坏现有 tools 系统和 agent loop
- 用户主动配置 = 主动信任
- 失败隔离：单个 server 出问题不影响其他 server 和内置功能
- 默认安全（off by default），用户显式开启

## 2. 设计决策

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | 范围 | Client only | 99% 价值在"接入更多工具"；server 模式跟个人学习场景不匹配 |
| 2 | Python 库 | 官方 `mcp` SDK | OpenClaw 也用官方 SDK，设计一致，长期维护有保障 |
| 3 | 异步桥接 | 后台常驻 event loop + `run_coroutine_threadsafe` | 复用连接，延迟低，OpenClaw 模式 |
| 4 | Transport | stdio + SSE + streamable_http | 三种全覆盖 |
| 5 | 生命周期 | 懒加载（首次 tool call 时 connect） | 启动快，按需资源 |
| 6 | 工具命名 | `server__tool` + 64 字符截断 | OpenClaw 风格，LLM 友好 |
| 7 | 安全模型 | Trust-first | 用户配置即信任；后续可加 approval gate |
| 8 | Config 敏感值 | `${ENV_VAR}` 占位符 | YAML 标准实践，零特殊语法 |
| 9 | Auto-discover | 不做 | MVP 保持显式配置 |
| 10 | MCP 原语 | Tools only | resources/prompts Phase 2 |
| 11 | 工具注册时机 | 每轮 turn 重新拉取 `tools_schema` | 懒加载工具立即可见，改动小 |
| 12 | 错误处理 | 30s 连接、60s call、无重试 | 防止 hang，agent 决定下一步 |
| 13 | Skills 关系 | 软 system prompt 提示 | 几十 token，不影响用户写 skill |
| 14 | 记忆系统 | 不集成 | 跟内置工具对称，transient |
| 15 | Config 热更新 | `/mcp reload` 命令 | 显式可控，不破坏 session |
| 16 | 实施分阶段 | MVP 5-7 天 + Phase 2 | 见实施计划 |

## 3. 架构

```
┌─────────────────────────────────────────────────────────────┐
│  Bobodan REPL / AgentLoop                                   │
│  ┌─────────────────────────────────────────────┐            │
│  │  tools_schema = static_tools + mcp_tools    │ ← 每 turn 拉取
│  └─────────────────────────────────────────────┘            │
│         ↓                                                    │
│  execute_tool("github__create_issue", args)                 │
│         ↓                                                    │
│  ┌─────────────────────────────────────────────┐            │
│  │  MCPManager (singleton)                      │            │
│  │  - get_tool(server, tool) → wrapper func     │            │
│  │  - reload_config()                           │            │
│  │  - list_servers()                            │            │
│  └─────────────────────────────────────────────┘            │
│         ↓                                                    │
│  ┌─────────────────────────────────────────────┐            │
│  │  AsyncEventLoop (daemon thread)              │            │
│  │  - run_coroutine_threadsafe(coro)            │            │
│  │  - 调 MCPClient.call_tool()                  │            │
│  └─────────────────────────────────────────────┘            │
│         ↓                                                    │
│  MCPClient (官方 SDK)                                        │
│    ├─ StdioTransport ── spawn subprocess                     │
│    ├─ SSETransport ──── long-lived HTTP                      │
│    └─ StreamableHTTPTransport ── HTTP                        │
└─────────────────────────────────────────────────────────────┘
```

## 4. Config Schema

```yaml
mcp:
  enabled: false                    # 全局开关（默认关闭）
  connection_timeout: 30            # server 连接超时（秒）
  tool_call_timeout: 60             # 单个 tool call 超时（秒）
  servers:
    context7:                       # server name (key)
      enabled: true                 # 单 server 开关（可选，默认 true）
      command: uvx                  # stdio: command
      args: ["context7-mcp"]        # stdio: args
      env: {FOO: "bar"}             # stdio: env vars (可选)
      cwd: "/path/to/dir"           # stdio: working dir (可选)
    
    github:                         # streamable_http
      url: "https://mcp.github.com"
      transport: streamable_http    # 显式指定
      headers:
        Authorization: "Bearer ${GITHUB_TOKEN}"   # ${ENV_VAR} 占位符
      connection_timeout: 10        # 覆盖全局（可选）
    
    legacy-server:                  # SSE (默认)
      url: "https://mcp.example.com/sse"
      # transport 省略默认 sse
      headers:
        X-API-Key: "${MY_API_KEY}"
```

**字段定义**：

| 字段 | 适用 | 必填 | 说明 |
|------|------|------|------|
| `command` | stdio | 必填（stdio） | 可执行文件 |
| `args` | stdio | 否 | 字符串列表 |
| `env` | stdio | 否 | dict，字符串值 |
| `cwd` | stdio | 否 | 工作目录 |
| `url` | http/sse | 必填（http） | http/https URL |
| `transport` | http | 否 | `sse`（默认）/ `streamable_http` |
| `headers` | http | 否 | dict，敏感值用 `${ENV_VAR}` |
| `connection_timeout` | 全部 | 否 | 覆盖全局默认值 |

**`${ENV_VAR}` 占位符处理**：
- 启动时扫描所有 string 字段的 `${...}` 模式
- 替换为环境变量值
- 缺失时启动报错（fail fast，提示哪个字段哪个变量）

## 5. 工具命名

**规则**（沿用 OpenClaw）：
- 格式：`serverName__toolName`
- Server name sanitize：替换 `[^A-Za-z0-9_-]` 为 `-`，截断 30 字符
- Tool name sanitize：同上，无截断
- 总长截断 64 字符（Anthropic/OpenAI 工具名限制）
- 冲突检测：跟现有内置工具名（`read_file` 等）冲突时加 `-2`/`-3` 后缀

**示例**：
| MCP server | MCP tool | Bobodan tool name |
|------------|----------|-------------------|
| `github` | `create_issue` | `github__create_issue` |
| `context7` | `get-docs` | `context7__get-docs` |
| `my-cool-server` | `do-thing` | `my-cool-server__do-thing` |
| `very-long-server-name-that-exceeds-thirty-chars` | `x` | `very-long-server-name-that-exc__x`（截断） |

## 6. 工具注册流程

```
1. MCPManager 启动时读 config，遍历 servers
2. 每个 server 注册一个 lazy connector（不立即连接）
3. 注册 placeholder 到 tool registry：name=`server__tool`, func=`lambda *a: mcp_manager.call(server, tool, a)`
4. Agent 调 `execute_tool("github__create_issue", args)` → placeholder func
5. placeholder func 调 MCPManager.call()：
   a. 检查 server 是否已连接，未连接则 connect（首次 lazy）
   b. 调 run_coroutine_threadsafe(async_call())
   c. 等待结果（带 60s 超时）
   d. 返回 ToolResult
```

**关键点**：
- Placeholder func 在注册时就有定义，避免 schema 跟实现不同步
- Lazy connect：首次 call 时连接，连接成功后 cache
- 工具 schema 在 server connect 后才完整可用（`description`、`inputSchema`）

**`tools_schema` 刷新机制**：

```python
# core/agent_loop.py
def run_stream(self, user_input):
    # 每轮 turn 开始前刷新 schema
    self.tools_schema = get_tools_schema()  # 现在包含 lazy MCP 工具
    ...
```

修改后：每个 turn 调 `get_tools_schema()` 获取最新 schema，包含所有已注册的 placeholder。

## 7. Async Bridge

```python
# mcp/event_loop.py
import asyncio
import threading
from concurrent.futures import Future

class AsyncEventLoop:
    """Singleton 后台 event loop，跨线程运行协程。"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
    
    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
    
    def run_sync(self, coro, timeout: float) -> Any:
        """同步等一个 coroutine 完成。"""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)
    
    @classmethod
    def get(cls) -> "AsyncEventLoop":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
```

**使用**：
```python
# mcp/manager.py
from .event_loop import AsyncEventLoop

class MCPManager:
    def call(self, server: str, tool: str, args: dict) -> ToolResult:
        try:
            result = AsyncEventLoop.get().run_sync(
                self._async_call(server, tool, args),
                timeout=self.tool_call_timeout,
            )
            return ToolResult(ok=True, content=result)
        except TimeoutError:
            return ToolResult(ok=False, content=f"MCP tool call timed out after {self.tool_call_timeout}s")
        except Exception as e:
            return ToolResult(ok=False, content=f"MCP error: {e}")
```

## 8. Transport 实现

**基类**：

```python
# mcp/transport_base.py
from abc import ABC, abstractmethod

class Transport(ABC):
    @abstractmethod
    async def connect(self) -> None: ...
    
    @abstractmethod
    async def disconnect(self) -> None: ...
    
    @abstractmethod
    async def list_tools(self) -> list[dict]: ...
    
    @abstractmethod
    async def call_tool(self, name: str, args: dict) -> dict: ...
```

**stdio**（`mcp/transport_stdio.py`）：
- 启动子进程：`subprocess.Popen([command] + args, stdin=PIPE, stdout=PIPE, stderr=PIPE, env=env, cwd=cwd)`
- 用官方 SDK 的 `StdioClientTransport`
- 捕获 stderr 到 log（OpenClaw 模式）

**streamable_http**（`mcp/transport_http.py`）：
- 官方 SDK `StreamableHTTPClientTransport`
- 注入 `headers`（解析 `${ENV_VAR}` 后的）

**SSE**（`mcp/transport_sse.py`）：
- 官方 SDK `SSEClientTransport`
- 注入 `headers`

## 9. 错误处理

| 场景 | 行为 | ToolResult |
|------|------|------------|
| Server 启动失败 | logWarn，状态 `disconnected` | (tool 不可用) |
| 连接超时 (>30s) | logWarn，状态 `disconnected` | (tool 不可用) |
| Tool call 超时 (>60s) | 终止协程 | `ok=False, content="MCP tool call timed out after 60s"` |
| Tool call 错误 (`isError`) | 透传 | `ok=False, content=<error message>` |
| Transport 中断 | 标记 `disconnected`，下次 call 重连 | (重连失败时返回错误) |
| Tool 不存在 | 透传 SDK 错误 | `ok=False, content="Tool not found: server__tool"` |
| Schema 无效 | logWarn，跳过该 tool | (tool 不注册) |

**关键点**：
- 单 server 失败**不影响**其他 server 和内置功能
- 失败有详细日志，agent 可基于错误信息重试或换方案
- 不做自动重试（避免重复失败浪费 token）

## 10. REPL 集成

**启动面板**：
```
mcp: 3 configured (1 connected, 2 disconnected), 142 tools available
```

**`/mcp` 命令组**：

| 命令 | 行为 |
|------|------|
| `/mcp` | 列出所有 server 和状态（默认视图） |
| `/mcp list` | 同上 |
| `/mcp status` | 详细状态（连接时间、tools 数量、错误） |
| `/mcp restart [name]` | 重连 server（无 name = 全部） |
| `/mcp tools <name>` | 列出该 server 的 tools |
| `/mcp reload` | 重新读 config.yaml，diff 后增删/重连 |

**`/tools` 输出**：
```
▸ github__create_issue       [mcp:github]       Create a GitHub issue
▸ context7__get-docs         [mcp:context7]     Get library documentation
▸ read_file                  [builtin]          Read a file from disk
```

**Tool call 显示**（agent 运行中）：
```
▸ github__create_issue({...})
✓ Created issue #123: Fix login bug
```

**System prompt 软提示**（由 `mcp/prompt.py` 生成）：
```
Active MCP servers: github (12 tools), context7 (3 tools)
MCP tools are available as `server__tool`. Use them when relevant.
```

## 11. 测试策略

**单元测试**（mock MCP SDK）：
- `tests/test_mcp_config.py` — config 加载、`${ENV_VAR}` 替换、校验
- `tests/test_mcp_naming.py` — sanitization、截断、冲突
- `tests/test_mcp_manager.py` — lifecycle、reload、error handling
- `tests/test_event_loop.py` — async bridge 正确性

**集成测试**（真实 stdio MCP server）：
- `tests/test_mcp_stdio_integration.py` — 启动一个最小的 stdio MCP 测试 server
- `tests/test_mcp_tool_call.py` — 端到端：register → connect → call → result
- `tests/test_mcp_reload.py` — config 变更后 reload 行为

**测试 fixture**（`tests/fixtures/mcp_echo_server.py`）：
- 最小的 stdio MCP server：暴露 1-2 个简单 tool（如 `echo`、`add`）
- 跑在 subprocess 里供集成测试连接
- 遵循官方 Python SDK 的 server 示例

**手动验证**：
- 配一个真实外部 server（如 `mcp-server-git` 或 context7）
- 跑 REPL，确认 tool 出现、能调用

## 12. 实施计划

### Step 1: 基础架构（1 天）
- `mcp/__init__.py`
- `mcp/event_loop.py` — AsyncEventLoop singleton
- `mcp/config.py` — config 加载 + `${ENV_VAR}` 替换
- `tests/test_mcp_config.py`、`tests/test_event_loop.py`

### Step 2: Manager 和 transport base（1 天）
- `mcp/transport_base.py` — Transport ABC
- `mcp/manager.py` — MCPManager 单例（lazy connect、reload、状态管理）
- `mcp/naming.py` — 命名 sanitization
- `tests/test_mcp_manager.py`、`tests/test_mcp_naming.py`

### Step 3: 三个 transport（1-2 天）
- `mcp/transport_stdio.py` — 子进程 + StdioClientTransport
- `mcp/transport_sse.py` — SSEClientTransport
- `mcp/transport_http.py` — StreamableHTTPClientTransport
- `tests/test_mcp_stdio_integration.py`（用 echo server 测）

### Step 4: 工具注册和包装（1 天）
- `mcp/catalog.py` — 拉取 tools list、生成 schema
- `mcp/tool_wrapper.py` — 包装成 Bobodan `register_tool()` 兼容的函数
- `mcp/prompt.py` — system prompt 软提示
- `tools/__init__.py` — 导出 `mcp_init()` 在 REPL 启动时调用

### Step 5: REPL 集成（1 天）
- `cli/repl.py` — 启动时初始化 MCP、加 `/mcp` 命令
- `core/agent_loop.py` — 每轮 turn 刷新 `tools_schema`
- 启动面板和 tool call 显示

### Step 6: 端到端测试和文档（1 天）
- `tests/test_mcp_e2e.py` — 完整流程
- 写 `docs/MCP.md`（用户文档）
- 更新 `CLAUDE.md` 和 `README.md`

**总工作量**：5-7 天

## 13. 关键文件

| 操作 | 文件 |
|------|------|
| 新建 | `mcp/__init__.py`、`mcp/event_loop.py`、`mcp/config.py` |
| 新建 | `mcp/manager.py`、`mcp/naming.py`、`mcp/prompt.py` |
| 新建 | `mcp/transport_base.py`、`mcp/transport_stdio.py`、`mcp/transport_sse.py`、`mcp/transport_http.py` |
| 新建 | `mcp/catalog.py`、`mcp/tool_wrapper.py` |
| 新建 | `tests/test_mcp_*.py`、`tests/fixtures/mcp_echo_server.py` |
| 新建 | `docs/MCP.md` |
| 修改 | `config.yaml`（加 mcp section 示例） |
| 修改 | `tools/__init__.py` |
| 修改 | `core/agent_loop.py`（刷新 schema） |
| 修改 | `cli/repl.py`（/mcp 命令、启动面板、system prompt） |
| 修改 | `CLAUDE.md`、`README.md`（文档） |

## 14. 复用的现有模块

| 模块 | 用途 |
|------|------|
| `tools/base.py` | `register_tool()`, `ToolResult`, `execute_tool()` |
| `tools/__init__.py` | 工具自动注册入口 |
| `core/agent_loop.py` | `run_stream()`, `tools_schema` |
| `cli/repl.py` | REPL 命令处理、流式显示 |
| `providers/factory.py` | `ProviderFactory.load_config()`（YAML 加载） |
| `core/memory.py` | `MemoryManager`（system prompt 注入模式参考） |

## 15. 验收标准

MVP 完成的标志：

- [ ] `pip install mcp` 装好后能跑
- [ ] 配置文件支持 3 种 transport
- [ ] `${ENV_VAR}` 占位符生效
- [ ] 至少一个 stdio server 端到端跑通（用测试 fixture）
- [ ] 至少一个 streamable_http server 端到端跑通
- [ ] 至少一个 SSE server 端到端跑通
- [ ] `/mcp list`、`/mcp status`、`/mcp restart`、`/mcp tools` 命令工作
- [ ] `/mcp reload` 能 diff 配置并增删 server
- [ ] 工具命名 sanitization 正确（截断、特殊字符）
- [ ] Lazy connect 工作（首次 tool call 才连接）
- [ ] 30s 连接超时、60s call 超时生效
- [ ] 单 server 失败不影响其他 server
- [ ] System prompt 包含 MCP 状态段
- [ ] `/tools` 显示 MCP 工具（带 `[mcp:server]` 标签）
- [ ] 全部现有 346 测试无回归
- [ ] 新增 20+ MCP 测试通过

## 16. 风险和缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 官方 `mcp` Python SDK 跟 TS SDK API 不一致 | 实现复杂度增加 | 早期 spike 验证 SDK API 形状 |
| 跨线程 event loop 跟 Bobodan 现有 stream 机制冲突 | 死锁、性能问题 | spike 验证 stream + MCP 并发调用 |
| Tool call hang（即使有 60s 超时） | 用户体验差 | 配置可调，文档建议 < 30s |
| MCP server 暴露危险工具（filesystem delete） | 安全隐患 | 信任模型 + Phase 2 approval gate |
| `${ENV_VAR}` 替换遗漏敏感字段 | token 泄漏到日志 | 详细测试 + 日志脱敏 |
| Schema 不规范的 MCP server | tool 注册失败 | 跳过无效 tool，logWarn，继续 |

## 17. Phase 2 路线图

（不在本次实施范围）

- MCP resources 支持（`mcp_resource` 包装 tool）
- MCP prompts 支持（整合 skills 系统）
- 自动重试 1 次（瞬时网络错误）
- Circuit breaker（连续 N 次失败后停用 M 分钟）
- `/mcp add`/`/mcp remove` CLI 命令
- 工具使用统计（哪些 MCP 工具最常用）
- Per-server risk class + approval gate
- 调用审计日志（每天哪个 MCP tool 用了多少次）
- 文件 watcher 自动 reload
- MCP server 健康检查（heartbeat）

## 18. 开放问题

实施过程中需要验证：

1. **官方 `mcp` Python SDK 的 API 形状**（特别是 async API 是否跟 OpenClaw TS 版的语义一致）
2. **跟现有 stream 机制的兼容性**（AgentLoop 已有 run_coroutine_threadsafe 类似机制吗？）
3. **`asyncio.run_coroutine_threadsafe` 在 Windows 上的稳定性**（Windows ProactorEventLoop 跟 Unix 不同）
4. **多个 MCP tool 并发调用的行为**（是否会被序列化？性能？）

这些问题在 Step 1 spike 阶段解决。
