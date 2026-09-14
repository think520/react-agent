"""P1-16: the three specialists must be reachable from the browser too."""

from core.session import Session
from tools.base import TOOL_REGISTRY, ToolResult, execute_tool, register_tool


def test_execute_tool_injects_the_calling_session():
    """The web cannot close over a global "current session" like the REPL does:
    runs are concurrent, so the session has to travel with the call."""
    seen = {}

    def probe(session=None, arg1: str = "") -> ToolResult:
        seen["session"] = session
        return ToolResult(ok=True, content="ok")

    register_tool("probe_session", "probe", {"type": "object", "properties": {}}, probe)
    try:
        session = Session.new("/tmp/project")
        result = execute_tool("probe_session", {"arg1": "x"}, session=session)
        assert result.ok
        assert seen["session"] is session
    finally:
        TOOL_REGISTRY.pop("probe_session", None)


def test_web_runtime_registers_the_delegate_tools(tmp_path):
    """The delegate_* tools were registered only by cli/repl.py, so the browser
    could not use a single specialist."""
    from web.backend.specialists import ensure_specialist_tools

    config = {"specialists": {}}
    try:
        count = ensure_specialist_tools(config)
        assert count >= 1
        for name in ("delegate_doc_reader", "delegate_triage", "delegate_planner"):
            assert name in TOOL_REGISTRY, name

        # idempotent: a second call must not register duplicates
        before = len(TOOL_REGISTRY)
        ensure_specialist_tools(config)
        assert len(TOOL_REGISTRY) == before
    finally:
        for name in ("delegate_doc_reader", "delegate_triage", "delegate_planner"):
            TOOL_REGISTRY.pop(name, None)


def test_the_web_allowlist_lets_them_through():
    from web.backend.routers.chat import _WEB_TOOL_NAMES

    for name in ("delegate_doc_reader", "delegate_triage", "delegate_planner"):
        assert name in _WEB_TOOL_NAMES, name
