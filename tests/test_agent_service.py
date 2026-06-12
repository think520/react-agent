"""Tests for AgentService — service layer for provider, session, and agent run."""

import os
import pytest

from service.agent_service import AgentService


@pytest.fixture
def base_config():
    return {
        "llm": {
            "default_provider": "deepseek",
            "providers": {
                "deepseek": {
                    "type": "deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "api_key_env": "DEEPSEEK_API_KEY",
                    "model": "deepseek-chat",
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
    }


@pytest.fixture
def save_dir(tmp_path):
    return str(tmp_path / "sessions")


# --- create_provider ---

def test_create_provider_unknown(base_config):
    result = AgentService.create_provider(base_config, "nonexistent")
    assert not result["ok"]
    assert "Unknown provider" in result["error"]
    assert "deepseek" in result["error"]


def test_create_provider_missing_env(base_config, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = AgentService.create_provider(base_config, "deepseek")
    # Should fail because env var is missing
    assert not result["ok"]
    assert "DEEPSEEK_API_KEY" in result["error"] or "not set" in result["error"].lower() or "failed" in result["error"].lower()


def test_create_provider_success(base_config, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    result = AgentService.create_provider(base_config, "deepseek")
    assert result["ok"]
    assert result["provider"] is not None
    assert result["provider"].get_name() == "deepseek"


def test_create_provider_empty_config():
    result = AgentService.create_provider({}, "any")
    assert not result["ok"]
    assert "Unknown provider" in result["error"]


# --- list_providers ---

def test_list_providers(base_config, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = AgentService.list_providers(base_config)
    assert result["ok"]
    providers = result["providers"]
    assert len(providers) == 2

    names = {p["name"] for p in providers}
    assert names == {"deepseek", "openai"}

    ds = next(p for p in providers if p["name"] == "deepseek")
    assert ds["configured"] is True
    assert ds["model"] == "deepseek-chat"
    assert ds["is_default"] is True

    oai = next(p for p in providers if p["name"] == "openai")
    assert oai["configured"] is False
    assert oai["is_default"] is False


def test_list_providers_empty_config():
    result = AgentService.list_providers({})
    assert result["ok"]
    assert result["providers"] == []


# --- list_sessions ---

def test_list_sessions_empty(save_dir):
    result = AgentService.list_sessions(save_dir)
    assert result["ok"]
    assert result["sessions"] == []


def test_list_sessions_with_data(save_dir):
    from core.session import Session

    os.makedirs(save_dir, exist_ok=True)
    s = Session.new("/tmp")
    s.name = "test-session"
    s.save_to_file(os.path.join(save_dir, f"{s.session_id}.json"))

    result = AgentService.list_sessions(save_dir)
    assert result["ok"]
    assert len(result["sessions"]) == 1
    assert result["sessions"][0]["name"] == "test-session"


# --- save_session ---

def test_save_session(save_dir):
    from core.session import Session

    session = Session.new("/tmp")
    result = AgentService.save_session(session, save_dir, name="my-session")
    assert result["ok"]
    assert result["session_id"] == session.session_id
    assert os.path.exists(result["path"])
    assert session.name == "my-session"


def test_save_session_creates_dir(save_dir):
    from core.session import Session

    session = Session.new("/tmp")
    result = AgentService.save_session(session, save_dir)
    assert result["ok"]
    assert os.path.isdir(save_dir)


# --- load_session ---

def test_load_session_no_sessions(save_dir):
    result = AgentService.load_session("anything", save_dir)
    assert not result["ok"]
    assert "No saved sessions" in result["error"]


def test_load_session_exact_match(save_dir):
    from core.session import Session

    os.makedirs(save_dir, exist_ok=True)
    s = Session.new("/tmp")
    s.name = "test"
    s.save_to_file(os.path.join(save_dir, f"{s.session_id}.json"))

    result = AgentService.load_session(s.session_id, save_dir)
    assert result["ok"]
    assert result["session"].session_id == s.session_id


def test_load_session_prefix_match(save_dir):
    from core.session import Session

    os.makedirs(save_dir, exist_ok=True)
    s = Session.new("/tmp")
    s.save_to_file(os.path.join(save_dir, f"{s.session_id}.json"))

    prefix = s.session_id[:8]
    result = AgentService.load_session(prefix, save_dir)
    assert result["ok"]
    assert result["session"].session_id == s.session_id


def test_load_session_name_match(save_dir):
    from core.session import Session

    os.makedirs(save_dir, exist_ok=True)
    s = Session.new("/tmp")
    s.name = "my-unique-session"
    s.save_to_file(os.path.join(save_dir, f"{s.session_id}.json"))

    result = AgentService.load_session("my-unique", save_dir)
    assert result["ok"]
    assert result["session"].name == "my-unique-session"


def test_load_session_not_found(save_dir):
    from core.session import Session

    os.makedirs(save_dir, exist_ok=True)
    s = Session.new("/tmp")
    s.save_to_file(os.path.join(save_dir, f"{s.session_id}.json"))

    result = AgentService.load_session("zzzzzzzz-nonexistent", save_dir)
    assert not result["ok"]
    assert "not found" in result["error"].lower()


def test_load_session_ambiguous_prefix(save_dir):
    from core.session import Session

    os.makedirs(save_dir, exist_ok=True)
    # Create two sessions with a shared prefix
    s1 = Session.__new__(Session)
    s1.session_id = "aaaa-1111-2222-3333-4444"
    s1.cwd = "/tmp"
    s1.workspace_root = "/tmp"
    s1.messages = []
    s1.created_at = "2026-01-01"
    s1.last_active = "2026-01-01"
    s1.max_messages = None
    s1.name = "s1"

    s2 = Session.__new__(Session)
    s2.session_id = "aaaa-5555-6666-7778-8888"
    s2.cwd = "/tmp"
    s2.workspace_root = "/tmp"
    s2.messages = []
    s2.created_at = "2026-01-01"
    s2.last_active = "2026-01-01"
    s2.max_messages = None
    s2.name = "s2"

    s1.save_to_file(os.path.join(save_dir, f"{s1.session_id}.json"))
    s2.save_to_file(os.path.join(save_dir, f"{s2.session_id}.json"))

    # Both start with "aaaa" — ambiguous
    result = AgentService.load_session("aaaa", save_dir)
    assert not result["ok"]
    assert "ambiguous" in result["error"].lower()


def test_load_session_strips_json_suffix(save_dir):
    from core.session import Session

    os.makedirs(save_dir, exist_ok=True)
    s = Session.new("/tmp")
    s.save_to_file(os.path.join(save_dir, f"{s.session_id}.json"))

    result = AgentService.load_session(f"{s.session_id}.json", save_dir)
    assert result["ok"]
    assert result["session"].session_id == s.session_id


# --- run_stream ---

def test_run_stream_yields_events(monkeypatch):
    from core.session import Session

    class DummyProvider:
        def complete(self, messages, tools=None):
            from providers.types import LLMResponse
            return LLMResponse(content="Hello!")

        def get_name(self):
            return "dummy"

    session = Session.new("/tmp")
    monkeypatch.setattr("core.agent_loop.get_tools_schema", lambda: [])

    events = list(AgentService.run_stream(session, "hi", DummyProvider()))
    types = [e["type"] for e in events]
    assert "assistant_delta" in types
    assert "assistant_done" in types


def test_run_stream_mutates_session(monkeypatch):
    from core.session import Session

    class DummyProvider:
        def complete(self, messages, tools=None):
            from providers.types import LLMResponse
            return LLMResponse(content="Hello!")

        def get_name(self):
            return "dummy"

    session = Session.new("/tmp")
    monkeypatch.setattr("core.agent_loop.get_tools_schema", lambda: [])

    assert len(session.messages) == 0
    list(AgentService.run_stream(session, "hi", DummyProvider()))
    assert len(session.messages) >= 2  # user + assistant
