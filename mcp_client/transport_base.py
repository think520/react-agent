"""Abstract base for MCP transports.

Each transport (stdio, SSE, streamable_http) wraps the official
`mcp` SDK's client transport object and exposes four async methods.
The manager calls these from a background event loop.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Transport(ABC):
    """Async interface to an MCP server connection.

    Lifecycle:
        1. Construct with a `MCPServerConfig` and a connection timeout
        2. `await connect()` to establish the underlying MCP session
        3. `await list_tools()` to enumerate exposed tools
        4. `await call_tool(name, args)` per invocation
        5. `await disconnect()` on shutdown

    Implementations should be safe to disconnect without prior connect
    (no-op) and to call `connect()` again after `disconnect()`.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish the connection. Raise on failure (timeout, refused, etc)."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Tear down the connection. No-op if not connected."""

    @abstractmethod
    async def list_tools(self) -> list[dict[str, Any]]:
        """Return the list of tools exposed by the server.

        Each item is a dict with at least: name, description, inputSchema.
        The exact shape matches the official SDK's `listTools` result.
        """

    @abstractmethod
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a tool and return its result.

        The result is the SDK's raw response dict, which usually
        contains `content` (list of content blocks) and `isError`.
        """

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the underlying connection is currently active."""
