"""stdio transport — spawn a child process and speak MCP JSON-RPC over stdio.

Wraps the official `mcp.client.stdio.stdio_client` context manager
and `mcp.ClientSession`. Captures the child's stderr for logging.
"""

from __future__ import annotations

import logging
from typing import Any

# Module-level imports so tests can patch them with `patch.multiple`.
from mcp import ClientSession  # noqa: F401
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: F401

from .config import MCPServerConfig
from .transport_base import Transport

logger = logging.getLogger(__name__)


def _log_stderr_line(server_name: str, line: str) -> None:
    """Forward one line of child stderr to our logger at DEBUG level."""
    if not line:
        return
    logger.debug("mcp[%s] stderr: %s", server_name, line.rstrip())


class StdioTransport(Transport):
    """Spawn a child process and talk MCP JSON-RPC over its stdio."""

    def __init__(self, config: MCPServerConfig, timeout: int) -> None:
        self._config = config
        self._timeout = float(timeout)
        self._cm: Any = None
        self._session_cm: Any = None
        self._session: Any = None
        self._stderr_logger: Any = None
        self._connected = False

    async def connect(self) -> None:
        if not self._config.command:
            raise ValueError(
                f"server {self._config.name!r}: stdio transport requires 'command'"
            )

        params = StdioServerParameters(
            command=self._config.command,
            args=list(self._config.args or []),
            env=self._config.env or None,
            cwd=self._config.cwd,
        )

        # Capture stderr via a custom TextIO that forwards each line
        # to the module-level logger (per OpenClaw pattern).
        server_name = self._config.name

        class _StderrToLogger:
            def write(self_inner, data: str) -> None:
                for line in data.splitlines():
                    _log_stderr_line(server_name, line)

            def flush(self_inner) -> None:
                pass

        self._stderr_logger = _StderrToLogger()

        self._cm = stdio_client(params, errlog=self._stderr_logger)
        read, write = await self._cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        self._connected = True
        logger.info(
            "stdio: connected to %s (command=%s, args=%s)",
            self._config.name, self._config.command, self._config.args,
        )

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
        self._stderr_logger = None
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

        content: list[dict[str, Any]] = []
        for block in result.content or []:
            btype = getattr(block, "type", None)
            if btype == "text" and getattr(block, "text", None) is not None:
                content.append({"type": "text", "text": block.text})
            elif btype == "image" and hasattr(block, "data") and hasattr(block, "mimeType"):
                content.append(
                    {"type": "image", "data": block.data, "mimeType": block.mimeType}
                )
            elif btype == "resource" and hasattr(block, "resource"):
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
