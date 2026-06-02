"""MCP server configuration loader.

Reads the `mcp:` section of config.yaml, validates it, and substitutes
`${ENV_VAR}` placeholders in any string field with environment values.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

TransportType = Literal["stdio", "sse", "streamable_http"]


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server.

    Fields map directly to the YAML schema. The validation rules:
      - stdio transport: requires `command`
      - http transport (sse / streamable_http): requires `url`
      - `transport` is optional; defaults are inferred from which of
        `command` / `url` is present
    """

    name: str
    enabled: bool = True
    transport: TransportType = "stdio"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    connection_timeout: int | None = None  # seconds, override global

    def validate(self) -> None:
        """Raise ValueError if the config is malformed."""
        if not self.enabled:
            return
        if self.transport == "stdio":
            if not self.command:
                raise ValueError(
                    f"MCP server '{self.name}': stdio transport requires 'command'"
                )
        else:
            if not self.url:
                raise ValueError(
                    f"MCP server '{self.name}': {self.transport} transport requires 'url'"
                )
            if not (self.url.startswith("http://") or self.url.startswith("https://")):
                raise ValueError(
                    f"MCP server '{self.name}': url must be http:// or https://"
                )


@dataclass
class MCPConfig:
    """Top-level MCP config: global defaults + server list."""

    enabled: bool = False
    connection_timeout: int = 30
    tool_call_timeout: int = 60
    servers: dict[str, MCPServerConfig] = field(default_factory=dict)

    def enabled_servers(self) -> list[MCPServerConfig]:
        return [s for s in self.servers.values() if s.enabled]

    def validate(self) -> None:
        """Validate the whole config; raise on any server error."""
        for server in self.servers.values():
            server.validate()


def substitute_env(value: str) -> str:
    """Replace ${ENV_VAR} in a string with the env var's value.

    Raises:
        EnvironmentError: if any referenced env var is missing.
    """
    missing: list[str] = []

    def replacer(match: re.Match[str]) -> str:
        var = match.group(1)
        val = os.environ.get(var)
        if val is None:
            missing.append(var)
            return match.group(0)
        return val

    result = ENV_VAR_PATTERN.sub(replacer, value)
    if missing:
        raise EnvironmentError(
            f"Missing environment variables: {', '.join(sorted(set(missing)))}"
        )
    return result


def substitute_env_in_mapping(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively substitute env vars in a dict's string leaves."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, str):
            out[k] = substitute_env(v)
        elif isinstance(v, dict):
            out[k] = substitute_env_in_mapping(v)
        elif isinstance(v, list):
            new_list = []
            for item in v:
                if isinstance(item, str):
                    new_list.append(substitute_env(item))
                elif isinstance(item, dict):
                    new_list.append(substitute_env_in_mapping(item))
                else:
                    new_list.append(item)
            out[k] = new_list
        else:
            out[k] = v
    return out


def parse_server_config(name: str, raw: dict[str, Any]) -> MCPServerConfig:
    """Parse a single server config dict into MCPServerConfig.

    Auto-infers `transport` if not specified:
      - has `command` → stdio
      - has `url` → sse (default for HTTP)
    """
    if not isinstance(raw, dict):
        raise ValueError(
            f"MCP server '{name}': config must be a mapping, got {type(raw).__name__}"
        )

    raw = substitute_env_in_mapping(raw)

    transport_raw = raw.get("transport")
    command = raw.get("command")
    url = raw.get("url")

    if transport_raw:
        if transport_raw not in ("stdio", "sse", "streamable_http"):
            raise ValueError(
                f"MCP server '{name}': unknown transport '{transport_raw}' "
                f"(must be stdio, sse, or streamable_http)"
            )
        transport: TransportType = transport_raw  # type: ignore[assignment]
    elif command:
        transport = "stdio"
    elif url:
        transport = "sse"
    else:
        raise ValueError(
            f"MCP server '{name}': must have either 'command' (stdio) or 'url' (http)"
        )

    cfg = MCPServerConfig(
        name=name,
        enabled=raw.get("enabled", True),
        transport=transport,
        command=command,
        args=list(raw.get("args", [])),
        env=dict(raw.get("env", {})),
        cwd=raw.get("cwd"),
        url=url,
        headers=dict(raw.get("headers", {})),
        connection_timeout=raw.get("connection_timeout"),
    )
    cfg.validate()
    return cfg


def load_config(config: dict[str, Any] | None) -> MCPConfig:
    """Load MCP config from the full app config dict.

    `config` is the result of loading config.yaml. The function picks
    out the `mcp` section and parses it. If the section is missing or
    `mcp.enabled` is False, returns a disabled MCPConfig.
    """
    if not config:
        return MCPConfig(enabled=False)

    raw = config.get("mcp")
    if not isinstance(raw, dict):
        return MCPConfig(enabled=False)

    enabled = bool(raw.get("enabled", False))
    connection_timeout = int(raw.get("connection_timeout", 30))
    tool_call_timeout = int(raw.get("tool_call_timeout", 60))

    servers_raw = raw.get("servers", {}) or {}
    if not isinstance(servers_raw, dict):
        raise ValueError("mcp.servers must be a mapping")

    servers: dict[str, MCPServerConfig] = {}
    for name, srv_raw in servers_raw.items():
        servers[name] = parse_server_config(name, srv_raw)

    return MCPConfig(
        enabled=enabled,
        connection_timeout=connection_timeout,
        tool_call_timeout=tool_call_timeout,
        servers=servers,
    )
