"""P0-9 / P1-15: the hook registry gets its first real production consumers."""

from core.hooks import AFTER_TOOL, BEFORE_TOOL, ToolGate, clear_hooks, dispatch, registered
from tools.base import ToolResult


def test_a_huge_tool_result_is_bounded_keeping_head_and_tail():
    """P0-9: one rag_search / list_dir result could dump tens of thousands of
    characters straight into the context with no limit anywhere in the loop."""
    from core.builtin_hooks import cap_tool_result

    result = ToolResult(ok=True, content="开" * 60000)
    replacement = cap_tool_result(tool_name="rag_search", args={}, result=result, session=None)

    assert replacement is not None
    assert replacement.ok is True
    assert replacement.content.startswith("开")
    assert replacement.content.endswith("开")
    assert "省略" in replacement.content


def test_small_results_are_left_alone():
    from core.builtin_hooks import cap_tool_result

    result = ToolResult(ok=True, content="短")
    assert cap_tool_result(tool_name="read_file", args={}, result=result, session=None) is None


def test_error_results_are_never_truncated():
    """A failed tool result is the debugging trail and stays whole."""
    from core.builtin_hooks import cap_tool_result

    result = ToolResult(ok=False, content="E" * 100000)
    assert cap_tool_result(tool_name="read_file", args={}, result=result, session=None) is None


def test_dispatch_hands_the_bounded_result_back_to_the_loop():
    from core.builtin_hooks import MAX_TOOL_RESULT_CHARS, register_builtin_hooks

    clear_hooks()
    register_builtin_hooks()
    try:
        result = ToolResult(ok=True, content="x" * 90000)
        bounded = result
        for replacement in dispatch(
            AFTER_TOOL, tool_name="rag_search", args={}, result=result, session=None
        ):
            if isinstance(replacement, ToolResult):
                bounded = replacement
        assert len(bounded.content) <= MAX_TOOL_RESULT_CHARS + 400
    finally:
        clear_hooks()


def test_allowlist_gate_blocks_tools_outside_the_run():
    from core.builtin_hooks import allowlist_gate

    gate = allowlist_gate(tool_name="write_file", allowed={"rag_search"})
    assert isinstance(gate, ToolGate)
    assert gate.allow is False
    assert "unavailable in this runtime" in gate.reason
    assert allowlist_gate(tool_name="rag_search", allowed={"rag_search"}) is None
    assert allowlist_gate(tool_name="anything", allowed=None) is None


def test_registering_twice_does_not_duplicate_hooks():
    from core.builtin_hooks import register_builtin_hooks

    clear_hooks()
    try:
        register_builtin_hooks()
        register_builtin_hooks()
        assert len(registered(AFTER_TOOL)) == 1
        assert len(registered(BEFORE_TOOL)) == 1
    finally:
        clear_hooks()


def test_constructing_a_loop_registers_the_builtin_hooks(tmp_path):
    """P1-15: the guard that stops the registry from silently going dead again."""
    from core.agent_loop import AgentLoop
    from core.session import Session

    clear_hooks()
    try:
        AgentLoop(llm_provider=None, session=Session.new(str(tmp_path)), tools_schema=[])
        after = {getattr(fn, "__name__", "") for fn in registered(AFTER_TOOL)}
        before = {getattr(fn, "__name__", "") for fn in registered(BEFORE_TOOL)}
        assert "cap_tool_result" in after
        assert "allowlist_gate" in before
    finally:
        clear_hooks()
