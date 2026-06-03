"""MCPManager — central registry and lifecycle owner for MCP servers.

Responsibilities:
  - Hold a `MCPConfig` and per-server state (transport, connection
    status, last error, cached tool list)
  - Lazy-connect on first tool call (per server)
  - Provide a synchronous `call()` that bridges to the async SDK
  - Expose status for `/mcp status` REPL command
  - Handle `reload(new_config)` by diffing and applying changes
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import MCPConfig, MCPServerConfig
from .event_loop import AsyncEventLoop
from .transport_base import Transport

logger = logging.getLogger(__name__)


@dataclass
class ServerState:
    """Runtime state for one configured MCP server."""

    config: MCPServerConfig
    state: str = "disconnected"  # disconnected | connecting | connected | error
    last_error: str | None = None
    last_connected_at: str | None = None
    last_attempt_at: str | None = None
    transport: Transport | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class MCPManager:
    """Owns the lifecycle of every MCP server connection.

    Threading model:
      - `call()` and `reload()` may be called from any thread
      - The async SDK calls run on the background `AsyncEventLoop`
      - Each server has its own lock to serialize connect/disconnect
    """

    def __init__(self, config: MCPConfig) -> None:
        self._config = config
        self._servers: dict[str, ServerState] = {}
        for name, srv_cfg in config.servers.items():
            self._servers[name] = ServerState(config=srv_cfg)
        self._global_lock = threading.Lock()

    # ----- introspection -----

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def list_server_names(self) -> list[str]:
        return list(self._servers.keys())

    def get_state(self, name: str) -> ServerState | None:
        return self._servers.get(name)

    def get_all_states(self) -> dict[str, ServerState]:
        return dict(self._servers)

    def get_global_timeouts(self) -> tuple[int, int]:
        return self._config.connection_timeout, self._config.tool_call_timeout

    # ----- connection lifecycle -----

    async def _connect_server(self, state: ServerState) -> None:
        """Async: actually open the connection. Caller must hold state._lock."""
        if state.state == "connected":
            return
        state.state = "connecting"
        state.last_attempt_at = _now_iso()
        try:
            transport = self._build_transport(state.config)
            await transport.connect()
            state.transport = transport
            state.tools = await transport.list_tools()
            state.state = "connected"
            state.last_connected_at = _now_iso()
            state.last_error = None
            logger.info("MCP server %r connected (%d tools)", state.config.name, len(state.tools))
        except Exception as e:
            state.state = "error"
            state.last_error = f"{type(e).__name__}: {e}"
            state.transport = None
            state.tools = []
            logger.warning("MCP server %r failed to connect: %s", state.config.name, state.last_error)
            raise

    async def _disconnect_server(self, state: ServerState) -> None:
        """Async: cleanly close the connection. Caller must hold state._lock."""
        if state.transport is None:
            return
        try:
            await state.transport.disconnect()
        except Exception as e:
            logger.debug("MCP server %r disconnect raised: %s", state.config.name, e)
        finally:
            state.transport = None
            state.tools = []
            state.state = "disconnected"

    def _build_transport(self, cfg: MCPServerConfig) -> Transport:
        """Construct a transport instance. Import lazily so missing
        optional SDK pieces don't break the others."""
        from .transport_stdio import StdioTransport
        from .transport_http import StreamableHttpTransport
        from .transport_sse import SseTransport

        if cfg.transport == "stdio":
            return StdioTransport(cfg, timeout=cfg.connection_timeout or self._config.connection_timeout)
        if cfg.transport == "streamable_http":
            return StreamableHttpTransport(cfg, timeout=cfg.connection_timeout or self._config.connection_timeout)
        if cfg.transport == "sse":
            return SseTransport(cfg, timeout=cfg.connection_timeout or self._config.connection_timeout)
        raise ValueError(f"Unknown transport: {cfg.transport!r}")

    # ----- public sync API (used by tool wrapper and /mcp commands) -----

    def call(self, server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Synchronously call a tool. Bridges to async via the event loop.

        Returns a dict matching the MCP SDK's callTool result shape
        (with `content` and `isError` keys). On connection failure,
        returns a synthetic error result.
        """
        state = self._servers.get(server)
        if state is None:
            return _error_result(f"Unknown MCP server: {server}")
        if not state.config.enabled:
            return _error_result(f"MCP server {server!r} is disabled in config")

        async def runner() -> dict[str, Any]:
            with state._lock:
                if state.state != "connected" or state.transport is None:
                    # Lazy connect (or reconnect after failure)
                    await self._connect_server(state)
            # Re-read transport under lock-free state (already connected)
            transport = state.transport
            assert transport is not None
            return await transport.call_tool(tool, args)

        try:
            return AsyncEventLoop.get().run_sync(
                runner(), timeout=self._config.tool_call_timeout
            )
        except TimeoutError:
            return _error_result(
                f"MCP tool call {server}.{tool} timed out after {self._config.tool_call_timeout}s"
            )
        except Exception as e:
            return _error_result(f"MCP tool call {server}.{tool} failed: {type(e).__name__}: {e}")

    def list_tools_for_server(self, server: str) -> list[dict[str, Any]]:
        """Synchronously list tools for a server, connecting if needed."""
        state = self._servers.get(server)
        if state is None or not state.config.enabled:
            return []

        async def runner() -> list[dict[str, Any]]:
            with state._lock:
                if state.state != "connected" or state.transport is None:
                    await self._connect_server(state)
            return list(state.tools)

        try:
            return AsyncEventLoop.get().run_sync(
                runner(), timeout=self._config.connection_timeout
            )
        except Exception as e:
            logger.warning("Failed to list tools for %s: %s", server, e)
            return []

    def list_all_tools(self) -> dict[str, list[dict[str, Any]]]:
        """For all connected/connectable enabled servers, return {server: tools}."""
        out: dict[str, list[dict[str, Any]]] = {}
        for name, state in self._servers.items():
            if not state.config.enabled:
                continue
            tools = self.list_tools_for_server(name)
            if tools:
                out[name] = tools
        return out

    def restart_server(self, name: str) -> bool:
        """Disconnect and reconnect a server. Returns True on success."""
        state = self._servers.get(name)
        if state is None:
            return False

        async def runner() -> None:
            with state._lock:
                await self._disconnect_server(state)
                await self._connect_server(state)

        try:
            AsyncEventLoop.get().run_sync(runner(), timeout=self._config.connection_timeout)
            return state.state == "connected"
        except Exception as e:
            state.last_error = f"{type(e).__name__}: {e}"
            return False

    def shutdown(self) -> None:
        """Disconnect all servers. Called on REPL exit."""
        async def runner() -> None:
            for state in self._servers.values():
                with state._lock:
                    if state.transport is not None:
                        try:
                            await self._disconnect_server(state)
                        except Exception:
                            pass

        try:
            AsyncEventLoop.get().run_sync(runner(), timeout=5.0)
        except Exception as e:
            logger.debug("MCPManager shutdown raised: %s", e)

    # ----- reload -----

    def reload(self, new_config: MCPConfig) -> dict[str, list[str]]:
        """Apply a new config. Returns a diff summary {action: [server_names]}.

        Actions:
          - "added": new servers to register (not yet connected)
          - "removed": servers to disconnect + drop
          - "updated": servers whose config changed (disconnect + reconnect)
          - "unchanged": servers with no config change
        """
        old_names = set(self._servers)
        new_names = set(new_config.servers)
        added = new_names - old_names
        removed = old_names - new_names
        common = old_names & new_names

        updated: list[str] = []
        unchanged: list[str] = []
        for name in common:
            old_cfg = self._servers[name].config
            new_cfg = new_config.servers[name]
            if _server_config_changed(old_cfg, new_cfg):
                updated.append(name)
            else:
                unchanged.append(name)

        # Apply changes
        for name in removed:
            state = self._servers.pop(name)
            self._async_disconnect(state)

        for name in updated:
            state = self._servers[name]
            new_cfg = new_config.servers[name]
            self._async_disconnect(state)
            state.config = new_cfg
            state.last_error = None

        for name in added:
            self._servers[name] = ServerState(config=new_config.servers[name])

        self._config = new_config
        logger.info(
            "MCP config reloaded: +%d -%d ~%d =%d",
            len(added), len(removed), len(updated), len(unchanged),
        )
        return {
            "added": sorted(added),
            "removed": sorted(removed),
            "updated": sorted(updated),
            "unchanged": sorted(unchanged),
        }

    def _async_disconnect(self, state: ServerState) -> None:
        """Helper: run an async disconnect on the event loop, best-effort."""
        async def runner() -> None:
            with state._lock:
                if state.transport is not None:
                    try:
                        await self._disconnect_server(state)
                    except Exception:
                        pass

        try:
            AsyncEventLoop.get().run_sync(runner(), timeout=5.0)
        except Exception:
            pass


def _server_config_changed(a: MCPServerConfig, b: MCPServerConfig) -> bool:
    """Return True if any config field that would require a reconnect differs."""
    return (
        a.transport != b.transport
        or a.command != b.command
        or a.args != b.args
        or a.env != b.env
        or a.cwd != b.cwd
        or a.url != b.url
        or a.headers != b.headers
        or a.connection_timeout != b.connection_timeout
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _error_result(message: str) -> dict[str, Any]:
    """Build a synthetic MCP error result matching the SDK shape."""
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }
