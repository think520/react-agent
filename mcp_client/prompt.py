"""Build the MCP-aware segment of the system prompt.

Injected alongside skills/memory so the LLM knows which MCP tools
are available, under what server name, and how to call them
(`server__tool`).
"""

from __future__ import annotations

from .manager import MCPManager


def build_mcp_status_prompt(mgr: MCPManager | None) -> str:
    """Return a system prompt section describing active MCP servers.

    Returns an empty string if `mgr` is None or no servers are enabled.
    """
    if mgr is None or not mgr.enabled:
        return ""

    states = mgr.get_all_states()
    lines: list[str] = ["\n## MCP Servers"]
    any_listed = False
    for name, state in states.items():
        if not state.config.enabled:
            continue
        n_tools = len(state.tools) if state.state == "connected" else 0
        if state.state == "connected" and n_tools > 0:
            lines.append(
                f"- `{name}`: {n_tools} tools available; call as `{name}__<tool_name>`"
            )
            any_listed = True
        elif state.state == "connected":
            lines.append(f"- `{name}`: connected but exposes no tools")
        elif state.state == "error":
            err = state.last_error or "unknown error"
            # Truncate long error messages
            if len(err) > 80:
                err = err[:77] + "..."
            lines.append(f"- `{name}`: unavailable ({err})")
        else:
            lines.append(f"- `{name}`: {state.state} (call once to retry)")

    if not any_listed:
        # If nothing's connected, add a hint
        if any(s.config.enabled for s in states.values()):
            lines.append(
                "(MCP tools are not yet visible. They will appear after the first tool call attempts to connect.)"
            )
    return "\n".join(lines)
