"""Runtime facade (AG-0.5).

The single import surface for the agent runtime's external dependencies:
provider, tools, and memory. Future integrations only touch this facade,
never the loop or the services.

Python has no build-time module scan, so this facade is enforced by import
convention plus the contract test in tests/test_runtime_facade.py.
"""

from __future__ import annotations

from core.runtime.memory import PersonalKnowledgeStore
from core.runtime.provider import (
    GuardedProvider,
    ProviderFactory,
    create_provider,
    guard_provider,
)
from core.runtime.tools import (
    TOOL_REGISTRY,
    ToolResult,
    execute_tool,
    get_tools_schema,
    register_tool,
)

__all__ = [
    "GuardedProvider",
    "ProviderFactory",
    "create_provider",
    "guard_provider",
    "TOOL_REGISTRY",
    "ToolResult",
    "execute_tool",
    "get_tools_schema",
    "register_tool",
    "PersonalKnowledgeStore",
]
