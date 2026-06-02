"""Wrap a single MCP tool as a Bobodan-compatible callable.

The wrapped function takes **kwargs (whatever the LLM passes from the
tool's inputSchema) and dispatches to MCPManager. The result is
converted to a ToolResult that Bobodan's execute_tool() can handle.
"""

from __future__ import annotations

import logging
from typing import Any

from tools.base import ToolResult

from .manager import MCPManager

logger = logging.getLogger(__name__)


def _format_content(blocks: list[dict[str, Any]]) -> str:
    """Flatten MCP content blocks into a single text for the LLM.

    Only text blocks are included verbatim. Other block types (image,
    resource, unknown) are summarized so the LLM still gets a signal
    that something non-text was returned.
    """
    parts: list[str] = []
    for block in blocks or []:
        btype = block.get("type", "unknown")
        if btype == "text":
            parts.append(str(block.get("text", "")))
        elif btype == "image":
            parts.append(f"[image: {block.get('mimeType', 'image/png')}]")
        elif btype == "resource":
            parts.append(f"[resource: {block.get('resource', '?')}]")
        else:
            parts.append(f"[{btype}: {block.get('text') or str(block)}]")
    if not parts:
        return "(no content)"
    return "\n".join(parts)


def make_mcp_tool_func(
    server_name: str,
    tool_name: str,
    mgr: MCPManager,
) -> "Any":
    """Build a zero-arg function that the agent loop can register.

    The returned function accepts **kwargs because the MCP tool's
    parameter names come from the server's inputSchema and aren't
    known ahead of time. `execute_tool()` calls the function with the
    parsed tool_call.arguments as kwargs.
    """
    def func(**kwargs: Any) -> ToolResult:
        # Strip None values so optional params with no value don't
        # confuse the server (some MCP servers reject unknown keys).
        clean_kwargs = {k: v for k, v in kwargs.items() if v is not None}
        try:
            result = mgr.call(server_name, tool_name, clean_kwargs)
        except Exception as e:
            logger.exception("MCP tool call crashed: %s.%s", server_name, tool_name)
            return ToolResult(
                ok=False,
                content=f"MCP tool {server_name}.{tool_name} crashed: {type(e).__name__}: {e}",
                data={"server": server_name, "tool": tool_name},
            )

        is_error = bool(result.get("isError", False))
        blocks = result.get("content", []) or []
        if is_error and not blocks:
            content = f"MCP tool {server_name}.{tool_name} returned an error."
        else:
            content = _format_content(blocks)
        return ToolResult(
            ok=not is_error,
            content=content,
            data={"raw": result, "server": server_name, "tool": tool_name},
        )

    # Update the wrapper's __name__ so debug logs and exec_tool's
    # signature introspection read sensibly. Signature is intentionally
    # **kwargs so it accepts any args from the LLM.
    func.__name__ = f"mcp_{server_name}_{tool_name}"
    func.__qualname__ = func.__name__
    return func
