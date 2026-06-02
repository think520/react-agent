"""Tests for mcp_client.tool_wrapper — wrapping MCP tools as Bobodan ToolResults."""

from unittest.mock import MagicMock

import pytest

from mcp_client.event_loop import AsyncEventLoop
from mcp_client.tool_wrapper import _format_content, make_mcp_tool_func


@pytest.fixture(autouse=True)
def _reset_event_loop():
    AsyncEventLoop.reset()
    yield
    AsyncEventLoop.reset()


# --- _format_content ---


def test_format_content_text_blocks():
    blocks = [
        {"type": "text", "text": "hello"},
        {"type": "text", "text": "world"},
    ]
    assert _format_content(blocks) == "hello\nworld"


def test_format_content_image_block():
    blocks = [{"type": "image", "mimeType": "image/png", "data": "x"}]
    out = _format_content(blocks)
    assert "image" in out
    assert "image/png" in out


def test_format_content_resource_block():
    blocks = [{"type": "resource", "resource": "file:///x.md"}]
    out = _format_content(blocks)
    assert "resource" in out
    assert "file:///x.md" in out


def test_format_content_empty():
    assert _format_content([]) == "(no content)"


def test_format_content_none():
    assert _format_content(None) == "(no content)"


def test_format_content_mixed_types():
    blocks = [
        {"type": "text", "text": "answer:"},
        {"type": "image", "mimeType": "image/png", "data": "x"},
    ]
    out = _format_content(blocks)
    assert "answer:" in out
    assert "[image:" in out


# --- make_mcp_tool_func ---


def _make_mgr(return_value: dict):
    mgr = MagicMock()
    mgr.call.return_value = return_value
    return mgr


def test_wrapper_returns_tool_result_on_success():
    mgr = _make_mgr({
        "content": [{"type": "text", "text": "Beijing"}],
        "isError": False,
    })
    func = make_mcp_tool_func("amap", "geocode", mgr)
    result = func(keywords="北京")
    assert result.ok is True
    assert result.content == "Beijing"
    assert result.data["server"] == "amap"
    assert result.data["tool"] == "geocode"
    mgr.call.assert_called_once_with("amap", "geocode", {"keywords": "北京"})


def test_wrapper_returns_error_result():
    mgr = _make_mgr({
        "content": [{"type": "text", "text": "API key invalid"}],
        "isError": True,
    })
    func = make_mcp_tool_func("amap", "x", mgr)
    result = func()
    assert result.ok is False
    assert "API key invalid" in result.content


def test_wrapper_handles_empty_content():
    mgr = _make_mgr({"content": [], "isError": True})
    func = make_mcp_tool_func("amap", "x", mgr)
    result = func()
    assert result.ok is False
    assert "returned an error" in result.content


def test_wrapper_strips_none_kwargs():
    mgr = _make_mgr({"content": [], "isError": False})
    func = make_mcp_tool_func("amap", "x", mgr)
    func(a=1, b=None, c="hello")
    # None values should be filtered out
    mgr.call.assert_called_once_with("amap", "x", {"a": 1, "c": "hello"})


def test_wrapper_handles_call_exception():
    mgr = MagicMock()
    mgr.call.side_effect = RuntimeError("network down")
    func = make_mcp_tool_func("amap", "x", mgr)
    result = func()
    assert result.ok is False
    assert "crashed" in result.content
    assert "RuntimeError" in result.content
    assert "network down" in result.content


def test_wrapper_preserves_raw_data():
    raw = {
        "content": [{"type": "text", "text": "ok"}],
        "isError": False,
        "_meta": {"some": "thing"},
    }
    mgr = _make_mgr(raw)
    func = make_mcp_tool_func("amap", "x", mgr)
    result = func()
    assert result.data["raw"] is raw


def test_wrapper_function_name():
    mgr = _make_mgr({"content": [], "isError": False})
    func = make_mcp_tool_func("amap-maps", "geocode_address", mgr)
    assert func.__name__ == "mcp_amap-maps_geocode_address"


def test_wrapper_handles_text_and_image_mixed():
    raw = {
        "content": [
            {"type": "text", "text": "result: "},
            {"type": "image", "mimeType": "image/jpeg", "data": "base64data"},
        ],
        "isError": False,
    }
    mgr = _make_mgr(raw)
    func = make_mcp_tool_func("srv", "x", mgr)
    result = func()
    assert "result:" in result.content
    assert "[image:" in result.content
