"""MCP integration entry point — called by REPL during startup.

Loads MCP config, initializes the manager, and registers all
discovered tools with the standard `register_tool()` so they appear
in the LLM's tool list.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp_client.catalog import (
    build_mcp_tool_specs,
    is_mcp_tool,
    mcp_tool_names,
    reset_mcp_registry,
)
from mcp_client.config import load_config as load_mcp_config
from mcp_client.manager import MCPManager
from mcp_client.prompt import build_mcp_status_prompt
from mcp_client.tool_wrapper import make_mcp_tool_func
from tools.base import register_tool

logger = logging.getLogger(__name__)

# Module-level state — a single MCPManager per process
_mcp_manager: MCPManager | None = None
_mcp_config_dict: dict | None = None


def get_mcp_manager() -> MCPManager | None:
    """Return the active MCPManager, or None if MCP isn't initialized."""
    return _mcp_manager


def get_mcp_config_dict() -> dict | None:
    """Return the raw app config dict (for hot-reload via /mcp reload)."""
    return _mcp_config_dict


def register_mcp_tools(config: dict) -> MCPManager | None:
    """Initialize MCP and register all tool specs with `register_tool`.

    Args:
        config: the full app config dict (output of ProviderFactory.load_config).

    Returns:
        The MCPManager instance, or None if MCP is disabled / config invalid.
        Per-server connection failures are isolated: a server that can't
        connect is logged and skipped, other servers are unaffected.
    """
    global _mcp_manager, _mcp_config_dict
    _mcp_config_dict = config

    mcp_cfg = load_mcp_config(config)
    if not mcp_cfg.enabled:
        logger.info("MCP disabled in config")
        return None

    if not mcp_cfg.servers:
        logger.info("MCP enabled but no servers configured")
        return None

    reset_mcp_registry()
    _mcp_manager = MCPManager(mcp_cfg)

    # Collect existing tool names so we can avoid collisions in safe_name
    from tools.base import TOOL_REGISTRY
    reserved = set(TOOL_REGISTRY.keys())

    specs = build_mcp_tool_specs(_mcp_manager, reserved=reserved)
    for spec in specs:
        func = make_mcp_tool_func(spec["server"], spec["tool_name"], _mcp_manager)
        register_tool(
            name=spec["safe_name"],
            description=spec["description"],
            params_schema=spec["inputSchema"],
            func=func,
        )
    logger.info(
        "MCP: %d tools registered from %d server(s)",
        len(specs),
        sum(1 for s in _mcp_manager.get_all_states().values() if s.config.enabled),
    )
    return _mcp_manager


def get_mcp_status_text() -> str:
    """Human-readable MCP status for /mcp status and the startup panel."""
    if _mcp_manager is None:
        return "MCP: not initialized"
    info_lines: list[str] = []
    states = _mcp_manager.get_all_states()
    connected = sum(1 for s in states.values() if s.state == "connected")
    total = sum(1 for s in states.values() if s.config.enabled)
    n_tools = len(mcp_tool_names())
    info_lines.append(f"MCP: {connected}/{total} connected, {n_tools} tools")
    for name, state in sorted(states.items()):
        if not state.config.enabled:
            continue
        if state.state == "connected":
            info_lines.append(f"  ✓ {name}: {len(state.tools)} tools")
        else:
            err = state.last_error or state.state
            if len(err) > 60:
                err = err[:57] + "..."
            info_lines.append(f"  ✗ {name}: {err}")
    return "\n".join(info_lines)


def shutdown_mcp() -> None:
    """Disconnect all MCP servers. Called on REPL exit."""
    global _mcp_manager
    if _mcp_manager is not None:
        _mcp_manager.shutdown()
        _mcp_manager = None


__all__ = [
    "get_mcp_manager",
    "get_mcp_config_dict",
    "register_mcp_tools",
    "get_mcp_status_text",
    "shutdown_mcp",
    "build_mcp_status_prompt",
    "is_mcp_tool",
    "mcp_tool_names",
]
