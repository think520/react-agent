"""Tool facade (AG-0.5): the single door to the tool registry.

Re-exports the canonical tool symbols so consumers never reach into the tools
package directly; a future alternate tool runtime only changes this module.
"""

from __future__ import annotations

from tools import (
    TOOL_REGISTRY,
    ToolResult,
    execute_tool,
    get_tools_schema,
)
from tools.base import register_tool

__all__ = [
    "TOOL_REGISTRY",
    "ToolResult",
    "execute_tool",
    "get_tools_schema",
    "register_tool",
]
