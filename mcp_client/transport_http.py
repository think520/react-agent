"""streamable_http transport — modern MCP HTTP transport.

Stub for Step 2; real implementation lands in Step 3.
"""

from __future__ import annotations

from .transport_base import Transport


class StreamableHttpTransport(Transport):
    """HTTP transport using the streamable MCP protocol."""

    def __init__(self, config, timeout: int) -> None:  # type: ignore[no-untyped-def]
        self._config = config
        self._timeout = timeout
        self._connected = False

    async def connect(self) -> None:
        raise NotImplementedError("StreamableHttpTransport.connect — implemented in Step 3")

    async def disconnect(self) -> None:
        self._connected = False

    async def list_tools(self):
        return []

    async def call_tool(self, name: str, arguments: dict):
        raise NotImplementedError("StreamableHttpTransport.call_tool — implemented in Step 3")

    @property
    def is_connected(self) -> bool:
        return self._connected
