"""Built-in hooks: the first real consumers of the hook registry (P0-9).

The registry, its four dispatch points and its tests have existed since AG-2.1,
but nothing in production ever registered a hook - so the architecture doc
claimed permission gates and result sanitization that the running code did not
have. These two functions are what the agent loop registers, and they are also
where the audit P0-9 (tool results had no size limit) is fixed: the boundary
belongs at the dispatch layer, not inside each tool.
"""

from __future__ import annotations

from typing import Any, Iterable

from core.hooks import AFTER_TOOL, BEFORE_TOOL, ToolGate, block, register_hook, registered
from tools.base import ToolResult

#: Per-result ceiling before the text enters the conversation.
MAX_TOOL_RESULT_CHARS = 32000
#: Keep both ends: the beginning usually carries the shape, the end the tail of
#: a listing. The middle is what gets dropped.
_HEAD_SHARE = 0.4
_TAIL_SHARE = 0.4


def cap_tool_result(
    *,
    tool_name: str = "",
    args: dict | None = None,
    result: Any = None,
    session: Any = None,
    **kwargs: Any,
) -> ToolResult | None:
    """after_tool hook: bound one tool result before the model sees it.

    Returns a replacement result, or None to leave the result untouched.
    Failed results are exempt on purpose: the error text is the only debugging
    trail the user has.
    """
    if not isinstance(result, ToolResult) or result.ok is False:
        return None
    content = result.content or ""
    if len(content) <= MAX_TOOL_RESULT_CHARS:
        return None

    head = int(MAX_TOOL_RESULT_CHARS * _HEAD_SHARE)
    tail = int(MAX_TOOL_RESULT_CHARS * _TAIL_SHARE)
    omitted = len(content) - head - tail
    result.content = (
        f"{content[:head]}\n\n"
        f"… 已省略 {omitted} 个字符（单条工具结果上限 {MAX_TOOL_RESULT_CHARS}，"
        f"共 {len(content)} 字符）。需要更多内容请用 offset / limit 分段读取。\n\n"
        f"{content[-tail:]}"
    )
    return result


def allowlist_gate(
    *,
    tool_name: str = "",
    allowed: Iterable[str] | None = None,
    **kwargs: Any,
) -> ToolGate | None:
    """before_tool hook: the per-run tool allowlist as a gate.

    The allowlist is passed as data on every dispatch rather than registered
    globally, because a specialist run must not narrow the main loop.
    """
    if allowed is None:
        return None
    if tool_name not in allowed:
        return block(f"Tool unavailable in this runtime: {tool_name}")
    return None


def register_builtin_hooks() -> None:
    """Install the built-in hooks once; safe to call from every entry point."""
    if allowlist_gate not in registered(BEFORE_TOOL):
        register_hook(BEFORE_TOOL, allowlist_gate)
    if cap_tool_result not in registered(AFTER_TOOL):
        register_hook(AFTER_TOOL, cap_tool_result)
