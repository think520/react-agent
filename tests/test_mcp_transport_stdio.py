"""Tests for mcp_client.transport_stdio — stdio transport with SDK mocking."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_client.config import MCPServerConfig
from mcp_client.event_loop import AsyncEventLoop
from mcp_client.transport_stdio import StdioTransport


@pytest.fixture(autouse=True)
def _reset_event_loop():
    AsyncEventLoop.reset()
    yield
    AsyncEventLoop.reset()


def _make_cfg(**overrides) -> MCPServerConfig:
    defaults = dict(
        name="ctx",
        transport="stdio",
        command="uvx",
        args=["ctx-mcp"],
        env={"FOO": "bar"},
        cwd="/tmp",
    )
    defaults.update(overrides)
    return MCPServerConfig(**defaults)


def _patch_sdk(session: MagicMock):
    """Patch stdio_client and ClientSession; yield (outer_stdio, outer_session).

    The outer mocks record call_args; the inner fakes are returned via
    return_value to model the real context-manager chain.
    """
    fake_cm = MagicMock()
    fake_read = MagicMock()
    fake_write = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=(fake_read, fake_write))
    fake_cm.__aexit__ = AsyncMock(return_value=None)

    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)

    outer_stdio = MagicMock(return_value=fake_cm)
    outer_session = MagicMock(return_value=fake_session_cm)

    p1 = patch("mcp_client.transport_stdio.ClientSession", outer_session)
    p2 = patch("mcp_client.transport_stdio.stdio_client", outer_stdio)

    class _CM:
        def __enter__(self):
            p1.__enter__()
            p2.__enter__()
            return (outer_stdio, outer_session)

        def __exit__(self, *a):
            p2.__exit__(*a)
            p1.__exit__(*a)

    return _CM()


def _fake_session_with_tools(tools=None, call_result=None):
    session = MagicMock()
    session.initialize = AsyncMock()
    result = MagicMock()
    tool_mocks = []
    for t in (tools or []):
        m = MagicMock()
        m.name = t["name"]
        m.description = t.get("description", "")
        m.inputSchema = t.get("inputSchema", {})
        tool_mocks.append(m)
    result.tools = tool_mocks
    session.list_tools = AsyncMock(return_value=result)
    if call_result is None:
        call_result = {"content": [{"type": "text", "text": "ok"}], "isError": False}
    call_obj = MagicMock()
    blocks = []
    for b in call_result.get("content", []):
        bm = MagicMock()
        for k, v in b.items():
            setattr(bm, k, v)
        blocks.append(bm)
    call_obj.content = blocks
    call_obj.isError = call_result.get("isError", False)
    session.call_tool = AsyncMock(return_value=call_obj)
    return session


# --- connect ---


def test_connect_passes_command_args_env_cwd():
    cfg = _make_cfg(command="my-cmd", args=["--flag", "value"], env={"K": "V"}, cwd="/work")
    transport = StdioTransport(cfg, timeout=10)
    session = _fake_session_with_tools()

    with _patch_sdk(session) as (outer_stdio, _):
        AsyncEventLoop.get().run_sync(transport.connect())

    params = outer_stdio.call_args.args[0]
    assert params.command == "my-cmd"
    assert params.args == ["--flag", "value"]
    assert params.env == {"K": "V"}
    assert params.cwd == "/work"
    assert transport.is_connected is True


def test_connect_initializes_session():
    cfg = _make_cfg()
    transport = StdioTransport(cfg, timeout=10)
    session = _fake_session_with_tools()

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())

    session.initialize.assert_awaited_once()


def test_connect_missing_command_raises():
    cfg = MCPServerConfig(name="x", transport="stdio", command=None)
    transport = StdioTransport(cfg, timeout=10)
    with pytest.raises(ValueError, match="requires 'command'"):
        AsyncEventLoop.get().run_sync(transport.connect(), timeout=5)


def test_connect_stderr_logger_provided():
    """stdio_client should be called with an errlog parameter (a TextIO-like)."""
    cfg = _make_cfg()
    transport = StdioTransport(cfg, timeout=10)
    session = _fake_session_with_tools()

    with _patch_sdk(session) as (outer_stdio, _):
        AsyncEventLoop.get().run_sync(transport.connect())
        kwargs = outer_stdio.call_args.kwargs
        # errlog is passed as keyword arg
        assert "errlog" in kwargs
        assert hasattr(kwargs["errlog"], "write")


# --- list_tools ---


def test_list_tools_returns_dicts():
    cfg = _make_cfg()
    transport = StdioTransport(cfg, timeout=10)
    session = _fake_session_with_tools([
        {"name": "echo", "description": "echo back", "inputSchema": {"type": "object"}},
    ])

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())
        tools = AsyncEventLoop.get().run_sync(transport.list_tools(), timeout=5)

    assert len(tools) == 1
    assert tools[0]["name"] == "echo"


def test_list_tools_raises_when_not_connected():
    cfg = _make_cfg()
    transport = StdioTransport(cfg, timeout=10)
    with pytest.raises(RuntimeError, match="not connected"):
        AsyncEventLoop.get().run_sync(transport.list_tools(), timeout=5)


# --- call_tool ---


def test_call_tool_returns_result():
    cfg = _make_cfg()
    transport = StdioTransport(cfg, timeout=10)
    session = _fake_session_with_tools([], call_result={
        "content": [{"type": "text", "text": "hello"}],
        "isError": False,
    })

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())
        result = AsyncEventLoop.get().run_sync(
            transport.call_tool("echo", {"msg": "hi"}), timeout=5
        )

    assert result["isError"] is False
    assert result["content"] == [{"type": "text", "text": "hello"}]


def test_call_tool_propagates_iserror():
    cfg = _make_cfg()
    transport = StdioTransport(cfg, timeout=10)
    session = _fake_session_with_tools([], call_result={
        "content": [{"type": "text", "text": "boom"}],
        "isError": True,
    })

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())
        result = AsyncEventLoop.get().run_sync(transport.call_tool("x", {}), timeout=5)

    assert result["isError"] is True


# --- disconnect ---


def test_disconnect_closes_both_contexts():
    cfg = _make_cfg()
    transport = StdioTransport(cfg, timeout=10)
    session = _fake_session_with_tools()

    with _patch_sdk(session) as (outer_stdio, outer_session):
        AsyncEventLoop.get().run_sync(transport.connect())
        AsyncEventLoop.get().run_sync(transport.disconnect(), timeout=5)

        assert transport.is_connected is False
        outer_stdio.return_value.__aexit__.assert_awaited_once()
        outer_session.return_value.__aexit__.assert_awaited_once()


def test_disconnect_when_not_connected_is_noop():
    cfg = _make_cfg()
    transport = StdioTransport(cfg, timeout=10)
    AsyncEventLoop.get().run_sync(transport.disconnect(), timeout=5)
    assert transport.is_connected is False


# --- stderr capture ---


def test_stderr_capture_writes_to_logger(caplog):
    """Lines from the child's stderr should be captured at DEBUG level."""
    import logging
    cfg = _make_cfg()
    transport = StdioTransport(cfg, timeout=10)
    session = _fake_session_with_tools()

    with _patch_sdk(session) as (outer_stdio, _):
        AsyncEventLoop.get().run_sync(transport.connect())
        errlog = outer_stdio.call_args.kwargs["errlog"]
        with caplog.at_level(logging.DEBUG, logger="mcp_client.transport_stdio"):
            errlog.write("first line\nsecond line\n")
        assert any("stderr: first line" in r.message for r in caplog.records)
        assert any("stderr: second line" in r.message for r in caplog.records)
