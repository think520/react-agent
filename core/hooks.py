"""Two-layer hook registry for the agent loop (AG-2.1).

A minimal, in-process registry (no plugin API). The loop dispatches at four
points, in registration order, and hook exceptions are caught so a broken hook
never breaks the loop:

- before_turn / after_turn (turn lifecycle: memory injection, usage accounting,
  title generation, learning events).
- before_tool / after_tool (tool lifecycle: allowlisting, permission checks,
  result sanitization, evidence-state recording).

A before_tool hook returns a ToolGate (allow, or block with reason/terminate).
A before_turn hook may return a string to inject into the turn's system
context. after_tool hooks may return a replacement ToolResult.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

logger = logging.getLogger(__name__)

BEFORE_TURN = "before_turn"
AFTER_TURN = "after_turn"
BEFORE_TOOL = "before_tool"
AFTER_TOOL = "after_tool"

_HOOK_EVENTS = (BEFORE_TURN, AFTER_TURN, BEFORE_TOOL, AFTER_TOOL)


@dataclass(frozen=True)
class ToolGate:
    """Decision returned by a before_tool hook."""

    allow: bool = True
    reason: str = ""
    terminate: bool = False


def allow() -> ToolGate:
    return ToolGate(allow=True)


def block(reason: str = "", terminate: bool = False) -> ToolGate:
    return ToolGate(allow=False, reason=reason, terminate=terminate)


_registry: dict[str, list[Callable[..., Any]]] = {event: [] for event in _HOOK_EVENTS}


def register_hook(event: str, fn: Callable[..., Any]) -> None:
    """Register a hook for an event. Registration order is dispatch order."""
    if event not in _HOOK_EVENTS:
        raise ValueError(f"Unknown hook event: {event}")
    _registry[event].append(fn)


def clear_hooks(event: str | None = None) -> None:
    """Remove registered hooks (for tests). event=None clears all events."""
    if event is None:
        for name in _HOOK_EVENTS:
            _registry[name].clear()
    elif event in _HOOK_EVENTS:
        _registry[event].clear()


def registered(event: str) -> list[Callable[..., Any]]:
    """Return the hooks registered for an event (read-only view)."""
    return list(_registry.get(event, ()))


def dispatch(event: str, **kwargs: Any) -> list[Any]:
    """Dispatch to hooks for event in order; returns non-None results.

    Hook exceptions are logged and swallowed so observers cannot break the
    loop. This mirrors the event-bus failure isolation discipline.
    """
    if event not in _HOOK_EVENTS:
        raise ValueError(f"Unknown hook event: {event}")
    results: list[Any] = []
    for fn in _registry[event]:
        try:
            result = fn(**kwargs)
            if result is not None:
                results.append(result)
        except Exception:  # noqa: BLE001 - a hook must not break the loop
            logger.exception("Hook %r failed for event %r", fn, event)
    return results


def before_turn_results(**kwargs: Any) -> list[str]:
    """Collect before_turn hook return values (injected context strings)."""
    return [r for r in dispatch(BEFORE_TURN, **kwargs) if isinstance(r, str) and r]


def before_tool_gates(**kwargs: Any) -> list[ToolGate]:
    """Collect before_tool hook gates (allow/block decisions)."""
    return [r for r in dispatch(BEFORE_TOOL, **kwargs) if isinstance(r, ToolGate)]
