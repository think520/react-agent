"""Build the catalog of MCP tool specs from a connected MCPManager.

Each spec is a dict with:
  - safe_name:   "server__tool" (collision-safe, length-bounded)
  - server:      original server name
  - tool_name:   original MCP tool name
  - description: tool description for the LLM
  - inputSchema: JSON Schema for the tool's parameters
"""

from __future__ import annotations

import logging
from typing import Any

from .manager import MCPManager
from .naming import build_safe_tool_name

logger = logging.getLogger(__name__)

# Set of MCP safe_names registered in this catalog. Exposed so the
# agent loop can distinguish MCP tools from builtin tools and so the
# REPL /mcp commands can list/manage them.
_mcp_safe_names: set[str] = set()


def reset_mcp_registry() -> None:
    """Clear the in-process MCP tool name set (test helper)."""
    _mcp_safe_names.clear()


def is_mcp_tool(safe_name: str) -> bool:
    """Return True if the given tool name was registered by MCP."""
    return safe_name in _mcp_safe_names


def mcp_tool_names() -> set[str]:
    """Return all MCP-registered tool names (snapshot)."""
    return set(_mcp_safe_names)


def build_mcp_tool_specs(
    mgr: MCPManager,
    *,
    reserved: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Enumerate tools across all enabled servers, connect lazily.

    Each server's tools are pulled via the manager (which lazily
    connects on first call). If a server is unreachable, its tools
    are skipped and a warning is logged — the failure is isolated.

    The optional `reserved` set lets callers pre-register names that
    should not be reused (e.g. builtin Bobodan tools). New names
    collide against `reserved` and the existing MCP set.
    """
    reserved = set(reserved or ())
    reserved.update(_mcp_safe_names)
    out: list[dict[str, Any]] = []
    for server_name in mgr.list_server_names():
        state = mgr.get_state(server_name)
        if state is None or not state.config.enabled:
            continue
        try:
            tools = mgr.list_tools_for_server(server_name)
        except Exception as e:
            logger.warning(
                "Skipping tools for %s (catalog fetch failed): %s",
                server_name, e,
            )
            continue
        for tool in tools:
            raw_name = tool.get("name", "")
            if not raw_name:
                continue
            safe_name = build_safe_tool_name(server_name, raw_name, reserved=reserved)
            reserved.add(safe_name)
            _mcp_safe_names.add(safe_name)
            out.append(
                {
                    "safe_name": safe_name,
                    "server": server_name,
                    "tool_name": raw_name,
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema")
                    or {"type": "object", "properties": {}},
                }
            )
    return out
