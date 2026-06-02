"""stdio transport — spawns a subprocess and speaks JSON-RPC over stdin/stdout.

Stub for Step 2; real implementation lands in Step 3.
"""

from __future__ import annotations

from .transport_base import Transport


class StdioTransport(Transport):
    """Spawn a child process and talk MCP JSON-RPC over its stdio."""

    def __init__(self, config, timeout: int) -> None:  # type: ignore[no-untyped-def]
        self._config = config
        self._timeout = timeout
        self._connected = False

    async def connect(self) -> None:
        raise NotImplementedError("StdioTransport.connect — implemented in Step 3")

    async def disconnect(self) -> None:
        self._connected = False

    async def list_tools(self):
        return []

    async def call_tool(self, name: str, arguments: dict):
        raise NotImplementedError("StdioTransport.call_tool — implemented in Step 3")

    @property
    def is_connected(self) -> bool:
        return self._connected
