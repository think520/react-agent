"""Tests for mcp_client.catalog — building tool specs from MCPManager."""

from unittest.mock import MagicMock

import pytest

from mcp_client.catalog import (
    build_mcp_tool_specs,
    is_mcp_tool,
    mcp_tool_names,
    reset_mcp_registry,
)
from mcp_client.config import MCPServerConfig
from mcp_client.event_loop import AsyncEventLoop
from mcp_client.manager import MCPManager, ServerState


@pytest.fixture(autouse=True)
def _reset_event_loop():
    AsyncEventLoop.reset()
    reset_mcp_registry()
    yield
    AsyncEventLoop.reset()
    reset_mcp_registry()


def _make_state(name: str, enabled: bool = True) -> ServerState:
    cfg = MCPServerConfig(
        name=name,
        transport="stdio",
        command="fake",
        enabled=enabled,
    )
    return ServerState(config=cfg)


class _FakeTransport:
    def __init__(self, cfg, timeout):
        self.cfg = cfg
        self.next_tools: list[dict] = []

    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def list_tools(self):
        return list(self.next_tools)

    async def call_tool(self, name, arguments):
        return {"content": [{"type": "text", "text": "ok"}], "isError": False}

    @property
    def is_connected(self):
        return True


def _make_manager(server_states: list[tuple[str, list[dict]]]) -> MCPManager:
    """Build an MCPManager with given (server_name, tools) pairs."""
    from mcp_client.config import MCPConfig

    servers_cfg: dict[str, MCPServerConfig] = {}
    states: dict[str, ServerState] = {}
    for name, tools in server_states:
        cfg = MCPServerConfig(name=name, transport="stdio", command="fake")
        servers_cfg[name] = cfg
        state = ServerState(config=cfg)
        state.state = "connected"
        state.tools = tools
        states[name] = state
    mgr = MCPManager(MCPConfig(enabled=True, servers=servers_cfg))
    # Manually overwrite the auto-built states with our pre-populated ones
    mgr._servers = states
    return mgr


def test_build_specs_basic():
    mgr = _make_manager([
        ("github", [
            {"name": "create_issue", "description": "Create an issue", "inputSchema": {"type": "object"}},
            {"name": "list_prs", "description": "List PRs", "inputSchema": {"type": "object"}},
        ]),
    ])
    specs = build_mcp_tool_specs(mgr)
    assert len(specs) == 2
    by_safe = {s["safe_name"]: s for s in specs}
    assert "github__create_issue" in by_safe
    assert "github__list_prs" in by_safe
    assert by_safe["github__create_issue"]["tool_name"] == "create_issue"
    assert by_safe["github__create_issue"]["server"] == "github"
    assert by_safe["github__create_issue"]["description"] == "Create an issue"


def test_build_specs_skips_disabled_servers():
    mgr = _make_manager([
        ("on", [{"name": "x", "description": "", "inputSchema": {}}]),
        ("off", [{"name": "y", "description": "", "inputSchema": {}}]),
    ])
    mgr.get_state("off").config.enabled = False
    specs = build_mcp_tool_specs(mgr)
    safe_names = [s["safe_name"] for s in specs]
    assert "on__x" in safe_names
    assert "off__y" not in safe_names


def test_build_specs_skips_tools_with_no_name():
    mgr = _make_manager([
        ("srv", [
            {"name": "good", "description": "", "inputSchema": {}},
            {"description": "no name", "inputSchema": {}},  # missing name
        ]),
    ])
    specs = build_mcp_tool_specs(mgr)
    assert len(specs) == 1
    assert specs[0]["tool_name"] == "good"


def test_build_specs_default_schema_when_missing():
    mgr = _make_manager([
        ("srv", [{"name": "x", "description": "no schema"}]),
    ])
    specs = build_mcp_tool_specs(mgr)
    assert specs[0]["inputSchema"] == {"type": "object", "properties": {}}


def test_build_specs_collision_against_reserved():
    mgr = _make_manager([
        ("github", [
            {"name": "create_issue", "description": "", "inputSchema": {}},
        ]),
    ])
    reserved = {"github__create_issue"}  # already taken by builtin
    specs = build_mcp_tool_specs(mgr, reserved=reserved)
    assert specs[0]["safe_name"] == "github__create_issue-2"


def test_build_specs_collision_within_mcp():
    """Two servers exposing the same tool name should get -2 suffix."""
    mgr = _make_manager([
        ("github", [{"name": "search", "description": "gh search", "inputSchema": {}}]),
        ("gitlab", [{"name": "search", "description": "gl search", "inputSchema": {}}]),
    ])
    specs = build_mcp_tool_specs(mgr)
    names = [s["safe_name"] for s in specs]
    assert "github__search" in names
    assert "gitlab__search" in names
    assert len(set(names)) == 2  # no duplicates


def test_is_mcp_tool_tracks_registered():
    mgr = _make_manager([
        ("srv", [{"name": "foo", "description": "", "inputSchema": {}}]),
    ])
    build_mcp_tool_specs(mgr)
    assert is_mcp_tool("srv__foo") is True
    assert is_mcp_tool("srv__bar") is False
    assert is_mcp_tool("read_file") is False


def test_mcp_tool_names_returns_set():
    mgr = _make_manager([
        ("a", [{"name": "x", "description": "", "inputSchema": {}}]),
        ("b", [{"name": "y", "description": "", "inputSchema": {}}]),
    ])
    build_mcp_tool_specs(mgr)
    names = mcp_tool_names()
    assert names == {"a__x", "b__y"}


def test_reset_clears_registry():
    mgr = _make_manager([
        ("srv", [{"name": "foo", "description": "", "inputSchema": {}}]),
    ])
    build_mcp_tool_specs(mgr)
    assert is_mcp_tool("srv__foo")
    reset_mcp_registry()
    assert not is_mcp_tool("srv__foo")
