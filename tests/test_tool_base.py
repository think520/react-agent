from core.session import Session
from tools.base import register_tool, get_tools_schema, execute_tool, ToolResult, TOOL_REGISTRY, TOOL_SCHEMAS


def dummy_tool(arg1: str) -> str:
    return f"result: {arg1}"


def dummy_tool_with_cwd(arg1: str, cwd: str = ".") -> str:
    return f"{cwd}:{arg1}"


def dummy_scoped_tool(document_ids=None, preferred_document_ids=None) -> str:
    return f"strict={document_ids};preferred={preferred_document_ids}"


def restore_registry(snapshot_registry, snapshot_schemas):
    TOOL_REGISTRY.clear()
    TOOL_REGISTRY.update(snapshot_registry)
    TOOL_SCHEMAS[:] = snapshot_schemas


def test_register_tool_updates_existing_schema():
    snapshot_registry = TOOL_REGISTRY.copy()
    snapshot_schemas = list(TOOL_SCHEMAS)
    schema = {
        "type": "object",
        "properties": {
            "arg1": {"type": "string", "description": "test arg"}
        },
        "required": ["arg1"]
    }

    try:
        register_tool("dummy", "A dummy tool", schema, dummy_tool)
        register_tool("dummy", "Updated dummy tool", schema, dummy_tool)

        occurrences = [s for s in get_tools_schema() if s["function"]["name"] == "dummy"]
        assert len(occurrences) == 1
        assert occurrences[0]["function"]["description"] == "Updated dummy tool"
    finally:
        restore_registry(snapshot_registry, snapshot_schemas)


def test_execute_tool():
    snapshot_registry = TOOL_REGISTRY.copy()
    snapshot_schemas = list(TOOL_SCHEMAS)
    try:
        register_tool("dummy", "A dummy tool", {"type": "object", "properties": {}}, dummy_tool)
        result = execute_tool("dummy", {"arg1": "test"})
        assert isinstance(result, ToolResult)
        assert result.ok
        assert result.content == "result: test"
    finally:
        restore_registry(snapshot_registry, snapshot_schemas)


def test_execute_tool_injects_session_cwd():
    snapshot_registry = TOOL_REGISTRY.copy()
    snapshot_schemas = list(TOOL_SCHEMAS)
    try:
        register_tool("dummy_cwd", "A dummy cwd tool", {"type": "object", "properties": {}}, dummy_tool_with_cwd)
        session = Session.new("/tmp/project")
        result = execute_tool("dummy_cwd", {"arg1": "test"}, session=session)
        assert isinstance(result, ToolResult)
        assert result.ok
        assert result.content == "/tmp/project:test"
    finally:
        restore_registry(snapshot_registry, snapshot_schemas)


def test_execute_tool_enforces_session_retrieval_scope():
    snapshot_registry = TOOL_REGISTRY.copy()
    snapshot_schemas = list(TOOL_SCHEMAS)
    try:
        register_tool("dummy_scope", "A scoped tool", {"type": "object", "properties": {}}, dummy_scoped_tool)
        session = Session.new("/tmp/project")
        session.active_document_ids = ["strict-doc"]
        session.preferred_document_ids = ["preferred-doc"]

        result = execute_tool(
            "dummy_scope",
            {"document_ids": ["model-doc"], "preferred_document_ids": ["model-preferred"]},
            session=session,
        )

        assert result.content == "strict=['strict-doc'];preferred=['preferred-doc']"
    finally:
        restore_registry(snapshot_registry, snapshot_schemas)


def test_execute_unknown_tool():
    result = execute_tool("unknown_tool", {})
    assert isinstance(result, ToolResult)
    assert not result.ok
    assert "unknown tool" in result.content.lower()


def test_tool_result_dataclass():
    r = ToolResult(ok=True, content="hello", data={"key": "value"})
    assert r.ok
    assert r.content == "hello"
    assert r.data["key"] == "value"


def test_tool_result_default_data():
    r = ToolResult(ok=False, content="error")
    assert r.data == {}
