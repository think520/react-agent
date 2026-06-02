"""Tests for mcp_client.transport_http — streamable_http transport.

Strategy: mock the official mcp SDK (`streamablehttp_client` context
manager and `ClientSession`) so the transport can be exercised without
a real HTTP server.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_client.config import MCPServerConfig
from mcp_client.event_loop import AsyncEventLoop
from mcp_client.transport_http import StreamableHttpTransport


@pytest.fixture(autouse=True)
def _reset_event_loop():
    AsyncEventLoop.reset()
    yield
    AsyncEventLoop.reset()


def _make_cfg(**overrides) -> MCPServerConfig:
    defaults = dict(
        name="amap-maps",
        transport="streamable_http",
        url="https://mcp.example.com/mcp",
    )
    defaults.update(overrides)
    return MCPServerConfig(**defaults)


class _FakeContentBlock:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _fake_session_with_tools(tools: list[dict], call_result: dict | None = None):
    session = MagicMock()
    session.initialize = AsyncMock()
    result = MagicMock()
    tool_mocks = []
    for t in tools:
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
    # Content blocks must be objects with .text/.data attributes, not dicts
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


def _patch_sdk(session: MagicMock):
    """Return a context manager that patches the SDK names with mocks.

    Yields (streamable_client_mock, session_context_manager_mock) —
    these are the OUTER MagicMocks that record call_args, not the
    return-value fakes.
    """
    fake_cm = MagicMock()
    fake_read = MagicMock()
    fake_write = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=(fake_read, fake_write, lambda: None))
    fake_cm.__aexit__ = AsyncMock(return_value=None)

    fake_session_cm = MagicMock()
    fake_session_cm.__aenter__ = AsyncMock(return_value=session)
    fake_session_cm.__aexit__ = AsyncMock(return_value=None)

    # Outer mocks (these record call_args)
    outer_streamable = MagicMock(return_value=fake_cm)
    outer_session = MagicMock(return_value=fake_session_cm)

    p1 = patch("mcp_client.transport_http.ClientSession", outer_session)
    p2 = patch("mcp_client.transport_http.streamablehttp_client", outer_streamable)

    class _CombinedCM:
        def __enter__(self):
            p1.__enter__()
            p2.__enter__()
            return (outer_streamable, outer_session)

        def __exit__(self, *a):
            p2.__exit__(*a)
            p1.__exit__(*a)

    return _CombinedCM()


def test_connect_initializes_session():
    cfg = _make_cfg()
    transport = StreamableHttpTransport(cfg, timeout=10)
    session = _fake_session_with_tools([])

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())

    assert transport.is_connected is True
    session.initialize.assert_awaited_once()


def test_list_tools_returns_dicts():
    cfg = _make_cfg()
    transport = StreamableHttpTransport(cfg, timeout=10)
    session = _fake_session_with_tools([
        {"name": "maps_search", "description": "search a place", "inputSchema": {"type": "object"}},
        {"name": "maps_geocode", "description": "geocode an address", "inputSchema": {"type": "object"}},
    ])

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())
        tools = AsyncEventLoop.get().run_sync(transport.list_tools(), timeout=5)
        assert len(tools) == 2
        assert tools[0]["name"] == "maps_search"
        assert tools[0]["description"] == "search a place"
        assert tools[1]["name"] == "maps_geocode"


def test_list_tools_raises_when_not_connected():
    cfg = _make_cfg()
    transport = StreamableHttpTransport(cfg, timeout=10)
    with pytest.raises(RuntimeError, match="not connected"):
        AsyncEventLoop.get().run_sync(transport.list_tools(), timeout=5)


def test_call_tool_raises_when_not_connected():
    cfg = _make_cfg()
    transport = StreamableHttpTransport(cfg, timeout=10)
    with pytest.raises(RuntimeError, match="not connected"):
        AsyncEventLoop.get().run_sync(transport.call_tool("x", {}), timeout=5)


def test_call_tool_returns_dict():
    cfg = _make_cfg()
    transport = StreamableHttpTransport(cfg, timeout=10)
    call_result = {
        "content": [
            {"type": "text", "text": "Beijing"},
            {"type": "text", "text": "Shanghai"},
        ],
        "isError": False,
    }
    session = _fake_session_with_tools([], call_result=call_result)

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())
        result = AsyncEventLoop.get().run_sync(
            transport.call_tool("maps_search", {"q": "capital"}), timeout=5
        )

    assert result["isError"] is False
    assert result["content"] == [
        {"type": "text", "text": "Beijing"},
        {"type": "text", "text": "Shanghai"},
    ]


def test_call_tool_iserror_propagates():
    cfg = _make_cfg()
    transport = StreamableHttpTransport(cfg, timeout=10)
    call_result = {
        "content": [{"type": "text", "text": "no such place"}],
        "isError": True,
    }
    session = _fake_session_with_tools([], call_result=call_result)

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())
        result = AsyncEventLoop.get().run_sync(
            transport.call_tool("maps_search", {}), timeout=5
        )

    assert result["isError"] is True


def test_call_tool_converts_text_content_block():
    """SDK returns a TextContent object, transport must dict-ify it."""
    cfg = _make_cfg()
    transport = StreamableHttpTransport(cfg, timeout=10)

    block = _FakeContentBlock(type="text", text="hello world")
    call_obj = MagicMock(content=[block], isError=False)
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    session.call_tool = AsyncMock(return_value=call_obj)

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())
        result = AsyncEventLoop.get().run_sync(transport.call_tool("x", {}), timeout=5)

    assert result["content"] == [{"type": "text", "text": "hello world"}]


def test_call_tool_converts_image_content_block():
    cfg = _make_cfg()
    transport = StreamableHttpTransport(cfg, timeout=10)

    block = _FakeContentBlock(type="image", data="base64data", mimeType="image/png")
    call_obj = MagicMock(content=[block], isError=False)
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    session.call_tool = AsyncMock(return_value=call_obj)

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())
        result = AsyncEventLoop.get().run_sync(transport.call_tool("x", {}), timeout=5)

    assert result["content"] == [
        {"type": "image", "data": "base64data", "mimeType": "image/png"}
    ]


def test_call_tool_handles_unknown_block():
    cfg = _make_cfg()
    transport = StreamableHttpTransport(cfg, timeout=10)

    class WeirdBlock:
        def __str__(self):
            return "weird block"

    block = WeirdBlock()
    call_obj = MagicMock(content=[block], isError=False)
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    session.call_tool = AsyncMock(return_value=call_obj)

    with _patch_sdk(session):
        AsyncEventLoop.get().run_sync(transport.connect())
        result = AsyncEventLoop.get().run_sync(transport.call_tool("x", {}), timeout=5)

    # Falls back to text representation
    assert result["content"][0]["type"] == "text"
    assert "weird block" in result["content"][0]["text"]


def test_disconnect_closes_both_contexts():
    cfg = _make_cfg()
    transport = StreamableHttpTransport(cfg, timeout=10)
    session = _fake_session_with_tools([])

    with _patch_sdk(session) as (outer_streamable, outer_session):
        AsyncEventLoop.get().run_sync(transport.connect())
        AsyncEventLoop.get().run_sync(transport.disconnect(), timeout=5)

        assert transport.is_connected is False
        outer_streamable.return_value.__aexit__.assert_awaited_once()
        outer_session.return_value.__aexit__.assert_awaited_once()


def test_disconnect_when_not_connected_is_noop():
    cfg = _make_cfg()
    transport = StreamableHttpTransport(cfg, timeout=10)
    AsyncEventLoop.get().run_sync(transport.disconnect(), timeout=5)
    assert transport.is_connected is False


def test_headers_passed_through():
    cfg = _make_cfg(headers={"Authorization": "Bearer secret"})
    transport = StreamableHttpTransport(cfg, timeout=10)
    session = _fake_session_with_tools([])

    with _patch_sdk(session) as (cm, _):
        AsyncEventLoop.get().run_sync(transport.connect())
        kwargs = cm.call_args.kwargs
        assert kwargs["headers"] == {"Authorization": "Bearer secret"}


def test_none_headers_passed_as_none():
    cfg = _make_cfg(headers={})
    transport = StreamableHttpTransport(cfg, timeout=10)
    session = _fake_session_with_tools([])

    with _patch_sdk(session) as (cm, _):
        AsyncEventLoop.get().run_sync(transport.connect())
        kwargs = cm.call_args.kwargs
        assert kwargs["headers"] is None


def test_url_passed_through():
    cfg = _make_cfg(url="https://my-server.example.com/stream")
    transport = StreamableHttpTransport(cfg, timeout=10)
    session = _fake_session_with_tools([])

    with _patch_sdk(session) as (cm, _):
        AsyncEventLoop.get().run_sync(transport.connect())
        kwargs = cm.call_args.kwargs
        assert kwargs["url"] == "https://my-server.example.com/stream"


def test_timeout_passed_through():
    cfg = _make_cfg()
    transport = StreamableHttpTransport(cfg, timeout=42)
    session = _fake_session_with_tools([])

    with _patch_sdk(session) as (cm, _):
        AsyncEventLoop.get().run_sync(transport.connect())
        kwargs = cm.call_args.kwargs
        assert kwargs["timeout"] == 42.0
