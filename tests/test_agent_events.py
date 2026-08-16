"""Unit tests for core.agent_events (AG-0.2)."""

from core.agent_events import (
    AGENT_SETTLED,
    MESSAGE_DELTA,
    MESSAGE_END,
    MESSAGE_START,
    TOOL_END,
    TOOL_START,
    TURN_END,
    canonical_type,
    canonicalize_event,
    is_canonical,
)


def test_legacy_assistant_delta_maps_to_message_delta():
    assert canonical_type("assistant_delta") == MESSAGE_DELTA


def test_legacy_assistant_done_maps_to_message_end():
    assert canonical_type("assistant_done") == MESSAGE_END


def test_tool_events_are_already_canonical():
    assert canonical_type("tool_start") == TOOL_START
    assert canonical_type("tool_end") == TOOL_END


def test_unknown_type_passes_through():
    assert canonical_type("custom_event") == "custom_event"


def test_canonicalize_rewrites_type_and_preserves_fields():
    event = {"type": "assistant_delta", "content": "hello"}
    out = canonicalize_event(event)
    assert out["type"] == MESSAGE_DELTA
    assert out["content"] == "hello"


def test_canonicalize_stamps_session_id_when_provided():
    out = canonicalize_event({"type": "tool_start"}, session_id="s1")
    assert out["session_id"] == "s1"


def test_canonicalize_does_not_overwrite_existing_session_id():
    out = canonicalize_event({"type": "tool_start", "session_id": "s2"}, session_id="s1")
    assert out["session_id"] == "s2"


def test_canonicalize_stamps_seq_when_provided():
    out = canonicalize_event({"type": "assistant_delta", "content": "a"}, seq=7)
    assert out["seq"] == 7


def test_is_canonical():
    assert is_canonical(MESSAGE_DELTA)
    assert is_canonical(AGENT_SETTLED)
    assert not is_canonical("assistant_delta")


def test_lifecycle_contains_core_types():
    for name in (MESSAGE_START, MESSAGE_END, TURN_END, AGENT_SETTLED):
        assert is_canonical(name)
