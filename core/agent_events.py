"""Canonical agent event types and helpers (AG-0.2).

Four-layer convergence contract:

    agent_start -> turn_start -> message_start -> message_delta -> message_end
                -> tool_start -> tool_end -> turn_end -> agent_end -> agent_settled

- agent layer: agent_start / agent_end / agent_settled (a settled run is final).
- turn layer:  turn_start / turn_end (one user message -> one assistant answer).
- message layer: message_start / message_delta / message_end (deltas carry content + seq).
- tool layer:   tool_start / tool_end.

The existing AgentLoop still emits its legacy names; this module is the single
mapping authority that upgrades them to canonical names without touching the
loop. The Web adapter (web/backend/events.py) translates canonical names back
to the stable SSE event names, so the frontend sees zero change.
"""

from __future__ import annotations

from typing import Any

AGENT_START = "agent_start"
TURN_START = "turn_start"
MESSAGE_START = "message_start"
MESSAGE_DELTA = "message_delta"
MESSAGE_END = "message_end"
TOOL_START = "tool_start"
TOOL_END = "tool_end"
TURN_END = "turn_end"
AGENT_END = "agent_end"
AGENT_SETTLED = "agent_settled"
ERROR = "error"
SPECIALIST_EVENT = "specialist_event"

# Ordered lifecycle (informational; used by tests and future emitters).
CANONICAL_LIFECYCLE = (
    AGENT_START,
    TURN_START,
    MESSAGE_START,
    MESSAGE_DELTA,
    MESSAGE_END,
    TOOL_START,
    TOOL_END,
    TURN_END,
    AGENT_END,
    AGENT_SETTLED,
)

CANONICAL_EVENT_TYPES = frozenset(CANONICAL_LIFECYCLE) | {ERROR, SPECIALIST_EVENT}

# Legacy AgentLoop event names -> canonical names.
LEGACY_TO_CANONICAL: dict[str, str] = {
    "assistant_delta": MESSAGE_DELTA,
    "assistant_done": MESSAGE_END,
    "tool_start": TOOL_START,
    "tool_end": TOOL_END,
    "error": ERROR,
    "specialist_event": SPECIALIST_EVENT,
}


def canonical_type(event_type: Any) -> str:
    """Return the canonical name for a (possibly legacy) event type."""
    return LEGACY_TO_CANONICAL.get(event_type, event_type)


def is_canonical(event_type: Any) -> bool:
    """Return True when event_type is one of the canonical event names."""
    return event_type in CANONICAL_EVENT_TYPES


def canonicalize_event(
    event: dict[str, Any],
    *,
    session_id: str | None = None,
    seq: int | None = None,
) -> dict[str, Any]:
    """Return a copy of event with a canonical type and optional identity fields.

    - type is mapped through the legacy -> canonical table.
    - session_id is stamped only when provided and not already present.
    - seq is stamped only when provided (message_delta carries delta order).
    """
    result = dict(event)
    result["type"] = canonical_type(result.get("type"))
    if session_id is not None:
        result.setdefault("session_id", session_id)
    if seq is not None:
        result["seq"] = seq
    return result
