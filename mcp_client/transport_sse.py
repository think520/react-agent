"""SSE transport — legacy HTTP+SSE MCP transport.

Stub for Step 2; real implementation lands in Step 3.
"""

from __future__ import annotations

from .transport_base import Transport


class SseTransport(Transport):
    """SSE-based HTTP transport (legacy MCP transport)."""

    def __init__(self, config, timeout: int) -> None:  # type: ignore[no-untyped-def]
        self._config = config
        self._timeout = timeout
        self._connected = False

    async def connect(self) -> None:
        raise NotImplementedError("SseTransport.connect — implemented in Step 3")

    async def disconnect(self) -> None:
        self._connected = False

    async def list_tools(self):
        return []

    async def call_tool(self, name: str, arguments: dict):
        raise NotImplementedError("SseTransport.call_tool — implemented in Step 3")

    @property
    def is_connected(self) -> bool:
        return self._connected
