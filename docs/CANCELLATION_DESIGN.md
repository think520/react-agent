# 取消原语设计（A4 批次三）

> 立项：2026-09-14。对应审计 P0-1 / P0-2 / P0-3，方案依据是同日锁定的第 4 项决策（协作取消为主，不引 asyncio 重写、不引子进程隔离）。
> 本文是批次三的实现依据：先有本文，再动代码。

---

## 1. 现状（实测，不是推测）

| 事实 | 证据 |
|---|---|
| 生产代码里没有任何取消原语 | 全仓 grep `stop_event` / `should_stop` / `cancel_event` 在生产代码 0 命中 |
| 停止生成只发生在前端 | `ChatPage.tsx` 只做 `abortRef.current?.abort()`，服务端无感，token 继续烧 |
| SSE 生成器从不被关闭 | `web/backend/sse.py::iterate_on_stream_lane` 没有 try/finally 关闭底层同步生成器；`create_run` 的 `finally` 只做 `persist_session()` 与 `emitter.clear()` |
| specialist 超时是假的 | `agents/runner.py` 用 `Future.cancel()`，对已经开始执行的任务无效；父级已按超时换路，旧任务仍在发请求、仍在写 learning store |
| CLI 取消是假的 | agent 跑在 daemon 线程，超时与 Ctrl+C 只跳出消费循环，线程继续跑 |

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


