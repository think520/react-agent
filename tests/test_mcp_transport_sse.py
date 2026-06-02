"""Tests for mcp_client.transport_sse — SSE transport with SDK mocking."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_client.config import MCPServerConfig
from mcp_client.event_loop import AsyncEventLoop
from mcp_client.transport_sse import SseTransport


@pytest.fixture(autouse=True)
def _reset_event_loop():
    AsyncEventLoop.reset()
    yield
    AsyncEventLoop.reset()


def _make_cfg(**overrides) -> MCPServerConfig:
    defaults = dict(
        name="legacy",
        transport="sse",
        url="https://mcp.example.com/sse",
    )
    defaults.update(overrides)
    return MCPServerConfig(**defaults)


def _patch_sdk(session: MagicMock):
    """Patch sse_client and ClientSession; yield (outer_sse, outer_session)."""
    fake_cm = MagicMock()
    fake_read = MagicMock()
    fake_write = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=(fake_read, fake_write))
    fake_cm.__aexit__ = AsyncMock(return_value=None)

    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)

    outer_sse = MagicMock(return_value=fake_cm)
    outer_session = MagicMock(return_value=fake_session_cm)

    p1 = patch("mcp_client.transport_sse.ClientSession", outer_session)
    p2 = patch("mcp_client.transport_sse.sse_client", outer_sse)

    class _CM:
        def __enter__(self):
            p1.__enter__()
            p2.__enter__()
            return (outer_sse, outer_session)

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


def test_connect_passes_url_and_headers():
    cfg = _make_cfg(url="https://x.example.com/sse", headers={"Authorization": "Bearer t"})
    transport = SseTransport(cfg, timeout=10)
    session = _fake_session_with_tools()

    with _patch_sdk(session) as (outer_sse, _):
        AsyncEventLoop.get().run_sync(transport.connect())

    kwargs = outer_sse.call_args.kwargs
    assert kwargs["url"] == "https://x.example.com/sse"
    assert kwargs["headers"] == {"Authorization": "Bearer t"}
    assert kwargs["timeout"] == 10.0
    assert transport.is_connected is True


def test_connect_none_headers():
    cfg = _make_cfg(headers={})
    transport = SseTransport(cfg, timeout=10)
    session = _fake_session_with_tools()

    with _patch_sdk(session) as (outer_sse, _):
        AsyncEventLoop.get().run_sync(transport.connect())

    kwargs = outer_sse.call_args.kwargs
    assert kwargs["headers"] is None


def test_connect_initializes_session():
    cfg = _make_cfg()
    transport = SseTransport(cfg, timeout=10)
    session = _fake_session_with_tools()

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())

    session.initialize.assert_awaited_once()


def test_connect_missing_url_raises():
    cfg = MCPServerConfig(name="x", transport="sse", url=None)
    transport = SseTransport(cfg, timeout=10)
    with pytest.raises(ValueError, match="requires 'url'"):
        AsyncEventLoop.get().run_sync(transport.connect(), timeout=5)


def test_connect_typeerror_falls_back_to_positional():
    """If sse_client rejects the kwargs form, fall back to positional."""
    cfg = _make_cfg()
    transport = SseTransport(cfg, timeout=10)
    session = _fake_session_with_tools()

    # First call raises TypeError, second succeeds
    fake_cm = MagicMock()
    fake_read = MagicMock()
    fake_write = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=(fake_read, fake_write))
    fake_cm.__aexit__ = AsyncMock(return_value=None)

    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)

    outer_sse = MagicMock(side_effect=[TypeError("bad kwargs"), fake_cm])
    outer_session = MagicMock(return_value=fake_session_cm)

    with patch("mcp_client.transport_sse.ClientSession", outer_session), \
         patch("mcp_client.transport_sse.sse_client", outer_sse):
        AsyncEventLoop.get().run_sync(transport.connect())

    assert transport.is_connected is True
    assert outer_sse.call_count == 2


# --- list_tools ---


def test_list_tools_returns_dicts():
    cfg = _make_cfg()
    transport = SseTransport(cfg, timeout=10)
    session = _fake_session_with_tools([
        {"name": "tool_a", "description": "first", "inputSchema": {"type": "object"}},
        {"name": "tool_b", "description": "second", "inputSchema": {}},
    ])

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())
        tools = AsyncEventLoop.get().run_sync(transport.list_tools(), timeout=5)

    assert len(tools) == 2
    assert tools[0]["name"] == "tool_a"
    assert tools[1]["name"] == "tool_b"


def test_list_tools_raises_when_not_connected():
    cfg = _make_cfg()
    transport = SseTransport(cfg, timeout=10)
    with pytest.raises(RuntimeError, match="not connected"):
        AsyncEventLoop.get().run_sync(transport.list_tools(), timeout=5)


# --- call_tool ---


def test_call_tool_returns_result():
    cfg = _make_cfg()
    transport = SseTransport(cfg, timeout=10)
    session = _fake_session_with_tools([], call_result={
        "content": [{"type": "text", "text": "SSE result"}],
        "isError": False,
    })

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())
        result = AsyncEventLoop.get().run_sync(
            transport.call_tool("tool_a", {"x": 1}), timeout=5
        )

    assert result["isError"] is False
    assert result["content"] == [{"type": "text", "text": "SSE result"}]


def test_call_tool_image_block():
    cfg = _make_cfg()
    transport = SseTransport(cfg, timeout=10)

    block = MagicMock()
    block.type = "image"
    block.data = "imgdata"
    block.mimeType = "image/jpeg"

    call_obj = MagicMock(content=[block], isError=False)
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    session.call_tool = AsyncMock(return_value=call_obj)

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())
        result = AsyncEventLoop.get().run_sync(transport.call_tool("x", {}), timeout=5)

    assert result["content"] == [{"type": "image", "data": "imgdata", "mimeType": "image/jpeg"}]


# --- disconnect ---


def test_disconnect_closes_both_contexts():
    cfg = _make_cfg()
    transport = SseTransport(cfg, timeout=10)
    session = _fake_session_with_tools()

    with _patch_sdk(session) as (outer_sse, outer_session):
        AsyncEventLoop.get().run_sync(transport.connect())
        AsyncEventLoop.get().run_sync(transport.disconnect(), timeout=5)

        assert transport.is_connected is False
        outer_sse.return_value.__aexit__.assert_awaited_once()
        outer_session.return_value.__aexit__.assert_awaited_once()


def test_disconnect_when_not_connected_is_noop():
    cfg = _make_cfg()
    transport = SseTransport(cfg, timeout=10)
    AsyncEventLoop.get().run_sync(transport.disconnect(), timeout=5)
    assert transport.is_connected is False
