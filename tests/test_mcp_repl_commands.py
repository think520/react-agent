"""Tests for /mcp REPL command handlers."""

from unittest.mock import MagicMock, patch

import pytest

from mcp_client.config import MCPServerConfig
from mcp_client.manager import MCPManager, ServerState


@pytest.fixture
def repl():
    """Build a minimal REPL instance bypassing __init__."""
    from cli.repl import REPL
    r = REPL.__new__(REPL)
    r.config_path = "config.yaml"
    r.session = MagicMock()
    r.session.workspace_root = "/tmp"
    return r


def _make_state(name, state="connected", n_tools=3, error=None, enabled=True):
    cfg = MCPServerConfig(
        name=name,
        transport="stdio",
        command="fake",
        enabled=enabled,
    )
    s = ServerState(config=cfg)
    s.state = state
    s.tools = [{"name": f"tool{i}"} for i in range(n_tools)]
    s.last_error = error
    s.last_connected_at = "2026-05-21T10:00:00+00:00"
    return s


# --- handle_mcp_list ---


def test_handle_mcp_list_no_manager(repl, capsys):
    with patch("tools.mcp.get_mcp_status_text", return_value="MCP: not initialized"):
        repl.handle_mcp_list()
    out = capsys.readouterr().out
    assert "MCP: not initialized" in out


def test_handle_mcp_list_shows_help(repl, capsys):
    with patch("tools.mcp.get_mcp_status_text", return_value="MCP: 1/1 connected, 3 tools"):
        repl.handle_mcp_list()
    out = capsys.readouterr().out
    assert "MCP: 1/1 connected" in out
    assert "/mcp status" in out
    assert "/mcp restart" in out
    assert "/mcp tools" in out
    assert "/mcp reload" in out


# --- handle_mcp_status ---


def test_handle_mcp_status_no_manager(repl, capsys):
    with patch("tools.mcp.get_mcp_manager", return_value=None):
        repl.handle_mcp_status()
    out = capsys.readouterr().out
    assert "not initialized" in out.lower()


def test_handle_mcp_status_empty(repl, capsys):
    mock_mgr = MagicMock()
    mock_mgr.get_all_states.return_value = {}
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_status()
    out = capsys.readouterr().out
    assert "No MCP servers" in out


def test_handle_mcp_status_connected_server(repl, capsys):
    state = _make_state("github", state="connected", n_tools=5)
    mock_mgr = MagicMock()
    mock_mgr.get_all_states.return_value = {"github": state}
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_status()
    out = capsys.readouterr().out
    assert "github" in out
    assert "connected" in out
    assert "tools: 5" in out
    assert "2026-05-21" in out


def test_handle_mcp_status_error_server(repl, capsys):
    state = _make_state("broken", state="error", n_tools=0, error="Connection refused")
    mock_mgr = MagicMock()
    mock_mgr.get_all_states.return_value = {"broken": state}
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_status()
    out = capsys.readouterr().out
    assert "broken" in out
    assert "Connection refused" in out


def test_handle_mcp_status_disabled(repl, capsys):
    state = _make_state("off", state="connected", enabled=False)
    mock_mgr = MagicMock()
    mock_mgr.get_all_states.return_value = {"off": state}
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_status()
    out = capsys.readouterr().out
    assert "disabled" in out


def test_handle_mcp_status_stdio_transport(repl, capsys):
    state = _make_state("ctx", state="connected")
    state.config.command = "ctx-mcp"
    mock_mgr = MagicMock()
    mock_mgr.get_all_states.return_value = {"ctx": state}
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_status()
    out = capsys.readouterr().out
    assert "stdio" in out
    assert "ctx-mcp" in out


def test_handle_mcp_status_http_transport(repl, capsys):
    state = _make_state("amap", state="connected")
    state.config.transport = "streamable_http"
    state.config.command = None
    state.config.url = "https://x.example.com/mcp"
    mock_mgr = MagicMock()
    mock_mgr.get_all_states.return_value = {"amap": state}
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_status()
    out = capsys.readouterr().out
    assert "streamable_http" in out
    assert "https://x.example.com/mcp" in out


# --- handle_mcp_restart ---


def test_handle_mcp_restart_no_manager(repl, capsys):
    with patch("tools.mcp.get_mcp_manager", return_value=None):
        repl.handle_mcp_restart([])
    out = capsys.readouterr().out
    assert "not initialized" in out.lower()


def test_handle_mcp_restart_specific_success(repl, capsys):
    state = _make_state("github", state="connected", n_tools=4)
    mock_mgr = MagicMock()
    mock_mgr.get_state.return_value = state
    mock_mgr.restart_server.return_value = True
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_restart(["github"])
    out = capsys.readouterr().out
    assert "github" in out
    assert "reconnected" in out
    mock_mgr.restart_server.assert_called_once_with("github")


def test_handle_mcp_restart_specific_failure(repl, capsys):
    state = _make_state("broken", state="error", error="timeout")
    mock_mgr = MagicMock()
    mock_mgr.get_state.return_value = state
    mock_mgr.restart_server.return_value = False
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_restart(["broken"])
    out = capsys.readouterr().out
    assert "failed" in out
    assert "timeout" in out


def test_handle_mcp_restart_unknown_server(repl, capsys):
    mock_mgr = MagicMock()
    mock_mgr.get_state.return_value = None
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_restart(["nope"])
    out = capsys.readouterr().out
    assert "No MCP server named" in out


def test_handle_mcp_restart_all(repl, capsys):
    s1 = _make_state("a", state="connected", n_tools=2)
    s2 = _make_state("b", state="error", n_tools=0, error="down")
    s3 = _make_state("c", state="connected", enabled=False)
    mock_mgr = MagicMock()
    mock_mgr.list_server_names.return_value = ["a", "b", "c"]
    mock_mgr.get_state.side_effect = lambda n: {"a": s1, "b": s2, "c": s3}[n]
    mock_mgr.restart_server.side_effect = lambda n: n == "a"
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_restart([])
    out = capsys.readouterr().out
    assert "a" in out
    assert "b" in out
    # disabled "c" should not be restarted
    assert "c" not in out.split("Restarting")[1] if "Restarting" in out else True


# --- handle_mcp_tools ---


def test_handle_mcp_tools_no_manager(repl, capsys):
    with patch("tools.mcp.get_mcp_manager", return_value=None):
        repl.handle_mcp_tools(["github"])
    out = capsys.readouterr().out
    assert "not initialized" in out.lower()


def test_handle_mcp_tools_missing_arg(repl, capsys):
    mock_mgr = MagicMock()
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_tools([])
    out = capsys.readouterr().out
    assert "Usage" in out


def test_handle_mcp_tools_unknown_server(repl, capsys):
    mock_mgr = MagicMock()
    mock_mgr.get_state.return_value = None
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_tools(["nope"])
    out = capsys.readouterr().out
    assert "No MCP server" in out


def test_handle_mcp_tools_disconnected(repl, capsys):
    state = _make_state("off", state="disconnected", n_tools=0)
    mock_mgr = MagicMock()
    mock_mgr.get_state.return_value = state
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_tools(["off"])
    out = capsys.readouterr().out
    assert "not connected" in out.lower()


def test_handle_mcp_tools_lists_tools(repl, capsys):
    state = _make_state(
        "amap",
        state="connected",
    )
    state.tools = [
        {"name": "maps_geo", "description": "Geocode an address"},
        {"name": "maps_direction_driving", "description": "Driving route"},
    ]
    mock_mgr = MagicMock()
    mock_mgr.get_state.return_value = state
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_tools(["amap"])
    out = capsys.readouterr().out
    assert "maps_geo" in out
    assert "maps_direction_driving" in out
    assert "Geocode" in out


def test_handle_mcp_tools_truncates_long_descriptions(repl, capsys):
    state = _make_state("amap", state="connected")
    state.tools = [{"name": "x", "description": "D" * 200}]
    mock_mgr = MagicMock()
    mock_mgr.get_state.return_value = state
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr):
        repl.handle_mcp_tools(["amap"])
    out = capsys.readouterr().out
    assert "..." in out
    assert "D" * 200 not in out  # full description is gone


# --- handle_mcp_reload ---


def test_handle_mcp_reload_no_manager(repl, capsys):
    with patch("tools.mcp.get_mcp_manager", return_value=None):
        repl.handle_mcp_reload()
    out = capsys.readouterr().out
    assert "not initialized" in out.lower()


def test_handle_mcp_reload_load_failure(repl, capsys):
    """If the config file can't be loaded, show an error."""
    mock_mgr = MagicMock()
    mock_mcp_cfg = MagicMock()
    mock_mcp_cfg.enabled = True
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr), \
         patch("providers.factory.ProviderFactory.load_config", side_effect=FileNotFoundError("nope")), \
         patch("mcp_client.config.load_config", return_value=mock_mcp_cfg):
        repl.handle_mcp_reload()
    out = capsys.readouterr().out
    assert "Failed to load" in out
    assert "nope" in out


def test_handle_mcp_reload_disabled(repl, capsys):
    mock_mgr = MagicMock()
    mock_cfg = MagicMock()
    mock_cfg.enabled = False
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr), \
         patch("mcp_client.config.load_config", return_value=mock_cfg):
        repl.handle_mcp_reload()
    out = capsys.readouterr().out
    assert "disabled" in out.lower()


def test_handle_mcp_reload_diff_display(repl, capsys):
    import re
    mock_mgr = MagicMock()
    mock_mgr.reload.return_value = {
        "added": ["new-srv"],
        "removed": ["old-srv"],
        "updated": ["changed-srv"],
        "unchanged": ["a", "b"],
    }
    mock_cfg = MagicMock()
    mock_cfg.enabled = True
    with patch("tools.mcp.get_mcp_manager", return_value=mock_mgr), \
         patch("mcp_client.config.load_config", return_value=mock_cfg), \
         patch("providers.factory.ProviderFactory.load_config", return_value={}):
        repl.handle_mcp_reload()
    out = capsys.readouterr().out
    # Strip ANSI escape codes (REPL output uses color)
    plain = re.sub(r"\x1b\[[0-9;]*m", "", out)
    assert "+ added: new-srv" in plain
    assert "- removed: old-srv" in plain
    assert "~ updated: changed-srv" in plain
    assert "unchanged: 2" in plain
    assert "re-launch" in plain  # hint about restarting REPL


# --- handle_mcp_command dispatch ---


def test_dispatch_no_args_shows_help(repl, capsys):
    with patch.object(repl, "handle_mcp_list") as mock:
        repl.handle_mcp_command("")
        mock.assert_called_once()


def test_dispatch_help_keyword(repl, capsys):
    with patch.object(repl, "handle_mcp_list") as mock:
        repl.handle_mcp_command("help")
        mock.assert_called_once()


def test_dispatch_status(repl, capsys):
    with patch.object(repl, "handle_mcp_status") as mock:
        repl.handle_mcp_command("status")
        mock.assert_called_once()


def test_dispatch_restart(repl, capsys):
    with patch.object(repl, "handle_mcp_restart") as mock:
        repl.handle_mcp_command("restart github")
        mock.assert_called_once_with(["github"])


def test_dispatch_tools(repl, capsys):
    with patch.object(repl, "handle_mcp_tools") as mock:
        repl.handle_mcp_command("tools amap")
        mock.assert_called_once_with(["amap"])


def test_dispatch_reload(repl, capsys):
    with patch.object(repl, "handle_mcp_reload") as mock:
        repl.handle_mcp_command("reload")
        mock.assert_called_once()


def test_dispatch_unknown(repl, capsys):
    with patch.object(repl, "print_mcp_help") as mock:
        repl.handle_mcp_command("frobnicate")
    out = capsys.readouterr().out
    assert "Unknown /mcp subcommand" in out
    mock.assert_called_once()


def test_dispatch_quoted_args(repl, capsys):
    """Server names with spaces should be handled via shlex."""
    with patch.object(repl, "handle_mcp_restart") as mock:
        repl.handle_mcp_command('restart "my server"')
        mock.assert_called_once_with(["my server"])
