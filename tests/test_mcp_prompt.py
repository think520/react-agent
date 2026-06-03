"""Tests for mcp_client.prompt — system prompt segment builder."""

from mcp_client.config import MCPServerConfig, MCPConfig
from mcp_client.manager import MCPManager, ServerState
from mcp_client.prompt import build_mcp_status_prompt


def _make_manager(enabled: bool = True, server_states: list[tuple[str, str, int]] | None = None) -> MCPManager:
    """server_states: list of (name, state, n_tools)."""
    servers_cfg: dict[str, MCPServerConfig] = {}
    states: dict[str, ServerState] = {}
    for name, st, n in (server_states or []):
        cfg = MCPServerConfig(name=name, transport="stdio", command="fake")
        servers_cfg[name] = cfg
        state = ServerState(config=cfg)
        state.state = st
        state.tools = [{"name": f"tool{i}"} for i in range(n)] if n else []
        states[name] = state
    cfg = MCPConfig(enabled=enabled, servers=servers_cfg)
    mgr = MCPManager(cfg)
    mgr._servers = states
    return mgr


def test_returns_empty_when_no_manager():
    assert build_mcp_status_prompt(None) == ""


def test_returns_empty_when_disabled():
    mgr = _make_manager(enabled=False, server_states=[("github", "connected", 3)])
    assert build_mcp_status_prompt(mgr) == ""


def test_connected_servers_listed():
    mgr = _make_manager(server_states=[("github", "connected", 5)])
    out = build_mcp_status_prompt(mgr)
    assert "github" in out
    assert "5 tools" in out
    assert "github__<tool_name>" in out


def test_error_state_shown():
    mgr = _make_manager(server_states=[("github", "error", 0)])
    mgr.get_state("github").last_error = "Connection refused"
    out = build_mcp_status_prompt(mgr)
    assert "github" in out
    assert "unavailable" in out
    assert "Connection refused" in out


def test_long_error_truncated():
    mgr = _make_manager(server_states=[("github", "error", 0)])
    mgr.get_state("github").last_error = "x" * 200
    out = build_mcp_status_prompt(mgr)
    # Truncation: 80 chars total (77 x's + "...")
    assert "x" * 77 in out
    assert "..." in out
    # Full 200-char string should NOT be present
    assert "x" * 200 not in out


def test_disconnected_servers_show_status():
    mgr = _make_manager(server_states=[("github", "disconnected", 0)])
    out = build_mcp_status_prompt(mgr)
    assert "github" in out
    assert "disconnected" in out


def test_connected_with_zero_tools():
    """A connected server that exposes no tools gets a special line."""
    mgr = _make_manager(server_states=[("github", "connected", 0)])
    out = build_mcp_status_prompt(mgr)
    assert "github" in out
    assert "no tools" in out


def test_disabled_servers_excluded():
    mgr = _make_manager(server_states=[
        ("on", "connected", 3),
        ("off", "connected", 3),
    ])
    mgr.get_state("off").config.enabled = False
    out = build_mcp_status_prompt(mgr)
    assert "on" in out
    assert "off" not in out


def test_multiple_servers_all_listed():
    mgr = _make_manager(server_states=[
        ("github", "connected", 3),
        ("context7", "connected", 5),
        ("broken", "error", 0),
    ])
    mgr.get_state("broken").last_error = "timeout"
    out = build_mcp_status_prompt(mgr)
    assert "github" in out
    assert "context7" in out
    assert "broken" in out
    assert "timeout" in out


def test_all_disconnected_adds_hint():
    mgr = _make_manager(server_states=[("github", "disconnected", 0)])
    out = build_mcp_status_prompt(mgr)
    assert "not yet visible" in out
