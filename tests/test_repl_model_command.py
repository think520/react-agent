"""Tests for the /model REPL command (provider switching)."""

import os
from unittest.mock import MagicMock, patch

import pytest

from cli.repl import REPL
from core.agent_loop import AgentLoop
from providers.factory import ProviderFactory


# --- Fixtures ---


@pytest.fixture
def base_config():
    """A minimal llm config dict with two providers."""
    return {
        "llm": {
            "default_provider": "minimax",
            "providers": {
                "minimax": {
                    "type": "minimax",
                    "base_url": "https://api.minimaxi.com/v1",
                    "api_key_env": "MINIMAX_API_KEY",
                    "model": "MiniMax-M2.7",
                },
                "deepseek": {
                    "type": "deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key_env": "DEEPSEEK_API_KEY",
                    "model": "deepseek-v4-flash",
                },
                "openai": {
                    "type": "openai",
                    "base_url": "https://api.openai.com/v1",
                    "api_key_env": "OPENAI_API_KEY",
                    "model": "gpt-4",
                },
            },
        },
        "agent": {"temperature": 0.7, "timeout": 60, "max_retries": 3},
        "session": {"save_dir": ".session", "max_messages": 100},
        "skills": {"enabled": True, "dir": "skills"},
        "memory": {"enabled": True, "dir": ".bobodan"},
        "rag": {"embedding_backend": "local"},
        "mcp": {"enabled": False},
    }


@pytest.fixture
def repl(base_config):
    """Build a REPL with config but no initialize() side effects."""
    r = REPL.__new__(REPL)
    r.config_path = "config.yaml"
    r.config = base_config
    llm = base_config["llm"]
    r.default_provider = llm["default_provider"]
    r.active_provider = r.default_provider
    r.model_name = llm["providers"][r.default_provider]["model"]
    r.active_model = r.model_name
    r.api_key_env = llm["providers"][r.default_provider]["api_key_env"]
    r.session = MagicMock()
    r.session.messages = []
    r.session.cwd = "/tmp"
    r.session.workspace_root = "/tmp"
    r.agent = MagicMock(spec=AgentLoop)
    return r


@pytest.fixture
def fake_provider():
    """A stand-in provider that has get_name()."""
    p = MagicMock()
    p.get_name.return_value = "fake-provider"
    return p


# --- AgentLoop.set_provider ---


def test_agent_loop_set_provider_swaps_llm():
    """AgentLoop.set_provider should replace self.llm with the new provider."""
    old = MagicMock()
    new = MagicMock()
    loop = AgentLoop(llm_provider=old, session=MagicMock())
    assert loop.llm is old
    loop.set_provider(new)
    assert loop.llm is new


# --- REPL.set_provider ---


def test_set_provider_happy_path(repl, fake_provider, monkeypatch):
    """Successful switch updates active provider, model, and self.agent.llm."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    with patch.object(ProviderFactory, "create", return_value=fake_provider) as mock_create:
        ok, message = repl.set_provider("deepseek")

    assert ok is True
    assert "minimax/MiniMax-M2.7" in message
    assert "deepseek/deepseek-v4-flash" in message
    assert repl.active_provider == "deepseek"
    assert repl.active_model == "deepseek-v4-flash"
    repl.agent.set_provider.assert_called_once_with(fake_provider)
    # ProviderFactory.create should have been called with deepseek's config
    called_config, _ = mock_create.call_args[0]
    assert called_config["model"] == "deepseek-v4-flash"
    assert called_config["api_key_env"] == "DEEPSEEK_API_KEY"


def test_set_provider_unknown_name(repl):
    """Switching to a provider not in config returns False and leaves state intact."""
    ok, message = repl.set_provider("nonexistent")
    assert ok is False
    assert "nonexistent" in message
    assert "minimax" in message  # Available list includes minimax
    assert repl.active_provider == "minimax"
    assert repl.active_model == "MiniMax-M2.7"
    repl.agent.set_provider.assert_not_called()


def test_set_provider_create_failure_preserves_state(repl, monkeypatch):
    """If ProviderFactory.create raises, state must not change."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    ok, message = repl.set_provider("deepseek")
    assert ok is False
    assert "DEEPSEEK_API_KEY" in message or "Failed" in message
    assert repl.active_provider == "minimax"
    assert repl.active_model == "MiniMax-M2.7"
    repl.agent.set_provider.assert_not_called()


def test_set_provider_no_agent(repl, fake_provider, monkeypatch):
    """If self.agent is None, set_provider should still update state without error."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    repl.agent = None
    with patch.object(ProviderFactory, "create", return_value=fake_provider):
        ok, message = repl.set_provider("deepseek")
    assert ok is True
    assert repl.active_provider == "deepseek"
    assert repl.active_model == "deepseek-v4-flash"


def test_set_provider_same_name_works(repl, fake_provider, monkeypatch):
    """Switching to the currently active provider is a valid no-op-ish action."""
    monkeypatch.setenv("MINIMAX_API_KEY", "fake")
    with patch.object(ProviderFactory, "create", return_value=fake_provider):
        ok, message = repl.set_provider("minimax")
    assert ok is True
    assert repl.active_provider == "minimax"
    repl.agent.set_provider.assert_called_once()


def test_set_provider_no_providers_in_config():
    """Empty providers dict should produce a clear error."""
    r = REPL.__new__(REPL)
    r.config = {"llm": {"providers": {}}}
    r.active_provider = "?"
    r.active_model = "?"
    ok, message = r.set_provider("anything")
    assert ok is False
    assert "Unknown provider" in message
    assert "(none)" in message


# --- handle_model_command ---


def test_handle_model_no_args_shows_current(repl, capsys):
    """/model with no args prints the active provider."""
    repl.handle_model_command("")
    out = capsys.readouterr().out
    assert "minimax" in out
    assert "MiniMax-M2.7" in out
    assert "(default)" in out


def test_handle_model_current_alias(repl, capsys):
    """/model current is the same as /model."""
    repl.handle_model_command("current")
    out = capsys.readouterr().out
    assert "minimax" in out
    assert "MiniMax-M2.7" in out


def test_handle_model_list(repl, capsys):
    """/model list shows all configured providers with active marker."""
    repl.handle_model_command("list")
    out = capsys.readouterr().out
    assert "deepseek" in out
    assert "deepseek-v4-flash" in out
    assert "minimax" in out
    assert "openai" in out
    assert "gpt-4" in out
    assert "★" in out  # Active marker
    assert "/model use" in out


def test_handle_model_list_no_providers(repl, capsys):
    """/model list with empty providers config shows a notice."""
    repl.config["llm"]["providers"] = {}
    repl.handle_model_command("list")
    out = capsys.readouterr().out
    assert "No providers" in out


def test_handle_model_use_success(repl, fake_provider, monkeypatch, capsys):
    """/model use <name> switches and prints success."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    with patch.object(ProviderFactory, "create", return_value=fake_provider):
        repl.handle_model_command("use deepseek")
    out = capsys.readouterr().out
    assert "minimax/MiniMax-M2.7" in out
    assert "deepseek/deepseek-v4-flash" in out
    assert repl.active_provider == "deepseek"


def test_handle_model_use_unknown(repl, capsys):
    """/model use <unknown> prints error and leaves state intact."""
    repl.handle_model_command("use bogus")
    out = capsys.readouterr().out
    assert "Unknown provider" in out
    assert "bogus" in out
    assert repl.active_provider == "minimax"


def test_handle_model_use_missing_arg(repl, capsys):
    """/model use without a name prints usage."""
    repl.handle_model_command("use")
    out = capsys.readouterr().out
    assert "Usage" in out
    assert "/model use" in out


def test_handle_model_use_create_failure(repl, monkeypatch, capsys):
    """/model use failing (e.g. missing API key) prints error, no state change."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    repl.handle_model_command("use deepseek")
    out = capsys.readouterr().out
    assert "Failed" in out or "DEEPSEEK_API_KEY" in out
    assert repl.active_provider == "minimax"


def test_handle_model_unknown_subcommand(repl, capsys):
    """/model foo prints help."""
    repl.handle_model_command("foo")
    out = capsys.readouterr().out
    assert "Unknown" in out
    assert "Model 命令" in out


def test_handle_model_help(repl, capsys):
    """/model help prints the help block."""
    repl.handle_model_command("help")
    out = capsys.readouterr().out
    assert "Model 命令" in out
    assert "/model list" in out
    assert "/model use" in out


# --- print_model_status edge cases ---


def test_print_model_status_overridden(repl, fake_provider, monkeypatch, capsys):
    """When active != default, status should show both."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    with patch.object(ProviderFactory, "create", return_value=fake_provider):
        repl.set_provider("deepseek")
    capsys.readouterr()  # discard set_provider output
    repl.print_model_status()
    out = capsys.readouterr().out
    assert "deepseek" in out
    assert "deepseek-v4-flash" in out
    assert "overridden" in out
    assert "minimax" in out  # default shown


# --- Command registration ---


def test_model_registered_in_all_commands():
    """'model' should appear in ALL_COMMANDS for tab completion."""
    from cli.repl import ALL_COMMANDS
    assert "model" in ALL_COMMANDS


def test_model_in_command_hints():
    """'model' should appear in COMMAND_HINTS for live autocomplete."""
    from cli.repl import COMMAND_HINTS
    hints = [c for c, _ in COMMAND_HINTS]
    assert "/model" in hints
    assert "/model list" in hints
    assert "/model use " in hints
