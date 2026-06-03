"""Tests for mcp_client.manager.

Strategy: inject a fake `Transport` class via monkeypatching the
`manager._build_transport` method, then exercise the manager's
synchronous API (call, list_tools_for_server, reload, etc).
"""

import pytest

from mcp_client.config import MCPConfig, MCPServerConfig
from mcp_client.event_loop import AsyncEventLoop
from mcp_client.manager import MCPManager, ServerState, _server_config_changed


@pytest.fixture(autouse=True)
def _reset_event_loop():
    AsyncEventLoop.reset()
    yield
    AsyncEventLoop.reset()


def _make_config() -> MCPConfig:
    return MCPConfig(
        enabled=True,
        connection_timeout=5,
        tool_call_timeout=10,
        servers={
            "ctx": MCPServerConfig(
                name="ctx",
                transport="stdio",
                command="fake-ctx",
            ),
            "remote": MCPServerConfig(
                name="remote",
                transport="streamable_http",
                url="https://mcp.example.com",
            ),
            "disabled_one": MCPServerConfig(
                name="disabled_one",
                enabled=False,
                transport="stdio",
                command="x",
            ),
        },
    )


# --- construction & introspection ---


def test_construction_creates_states():
    cfg = _make_config()
    mgr = MCPManager(cfg)
    assert mgr.list_server_names() == ["ctx", "remote", "disabled_one"]
    assert mgr.get_state("ctx").config.name == "ctx"
    assert mgr.get_state("nonexistent") is None
    assert mgr.get_global_timeouts() == (5, 10)


def test_construction_all_disconnected():
    mgr = MCPManager(_make_config())
    for state in mgr.get_all_states().values():
        assert state.state == "disconnected"
        assert state.transport is None
        assert state.tools == []


def test_disabled_server_state_tracks():
    mgr = MCPManager(_make_config())
    state = mgr.get_state("disabled_one")
    assert state.config.enabled is False


def test_empty_config():
    cfg = MCPConfig(enabled=False)
    mgr = MCPManager(cfg)
    assert mgr.list_server_names() == []


# --- call() with mocked transport ---


class _FakeTransport:
    """In-memory fake of the abstract Transport."""

    def __init__(self, cfg, timeout):
        self.cfg = cfg
        self.timeout = timeout
        self.connected = False
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.call_log: list[tuple[str, dict]] = []
        self.next_result: dict = {"content": [{"type": "text", "text": "ok"}], "isError": False}
        self.next_tools: list[dict] = [
            {"name": "echo", "description": "echo back", "inputSchema": {"type": "object"}},
        ]
        self.connect_should_raise: Exception | None = None
        self.call_should_raise: Exception | None = None

    async def connect(self):
        self.connect_calls += 1
        if self.connect_should_raise:
            raise self.connect_should_raise
        self.connected = True

    async def disconnect(self):
        self.disconnect_calls += 1
        self.connected = False

    async def list_tools(self):
        return list(self.next_tools)

    async def call_tool(self, name, arguments):
        self.call_log.append((name, arguments))
        if self.call_should_raise:
            raise self.call_should_raise
        return dict(self.next_result)

    @property
    def is_connected(self):
        return self.connected


def _inject_fake_transport(monkeypatch, mgr):
    """Patch manager._build_transport to return _FakeTransport instances,
    keeping a per-server registry so tests can assert on them.

    Fakes are created eagerly (one per enabled server) so tests can
    mutate them before the first call(). The same fake is returned
    on reconnect so the test can assert cumulative call counts.
    """
    registry: dict[str, _FakeTransport] = {}

    def fake_build(cfg: MCPServerConfig):
        if cfg.name in registry:
            return registry[cfg.name]
        t = _FakeTransport(cfg, timeout=5)
        registry[cfg.name] = t
        return t

    monkeypatch.setattr(mgr, "_build_transport", fake_build)

    # Eagerly create a fake for every enabled server so tests can
    # configure failure modes before triggering the first call.
    for state in mgr.get_all_states().values():
        if state.config.enabled:
            fake_build(state.config)
    return registry


def test_call_lazy_connects_then_invokes(monkeypatch):
    mgr = MCPManager(_make_config())
    fake_by_name = _inject_fake_transport(monkeypatch, mgr)

    result = mgr.call("ctx", "echo", {"x": 1})

    assert result["isError"] is False
    assert result["content"][0]["text"] == "ok"
    fake = fake_by_name["ctx"]
    assert fake.connect_calls == 1
    assert fake.call_log == [("echo", {"x": 1})]
    assert mgr.get_state("ctx").state == "connected"


def test_call_reuses_connection(monkeypatch):
    mgr = MCPManager(_make_config())
    fake_by_name = _inject_fake_transport(monkeypatch, mgr)

    mgr.call("ctx", "echo", {})
    mgr.call("ctx", "echo", {})

    fake = fake_by_name["ctx"]
    assert fake.connect_calls == 1  # only first call connects
    assert len(fake.call_log) == 2


def test_call_disabled_server_returns_error(monkeypatch):
    mgr = MCPManager(_make_config())
    _inject_fake_transport(monkeypatch, mgr)
    result = mgr.call("disabled_one", "x", {})
    assert result["isError"] is True
    assert "disabled" in result["content"][0]["text"]


def test_call_unknown_server_returns_error(monkeypatch):
    mgr = MCPManager(_make_config())
    _inject_fake_transport(monkeypatch, mgr)
    result = mgr.call("does_not_exist", "x", {})
    assert result["isError"] is True
    assert "Unknown MCP server" in result["content"][0]["text"]


def test_call_connection_failure_marks_error(monkeypatch):
    mgr = MCPManager(_make_config())
    fake_by_name = _inject_fake_transport(monkeypatch, mgr)
    fake_by_name["ctx"].connect_should_raise = ConnectionRefusedError("nope")

    result = mgr.call("ctx", "echo", {})

    assert result["isError"] is True
    assert "ConnectionRefusedError" in result["content"][0]["text"]
    assert mgr.get_state("ctx").state == "error"
    assert mgr.get_state("ctx").last_error is not None


def test_call_recovers_after_failed_connect(monkeypatch):
    mgr = MCPManager(_make_config())
    fake_by_name = _inject_fake_transport(monkeypatch, mgr)
    fake = fake_by_name["ctx"]
    fake.connect_should_raise = ConnectionRefusedError("first try")

    mgr.call("ctx", "echo", {})  # fails

    fake.connect_should_raise = None  # server now reachable
    result = mgr.call("ctx", "echo", {"ok": True})
    assert result["isError"] is False
    assert mgr.get_state("ctx").state == "connected"
    assert fake.connect_calls == 2  # retried on second call


def test_call_tool_error_propagates(monkeypatch):
    mgr = MCPManager(_make_config())
    fake_by_name = _inject_fake_transport(monkeypatch, mgr)
    fake_by_name["ctx"].next_result = {
        "content": [{"type": "text", "text": "tool said no"}],
        "isError": True,
    }
    result = mgr.call("ctx", "echo", {})
    assert result["isError"] is True
    assert "tool said no" in result["content"][0]["text"]


# --- list_tools_for_server ---


def test_list_tools_caches_after_first_call(monkeypatch):
    mgr = MCPManager(_make_config())
    fake_by_name = _inject_fake_transport(monkeypatch, mgr)

    tools_a = mgr.list_tools_for_server("ctx")
    tools_b = mgr.list_tools_for_server("ctx")

    assert tools_a == tools_b
    assert fake_by_name["ctx"].connect_calls == 1


def test_list_tools_for_disabled_returns_empty(monkeypatch):
    mgr = MCPManager(_make_config())
    _inject_fake_transport(monkeypatch, mgr)
    assert mgr.list_tools_for_server("disabled_one") == []


# --- restart_server ---


def test_restart_disconnects_then_reconnects(monkeypatch):
    mgr = MCPManager(_make_config())
    fake_by_name = _inject_fake_transport(monkeypatch, mgr)

    # First connect via call
    mgr.call("ctx", "echo", {})
    fake = fake_by_name["ctx"]
    pre_calls = fake.connect_calls

    # Restart
    ok = mgr.restart_server("ctx")
    assert ok is True
    assert fake.disconnect_calls == 1
    assert fake.connect_calls == pre_calls + 1
    assert mgr.get_state("ctx").state == "connected"


def test_restart_unknown_server_returns_false(monkeypatch):
    mgr = MCPManager(_make_config())
    _inject_fake_transport(monkeypatch, mgr)
    assert mgr.restart_server("nope") is False


# --- reload ---


def test_reload_add_new_server(monkeypatch):
    mgr = MCPManager(_make_config())
    _inject_fake_transport(monkeypatch, mgr)

    new_cfg = MCPConfig(
        enabled=True,
        connection_timeout=5,
        tool_call_timeout=10,
        servers={
            **mcfg_dict(),
            "new_server": MCPServerConfig(
                name="new_server",
                transport="stdio",
                command="new-cmd",
            ),
        },
    )
    diff = mgr.reload(new_cfg)
    assert "new_server" in diff["added"]
    assert mgr.get_state("new_server") is not None


def test_reload_remove_server(monkeypatch):
    mgr = MCPManager(_make_config())
    fake_by_name = _inject_fake_transport(monkeypatch, mgr)

    # Connect first so disconnect is exercised
    mgr.call("ctx", "echo", {})
    fake = fake_by_name["ctx"]
    pre_disc = fake.disconnect_calls

    new_cfg = MCPConfig(
        enabled=True,
        connection_timeout=5,
        tool_call_timeout=10,
        servers={
            "remote": MCPServerConfig(
                name="remote",
                transport="streamable_http",
                url="https://mcp.example.com",
            ),
        },
    )
    diff = mgr.reload(new_cfg)
    assert "ctx" in diff["removed"]
    assert mgr.get_state("ctx") is None
    assert fake.disconnect_calls == pre_disc + 1


def test_reload_updated_config_disconnects(monkeypatch):
    mgr = MCPManager(_make_config())
    fake_by_name = _inject_fake_transport(monkeypatch, mgr)

    mgr.call("ctx", "echo", {})
    fake = fake_by_name["ctx"]
    pre_disc = fake.disconnect_calls

    new_cfg = MCPConfig(
        enabled=True,
        connection_timeout=5,
        tool_call_timeout=10,
        servers={
            "ctx": MCPServerConfig(
                name="ctx",
                transport="stdio",
                command="different-cmd",  # changed
            ),
            "remote": MCPServerConfig(
                name="remote",
                transport="streamable_http",
                url="https://mcp.example.com",
            ),
            "disabled_one": MCPServerConfig(
                name="disabled_one",
                enabled=False,
                transport="stdio",
                command="x",
            ),
        },
    )
    diff = mgr.reload(new_cfg)
    assert "ctx" in diff["updated"]
    assert fake.disconnect_calls == pre_disc + 1
    assert mgr.get_state("ctx").config.command == "different-cmd"


def test_reload_unchanged_no_disconnect(monkeypatch):
    mgr = MCPManager(_make_config())
    fake_by_name = _inject_fake_transport(monkeypatch, mgr)
    mgr.call("ctx", "echo", {})
    pre_disc = fake_by_name["ctx"].disconnect_calls

    diff = mgr.reload(_make_config())
    assert "ctx" in diff["unchanged"]
    assert fake_by_name["ctx"].disconnect_calls == pre_disc


def test_reload_clears_last_error(monkeypatch):
    mgr = MCPManager(_make_config())
    fake_by_name = _inject_fake_transport(monkeypatch, mgr)
    fake_by_name["ctx"].connect_should_raise = ConnectionRefusedError("x")
    mgr.call("ctx", "echo", {})  # sets last_error

    state = mgr.get_state("ctx")
    assert state.last_error is not None

    diff = mgr.reload(_make_config())
    # "ctx" is unchanged (same command), so last_error is preserved
    assert "ctx" in diff["unchanged"]
    assert state.last_error is not None  # still there

    # Force an "updated" path to verify clear
    new_cfg = MCPConfig(
        enabled=True,
        connection_timeout=5,
        tool_call_timeout=10,
        servers={
            "ctx": MCPServerConfig(
                name="ctx",
                transport="stdio",
                command="changed",
            ),
            "remote": MCPServerConfig(
                name="remote",
                transport="streamable_http",
                url="https://mcp.example.com",
            ),
            "disabled_one": MCPServerConfig(
                name="disabled_one",
                enabled=False,
                transport="stdio",
                command="x",
            ),
        },
    )
    mgr.reload(new_cfg)
    assert state.last_error is None  # cleared on update


# --- shutdown ---


def test_shutdown_disconnects_all(monkeypatch):
    mgr = MCPManager(_make_config())
    fake_by_name = _inject_fake_transport(monkeypatch, mgr)
    mgr.call("ctx", "echo", {})
    mgr.call("remote", "x", {})

    mgr.shutdown()

    assert fake_by_name["ctx"].disconnect_calls == 1
    assert fake_by_name["remote"].disconnect_calls == 1


def test_shutdown_no_connections_is_noop(monkeypatch):
    mgr = MCPManager(_make_config())
    _inject_fake_transport(monkeypatch, mgr)
    mgr.shutdown()  # should not raise


# --- helpers ---


def test_server_config_changed_detects_diff():
    a = MCPServerConfig(name="x", transport="stdio", command="foo")
    b = MCPServerConfig(name="x", transport="stdio", command="foo")
    assert _server_config_changed(a, b) is False

    c = MCPServerConfig(name="x", transport="stdio", command="bar")
    assert _server_config_changed(a, c) is True

    d = MCPServerConfig(name="x", transport="sse", command=None, url="https://x")
    assert _server_config_changed(a, d) is True

    e = MCPServerConfig(name="x", transport="stdio", command="foo", args=["--flag"])
    assert _server_config_changed(a, e) is True

    f = MCPServerConfig(name="x", transport="stdio", command="foo", env={"K": "V"})
    assert _server_config_changed(a, f) is True


def mcfg_dict():
    """Reconstruct the {name: MCPServerConfig} dict for reload tests."""
    cfg = _make_config()
    return dict(cfg.servers)
