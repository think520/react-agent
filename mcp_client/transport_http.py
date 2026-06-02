"""streamable_http transport — modern MCP HTTP transport.

Wraps the official `mcp.client.streamable_http.streamablehttp_client`
context manager and the `mcp.ClientSession`. Keeps both alive for the
lifetime of the connection.
"""

from __future__ import annotations

import logging
from typing import Any

# Module-level imports so tests can patch them with `patch.multiple`.
from mcp import ClientSession  # noqa: F401
from mcp.client.streamable_http import streamablehttp_client  # noqa: F401

from .config import MCPServerConfig
from .transport_base import Transport

logger = logging.getLogger(__name__)


class StreamableHttpTransport(Transport):
    """HTTP transport using the streamable MCP protocol."""

    def __init__(self, config: MCPServerConfig, timeout: int) -> None:
        self._config = config
        self._timeout = float(timeout)
        self._cm: Any = None  # the streamablehttp_client context manager
        self._session_cm: Any = None  # the ClientSession context manager
        self._session: Any = None  # the actual ClientSession (post-__aenter__)
        self._connected = False

    async def connect(self) -> None:
        if self._config.url is None:
            raise ValueError(f"server {self._config.name!r}: streamable_http requires url")
        headers = self._config.headers or None

        self._cm = streamablehttp_client(
            url=self._config.url,
            headers=headers,
            timeout=self._timeout,
        )
        read, write, _ = await self._cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        self._connected = True
        logger.info("streamable_http: connected to %s", self._config.url)

    async def disconnect(self) -> None:
        if self._session_cm is not None:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception as e:
                logger.debug("session close raised: %s", e)
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception as e:
                logger.debug("transport close raised: %s", e)
        self._session = None
        self._session_cm = None
        self._cm = None
        self._connected = False

    async def list_tools(self) -> list[dict[str, Any]]:
        if self._session is None:
            raise RuntimeError("not connected")
        result = await self._session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.inputSchema or {"type": "object", "properties": {}},
            }
            for tool in result.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("not connected")
        result = await self._session.call_tool(name, arguments or {})

        # Convert SDK content blocks to a plain JSON-serializable shape.
        content: list[dict[str, Any]] = []
        for block in result.content or []:
            if hasattr(block, "text"):
                content.append({"type": "text", "text": block.text})
            elif hasattr(block, "data") and hasattr(block, "mimeType"):
                content.append(
                    {"type": "image", "data": block.data, "mimeType": block.mimeType}
                )
            elif hasattr(block, "resource"):
                content.append({"type": "resource", "resource": str(block.resource)})
            else:
                content.append({"type": "text", "text": str(block)})

        return {
            "content": content,
            "isError": bool(getattr(result, "isError", False)),
        }

    @property
    def is_connected(self) -> bool:
        return self._connected
