"""MCP tool name sanitization and collision-safe building.

The names follow OpenClaw's pattern:
  - Format: `serverName__toolName`
  - Allowed chars in each side: A-Z, a-z, 0-9, _, -
  - Other chars become `-`
  - server name capped at 30 chars
  - combined tool name capped at 64 chars (LLM API limits)
  - collisions against a reserved set get `-2` / `-3` suffix
"""

from __future__ import annotations

import re
from typing import Iterable

SERVER_NAME_MAX = 30
TOOL_NAME_MAX = 64
TOOL_NAME_SEPARATOR = "__"

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_-]")


def sanitize_server_name(name: str) -> str:
    """Sanitize and truncate a server name to safe characters and length.

    Examples:
        "github"            -> "github"
        "my-cool-server"    -> "my-cool-server"
        "context7/mcp!"     -> "context7-mcp-"
        "a" * 50            -> "a" * 30
    """
    cleaned = _SANITIZE_RE.sub("-", name)
    return cleaned[:SERVER_NAME_MAX]


def sanitize_tool_name(name: str) -> str:
    """Sanitize an MCP tool name to safe characters (no length cap here).

    The 64-char cap is applied at the *combined* name level by
    `build_safe_tool_name`.
    """
    return _SANITIZE_RE.sub("-", name)


def _truncate_combined(server_part: str, tool_part: str) -> tuple[str, str]:
    """Return (server_part, tool_part) such that their joined length is
    at most TOOL_NAME_MAX. Truncates the tool part first since it's
    usually more user-facing.
    """
    sep_len = len(TOOL_NAME_SEPARATOR)
    available = TOOL_NAME_MAX - len(server_part) - sep_len
    if available <= 0:
        # server name already exhausted the budget; keep the separator
        # and produce an empty tool part
        return server_part[: TOOL_NAME_MAX - sep_len], ""
    if len(tool_part) <= available:
        return server_part, tool_part
    return server_part, tool_part[:available]


def build_safe_tool_name(
    server_name: str,
    tool_name: str,
    reserved: Iterable[str] | None = None,
) -> str:
    """Build a collision-safe, length-bounded tool name.

    Format: `{sanitized_server}__{sanitized_tool}`, total <= 64 chars.
    If the result collides with a name in `reserved`, append `-2`,
    `-3`, ... until it doesn't.

    Examples:
        build_safe_tool_name("github", "create_issue")
        -> "github__create_issue"

        build_safe_tool_name("context7", "get-docs")
        -> "context7__get-docs"
    """
    safe_server = sanitize_server_name(server_name)
    safe_tool = sanitize_tool_name(tool_name)
    safe_server, safe_tool = _truncate_combined(safe_server, safe_tool)
    candidate = f"{safe_server}{TOOL_NAME_SEPARATOR}{safe_tool}"

    if reserved is None:
        return candidate

    used = set(reserved)
    if candidate not in used:
        return candidate

    # Append -2, -3, ... until unique. Truncate the tool part further
    # to make room for the suffix.
    for n in range(2, 1000):
        suffix = f"-{n}"
        server_part, tool_part = _truncate_combined(
            safe_server, safe_tool[: max(0, TOOL_NAME_MAX - len(safe_server) - len(TOOL_NAME_SEPARATOR) - len(suffix))]
        )
        attempt = f"{server_part}{TOOL_NAME_SEPARATOR}{tool_part}{suffix}"
        if attempt not in used:
            return attempt

    raise RuntimeError(
        f"Could not find a unique tool name for server={server_name!r} "
        f"tool={tool_name!r} after 1000 attempts"
    )
