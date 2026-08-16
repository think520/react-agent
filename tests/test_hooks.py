"""Unit tests for core.hooks (AG-2.1)."""

import pytest

from core.hooks import (
    AFTER_TOOL,
    AFTER_TURN,
    BEFORE_TOOL,
    BEFORE_TURN,
    ToolGate,
    allow,
    block,
    before_tool_gates,
    before_turn_results,
    clear_hooks,
    dispatch,
    register_hook,
    registered,
)


@pytest.fixture(autouse=True)
def _clean_hooks():
    clear_hooks()
    yield
    clear_hooks()


def test_register_and_dispatch_in_order():
    order = []
    register_hook(BEFORE_TURN, lambda **kw: order.append("a"))
    register_hook(BEFORE_TURN, lambda **kw: order.append("b"))
    dispatch(BEFORE_TURN)
    assert order == ["a", "b"]


def test_dispatch_collects_non_none_results():
    register_hook(BEFORE_TURN, lambda **kw: "injected")
    register_hook(BEFORE_TURN, lambda **kw: None)
    assert before_turn_results() == ["injected"]


def test_hook_exception_does_not_break_dispatch():
    seen = []
    def bad(**kw):
        raise RuntimeError("boom")
    register_hook(BEFORE_TOOL, bad)
    register_hook(BEFORE_TOOL, lambda **kw: seen.append("ok"))
    dispatch(BEFORE_TOOL)
    assert seen == ["ok"]


def test_before_tool_gates_filter_non_gate_results():
    register_hook(BEFORE_TOOL, lambda **kw: allow())
    register_hook(BEFORE_TOOL, lambda **kw: block("denied"))
    register_hook(BEFORE_TOOL, lambda **kw: "not a gate")
    gates = before_tool_gates()
    assert gates == [ToolGate(True), ToolGate(False, "denied")]


def test_block_helper_sets_reason_and_terminate():
    gate = block("denied", terminate=True)
    assert gate.allow is False
    assert gate.reason == "denied"
    assert gate.terminate is True


def test_register_unknown_event_raises():
    with pytest.raises(ValueError):
        register_hook("bogus", lambda **kw: None)


def test_clear_hooks_single_event():
    register_hook(BEFORE_TOOL, lambda **kw: None)
    register_hook(AFTER_TOOL, lambda **kw: None)
    clear_hooks(BEFORE_TOOL)
    assert registered(BEFORE_TOOL) == []
    assert len(registered(AFTER_TOOL)) == 1


def test_clear_hooks_all():
    register_hook(BEFORE_TOOL, lambda **kw: None)
    register_hook(AFTER_TURN, lambda **kw: None)
    clear_hooks()
    assert registered(BEFORE_TOOL) == []
    assert registered(AFTER_TURN) == []


def test_after_tool_hook_can_return_replacement():
    register_hook(AFTER_TOOL, lambda **kw: {"sanitized": True})
    results = dispatch(AFTER_TOOL)
    assert results == [{"sanitized": True}]
