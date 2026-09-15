# 取消原语设计（A4 批次三）

> 立项：2026-09-14。对应审计 P0-1 / P0-2 / P0-3，方案依据是同日锁定的第 4 项决策（协作取消为主，不引 asyncio 重写、不引子进程隔离）。
> 本文是批次三的实现依据：先有本文，再动代码。

---

## 1. 现状（实测，不是推测）

| 事实 | 证据 | 收口状态 |
|---|---|---|
| 生产代码里没有任何取消原语 | 全仓 grep `stop_event` / `should_stop` / `cancel_event` 在生产代码 0 命中 | ✅ `core/cancellation.py` |
| 停止生成只发生在前端 | `ChatPage.tsx` 只做 `abortRef.current?.abort()`，服务端无感，token 继续烧 | ✅ 见 §6.3：`POST /streams/{id}/cancel` |
| SSE 生成器从不被关闭 | `web/backend/sse.py::iterate_on_stream_lane` 没有 try/finally 关闭底层同步生成器 | ✅ 已显式关闭；且 run 生产已与响应解耦（§6.2） |
| specialist 超时是假的 | `agents/runner.py` 用 `Future.cancel()`，对已经开始执行的任务无效 | ✅ 子 token + 超时主动通知 |
| CLI 取消是假的 | agent 跑在 daemon 线程，超时与 Ctrl+C 只跳出消费循环，线程继续跑 | ✅ 超时与 Ctrl+C 都接到同一个 token |

危害的共同形态：**用户以为停了，服务端还在烧钱、还在写状态**。

## 2. 方案（已锁定）

协作取消。理由是三条边界：

1. 真正需要被打断的只有阻塞点，而阻塞点只有两类：**流式 HTTP**（可以在读循环里跳出并关闭响应，这会真的断开 socket）与**非流式 HTTP**（本来就打断不了，只能靠 httpx 的 timeout 兜底）。
2. 工具绝大多数是本地 IO，在工具边界检查一次就够。
3. asyncio 重写要让 `AgentLoop`、provider、工具派发、specialist、CLI 五处一起变成 async，还要重新解决同步工具与文件 IO 的阻塞问题；子进程隔离要把 session 与工具状态序列化跨进程。两者都是在为一个「边界检查就够用」的问题付架构成本。

**明确的诚实边界**：Python 不能杀死线程。协作取消的语义是「不再等它 + 通知它停」，所以：

- 流式请求：真停（关闭响应）
- 非流式请求：等在途请求自己的 timeout，但取消后**不再重试、不再发下一个**
- 无视取消标志的工具：会跑完；我们不去假装能杀掉它（审计对 OpenMAIC 的批评正是「不再等不等于真杀掉」）

## 3. 原语：`core/cancellation.py::CancelToken`

```python
class RunCancelled(Exception):
    """Raised at a cooperative checkpoint; not a provider failure."""

class CancelToken:
    def cancel(self, reason: str = "") -> None      # 幂等、线程安全
    def is_cancelled(self) -> bool
    def reason(self) -> str
    def raise_if_cancelled(self) -> None            # 抛 RunCancelled(reason)
    def child(self) -> CancelToken                  # 父取消自动传播到子
```

为什么不是裸 `threading.Event`：需要 reason（落盘与 UI 要说明为什么停）、需要父子传播（specialist）、需要与 `ProviderError` 区分的语义（取消不是失败，不该触发重试、不该算进错误率）。

## 4. 穿透点与各自的行为

| 层 | 检查点 | 行为 |
|---|---|---|
| `AgentLoop.run_stream` | 每轮迭代开始、每次工具派发前 | 取消则结束本轮，`termination_reason=cancelled`，已产出内容照常落盘 |
| 工具派发 | 派发前检查；已开始的工具在其 IO 边界自检 | 未开始的直接跳过；已开始的结果保留，不丢 |
| `providers/openai_compat.complete_stream` | 每个 chunk 之前 | break 出读循环，`with` 退出，响应与连接关闭，请求真的停 |
| `providers/openai_compat.complete` | 不可中断 | 取消后不重试；取消导致的异常不归类为 `ProviderError` |
| `agents/runner.run_specialist` | 子 token | 父取消则子在下一次 LLM 调用或工具边界停；超时结果照旧返回给父级 |
| `cli/repl.py` | SIGINT 设 token | 线程内的 `run_stream` 在下一边界退出（不再只跳出消费循环） |

## 5. 每工具超时：转成结构化错误

`asyncio.wait_for` 在同步栈里的等价物是 `future.result(timeout=...)`。契约：

- 超时 = `ToolResult(ok=False, ..., data={"code": "tool_timeout"})`，**不抛异常、不炸会话**（OpenMAIC 的做法）
- 单个工具超时**不**终止整轮：只把结构化错误交回模型，由模型决定下一步
- 取消不触发任何 provider 重试

## 6. Web 断线：宽限期（第 3 项决策）

```text
run 注册表:  stream_id -> RunHandle(token, grace_timer)

SSE 生成器 finally（断线也走）
        |
        +-- 启动宽限计时（默认 30s）
        |
        +-- 宽限内客户端带 after_seq 重连 replay 端点：取消计时，run 继续跑
        |   （事件已在批次二落库，所以断线期间的事件能补齐）
        |
        +-- 超期：token.cancel("client_disconnected")，落盘已产出内容并标记 cancelled
```

宽限期是「刷新页面」与「关掉标签页」的分界：刷新会在几秒内重连，误关来得及撤回，真的关掉就止血。

### 6.1 宽限窗口可配

```yaml
web:
  stream_grace_seconds: 30
```

`resolve_grace_seconds(config)` 读它，非法值回落 30s；`RunRegistry.start(stream_id, grace_seconds)` 支持每个 run 覆盖（测试要用短窗口）。

### 6.2 实现时被迫补的一步：run 必须与响应解耦

光有计时器不成立。实测下来：SSE 生成器是**被客户端拉动**的，客户端一走 run 就停在上一个 yield——那时取消的是一个「已经停下」的东西。所以真正让宽限期有意义的是 `web/backend/run_pump.py::RunPump`：

- 泵在自己的线程里把 producer 拉到结束（帧已由 `StreamEmitter` 写进批次二的事件日志，泵不另外缓冲）
- HTTP 响应退化成**读者**：`tail()` 从游标读日志直到泵结束
- 断线只影响读者；run 继续走，`finally` 里的会话落盘变成正常完成路径

由此带来一条额外约束：**保留策略不能删活流**。`EventLog.prune` 原本按「最旧的流先删」，会删掉正在跑的 run 的帧，且 `append` 的 seq 来自 `MAX(seq)`，删完 seq 从 1 重来、读者永远等不到自己的游标。现在 `prune(exempt=live_stream_ids())`，且流数量上限只作用于可删集合。

### 6.3 前端必须显式说「停」

解耦之后，`abort()` 只断开读者，**不再**停服务端。所以：

- 后端 `POST /api/chat/streams/{stream_id}/cancel` → `RunRegistry.cancel_now(reason="user_stopped")`；未知或已结束的流返回 `{ok: true, cancelled: false}`（晚点一下不会变成报错）
- 前端 `onStreamId` 在第一帧拿到 stream id，停止按钮同时做两件事：`abort()` 本地 fetch + `api.cancelRun(id)`
- 读者意外断开时，客户端从 `after_seq` 重连 replay 端点续看（三次退避 300/900/2000ms）；一次重连**零帧**即认为日志已读完，不再重试

## 7. 明确不做

- 不引入 asyncio 重写；不做子进程隔离（理由见第 2 节）
- 不做跨进程取消：CLI 的取消不会影响 Web 进程里正在跑的 run
- 不假装能杀死无视取消的工具；这类工具在文档里逐个标注（第 5 节）

## 8. 验收口径

| 用例 | 方式 |
|---|---|
| 父取消传播到子 | 单测 |
| 流式请求在 N 个 chunk 后取消：真的停止产出且生成器被关闭 | **真实集成**：假 provider 持续产 chunk，断言停止后不再有新 chunk，且其 finally 被走到 |
| 取消不触发 provider 重试 | 单测（假 provider 计数调用次数） |
| 工具超时转结构化错误、会话不炸 | 单测 + 一个慢工具注入 |
| 断线宽限超期取消；宽限内重连继续跑 | **真实集成**：TestClient 断开 + 重连 replay |

## 9. 分阶段

1. **原语与穿透**：`CancelToken` + `AgentLoop` 迭代与工具边界 + provider 流式读循环 + 测试（本批核心）
2. **Web 宽限期**：run 注册表 + 断线取消 + 重连续跑 + 测试
3. **CLI 与 specialist**：SIGINT 接 token；specialist 子 token + 超时后不再写状态 + 测试
4. **每工具超时表**：per-tool timeout 配置 + 结构化超时结果

---

## 10. 收口证据（as-built，2026-09-14）

| 验收项 | 落地的测试 |
|---|---|
| 取消幂等、保留首个 reason、父子传播 | `tests/test_cancellation.py`（7 条）、`tests/test_agent_cancellation.py`（2 条） |
| 流式请求真的停、且取消后不重试 | `tests/test_provider_cancellation.py`（3 条，`httpx.MockTransport` 保留真实读循环） |
| 工具超时转结构化错误、会话不炸 | `tests/test_tool_timeouts.py`（5 条，含端到端） |
| specialist 子 token / 超时通知 | `tests/test_agents_runner.py` |
| 每工具超时表 | `tools/timeouts.py` + `tests/test_tool_timeouts.py` |
| CLI 超时与 Ctrl+C | `tests/test_repl.py`（真 `SIGINT` 一条 + 超时） |
| 断线宽限、重连撤销、并发独立 | `tests/test_run_registry.py`（7 条） |
| 生产与响应解耦 | `tests/test_run_pump.py`（8 条，关键一条是「读者只取一帧就走，泵仍跑完」） |
| 保留策略不删活流 | `tests/test_event_log.py::test_prune_never_deletes_a_stream_that_is_still_live` |
| 路由层接线（token 来源、句柄回收、宽限期来自配置） | `tests/test_web_backend.py`（3 条） |
| 停止端点 | `tests/test_web_backend.py::test_cancel_stream_reaches_a_live_run` |
| 前端重连续看与去重 | `web/frontend/src/lib/api.test.ts`（4 条新增） |
| 停止按钮行为 | `web/frontend/e2e/interaction.spec.ts::stopping a run keeps what was already produced` |

### 仍然成立的边界（不假装完成）

- Python 杀不掉线程：以上全是「不再等 + 在检查点通知」，不是抢占式终止。
- 非流式请求打断不了在途 HTTP，只能取消后不再重试。
- 断开标签页后重连**必须**是客户端行为：replay 端点与 `note_reconnect` 都已就位，但服务端无法替浏览器重连。
- 前端重连是「同页面的读者断了再续」，不是「关掉再打开页面」——刷新后新页面靠的是 `run_completed` 落盘保留的那一轮会话，不靠 replay。


