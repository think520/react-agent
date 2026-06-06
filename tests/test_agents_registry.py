"""Tests for SpecialistRegistry."""
from __future__ import annotations

import pytest

from agents.registry import SpecialistRegistry, InvocationRecord
from agents.specialists.triage import TriageSpecialist
from agents.specialists.doc_reader import DocReaderSpecialist


def test_register_creates_config():
    reg = SpecialistRegistry()
    cfg = reg.register(TriageSpecialist())
    assert cfg.name == "triage"
    assert reg.get("triage") is not None
    assert reg.get_config("triage") is cfg


def test_register_duplicate_raises():
    reg = SpecialistRegistry()
    reg.register(TriageSpecialist())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(TriageSpecialist())


def test_get_returns_none_for_missing():
    reg = SpecialistRegistry()
    assert reg.get("nonexistent") is None
    assert reg.get_config("nonexistent") is None


def test_list_names():
    reg = SpecialistRegistry()
    reg.register(TriageSpecialist())
    reg.register(DocReaderSpecialist())
    assert sorted(reg.list_names()) == ["doc_reader", "triage"]


def test_list_enabled_filters_disabled():
    reg = SpecialistRegistry()
    from agents.config import SpecialistConfig
    reg.register(TriageSpecialist(), yaml_overrides={"enabled": False})
    reg.register(DocReaderSpecialist())
    enabled = reg.list_enabled()
    assert [n for n, _, _ in enabled] == ["doc_reader"]


def test_yaml_overrides_applied_at_register():
    reg = SpecialistRegistry()
    reg.register(TriageSpecialist(), yaml_overrides={"timeout_seconds": 99})
    cfg = reg.get_config("triage")
    assert cfg.timeout_seconds == 99


def test_record_invocation_stores_deque():
    reg = SpecialistRegistry()
    for i in range(15):
        reg.record_invocation("triage", ok=True, error_type=None,
                              duration_ms=100 + i, content=f"call {i}",
                              model="m")
    records = reg.get_invocation(100)
    # deque(maxlen=10) keeps last 10
    assert len(records) == 10
    assert records[0].content_preview == "call 5"
    assert records[-1].content_preview == "call 14"


def test_record_invocation_truncates_preview():
    reg = SpecialistRegistry()
    long = "x" * 5000
    reg.record_invocation("triage", ok=True, error_type=None,
                          duration_ms=10, content=long, model="m")
    rec = reg.get_invocation(1)[0]
    assert len(rec.content_preview) <= 220
    assert rec.content_preview.endswith("...")


def test_record_invocation_failure_path():
    reg = SpecialistRegistry()
    reg.record_invocation("triage", ok=False, error_type="timeout",
                          duration_ms=30000, content="", model="m")
    rec = reg.get_invocation(1)[0]
    assert rec.ok is False
    assert rec.error_type == "timeout"


def test_register_builtin_specialists_loads_three():
    from agents.registry import register_builtin_specialists
    reg = register_builtin_specialists()
    assert sorted(reg.list_names()) == ["doc_reader", "planner", "triage"]


def test_register_delegate_tools_skips_disabled_specialists():
    """Disabled specialists should not be visible in the parent tool schema."""
    from tools.agents import register_delegate_tools
    from tools.base import TOOL_REGISTRY, TOOL_SCHEMAS

    def clear_delegate_tools():
        for key in list(TOOL_REGISTRY):
            if key.startswith("delegate_"):
                TOOL_REGISTRY.pop(key, None)
        TOOL_SCHEMAS[:] = [
            schema for schema in TOOL_SCHEMAS
            if not schema.get("function", {}).get("name", "").startswith("delegate_")
        ]

    clear_delegate_tools()
    try:
        reg = SpecialistRegistry()
        reg.register(TriageSpecialist(), yaml_overrides={"enabled": False})
        reg.register(DocReaderSpecialist())

        count = register_delegate_tools(reg, get_session=lambda: None, get_app_config=lambda: {})

        delegate_names = {
            schema["function"]["name"]
            for schema in TOOL_SCHEMAS
            if schema.get("function", {}).get("name", "").startswith("delegate_")
        }
        assert count == 1
        assert delegate_names == {"delegate_doc_reader"}
    finally:
        clear_delegate_tools()
