"""Per-tool timeouts that degrade into a structured result (audit P0-2/P0-3).

A timed-out tool used to be impossible to express: the loop called
`execute_tool` inline, so a hanging tool hung the whole turn. Here a tool that
declares a timeout runs on a one-shot worker and a timeout becomes an ordinary
`ToolResult(ok=False, code="tool_timeout")` the model can react to - the session
does not break (OpenMAIC does the same, and it is the right shape).

Honest limits: Python cannot kill the worker thread. A timeout means "stop
waiting and tell the model"; the abandoned thread ends on its own IO timeout.
Tools with no declared timeout run inline exactly as before, so nothing pays for
a thread it does not need.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Callable

from tools.base import ToolResult

logger = logging.getLogger(__name__)

#: Tools that can block on something outside our control. Everything else runs
#: inline: a thread per tool call would be a cost with no benefit.
#: (delegate_* included: a specialist is an LLM run of its own.)
TOOL_TIMEOUTS: dict[str, float] = {
    "delegate_doc_reader": 60.0,
    "delegate_triage": 120.0,
    "delegate_planner": 120.0,
    "rag_search": 60.0,
    "web_research": 120.0,
    "request_web_search": 30.0,
}


def tool_timeout(tool_name: str) -> float | None:
    """Configured timeout in seconds, or None when the tool runs inline."""
    value = TOOL_TIMEOUTS.get(tool_name)
    try:
        timeout = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return timeout if timeout > 0 else None


def run_with_timeout(call: Callable[[], ToolResult], timeout: float, tool_name: str) -> ToolResult:
    """Run one tool call with a wall-clock budget, as a structured result."""
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(call)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeout:
        future.cancel()
        logger.warning("Tool %s exceeded %.0fs; giving up on it", tool_name, timeout)
        return ToolResult(
            ok=False,
            content=f"工具 {tool_name} 超过 {timeout:.0f} 秒未返回，已放弃等待。可以缩小范围或换个问法重试。",
            data={"code": "tool_timeout", "tool": tool_name, "timeout_seconds": timeout},
        )
    except Exception as exc:  # a raising tool must not break the turn either
        logger.exception("Tool %s raised while running with a timeout", tool_name)
        return ToolResult(ok=False, content=f"Tool execution error: {exc}")
    finally:
        # Never wait for the abandoned worker: that would reintroduce the hang.
        executor.shutdown(wait=False)
