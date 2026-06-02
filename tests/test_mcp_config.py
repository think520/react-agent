"""Tests for mcp_client.config: YAML loading, env var substitution, validation."""

import os
import pytest

from mcp_client.config import (
    MCPConfig,
    MCPServerConfig,
    load_config,
    parse_server_config,
    substitute_env,
    substitute_env_in_mapping,
)


# --- substitute_env ---


def test_substitute_env_simple(monkeypatch):
    monkeypatch.setenv("FOO", "bar")
    assert substitute_env("hello ${FOO}") == "hello bar"


def test_substitute_env_multiple(monkeypatch):
    monkeypatch.setenv("A", "1")
    monkeypatch.setenv("B", "2")
    assert substitute_env("${A}-${B}") == "1-2"


def test_substitute_env_no_placeholder():
    assert substitute_env("plain string") == "plain string"


def test_substitute_env_missing_raises():
    with pytest.raises(EnvironmentError, match="MISSING_VAR"):
        substitute_env("value: ${MISSING_VAR}")


def test_substitute_env_partial_missing(monkeypatch):
    monkeypatch.setenv("PRESENT", "ok")
    with pytest.raises(EnvironmentError, match="ABSENT"):
        substitute_env("${PRESENT} and ${ABSENT}")


# --- substitute_env_in_mapping ---


def test_substitute_env_in_mapping_nested(monkeypatch):
    monkeypatch.setenv("TOKEN", "abc123")
    raw = {
        "url": "https://api.example.com",
        "headers": {"Authorization": "Bearer ${TOKEN}"},
        "args": ["--token", "${TOKEN}"],
        "meta": {"comment": "uses ${TOKEN}"},
        "port": 8080,
    }
    out = substitute_env_in_mapping(raw)
    assert out["headers"]["Authorization"] == "Bearer abc123"
    assert out["args"] == ["--token", "abc123"]
    assert out["meta"]["comment"] == "uses abc123"
    assert out["port"] == 8080


# --- parse_server_config ---


def test_parse_stdio_defaults_transport():
    cfg = parse_server_config("ctx", {"command": "uvx", "args": ["ctx"]})
    assert cfg.transport == "stdio"
    assert cfg.command == "uvx"
    assert cfg.args == ["ctx"]


def test_parse_http_defaults_to_sse():
    cfg = parse_server_config("docs", {"url": "https://x.example.com"})
    assert cfg.transport == "sse"
    assert cfg.url == "https://x.example.com"


def test_parse_explicit_streamable_http():
    cfg = parse_server_config("s", {"url": "https://x", "transport": "streamable_http"})
    assert cfg.transport == "streamable_http"


def test_parse_disabled_server():
    cfg = parse_server_config("x", {"command": "foo", "enabled": False})
    assert cfg.enabled is False
    # Validation should not raise when disabled
    cfg.validate()


def test_parse_unknown_transport_raises():
    with pytest.raises(ValueError, match="unknown transport"):
        parse_server_config("x", {"url": "https://x", "transport": "weird"})


def test_parse_missing_command_and_url_raises():
    with pytest.raises(ValueError, match="must have either"):
        parse_server_config("x", {})


def test_parse_rejects_non_https():
    with pytest.raises(ValueError, match="http:// or https://"):
        parse_server_config("x", {"url": "ftp://example.com"})


def test_validate_stdio_requires_command():
    cfg = MCPServerConfig(name="x", transport="stdio")
    with pytest.raises(ValueError, match="requires 'command'"):
        cfg.validate()


def test_validate_http_requires_url():
    cfg = MCPServerConfig(name="x", transport="sse")
    with pytest.raises(ValueError, match="requires 'url'"):
        cfg.validate()


def test_validate_disabled_skips_check():
    cfg = MCPServerConfig(name="x", transport="stdio", enabled=False)
    cfg.validate()  # should not raise


# --- load_config ---


def test_load_config_missing_section():
    cfg = load_config({})
    assert cfg.enabled is False
    assert cfg.servers == {}


def test_load_config_disabled_by_default():
    cfg = load_config({"mcp": {"servers": {"x": {"command": "foo"}}}})
    assert cfg.enabled is False


def test_load_config_full():
    raw = {
        "mcp": {
            "enabled": True,
            "connection_timeout": 15,
            "tool_call_timeout": 45,
            "servers": {
                "ctx": {"command": "uvx", "args": ["ctx-mcp"]},
                "docs": {"url": "https://docs.example.com"},
            },
        }
    }
    cfg = load_config(raw)
    assert cfg.enabled is True
    assert cfg.connection_timeout == 15
    assert cfg.tool_call_timeout == 45
    assert set(cfg.servers) == {"ctx", "docs"}
    assert cfg.servers["ctx"].transport == "stdio"
    assert cfg.servers["docs"].transport == "sse"


def test_load_config_validates_each_server():
    raw = {"mcp": {"enabled": True, "servers": {"bad": {}}}}
    with pytest.raises(ValueError, match="must have either"):
        load_config(raw)


def test_load_config_none():
    cfg = load_config(None)
    assert cfg.enabled is False


def test_load_config_servers_not_mapping():
    raw = {"mcp": {"enabled": True, "servers": ["not", "a", "dict"]}}
    with pytest.raises(ValueError, match="must be a mapping"):
        load_config(raw)


def test_enabled_servers_filters():
    raw = {
        "mcp": {
            "enabled": True,
            "servers": {
                "a": {"command": "foo"},
                "b": {"command": "bar", "enabled": False},
            },
        }
    }
    cfg = load_config(raw)
    enabled = cfg.enabled_servers()
    assert len(enabled) == 1
    assert enabled[0].name == "a"


def test_env_substitution_in_config(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "secret-xyz")
    raw = {
        "mcp": {
            "enabled": True,
            "servers": {
                "auth": {
                    "url": "https://x.example.com",
                    "headers": {"Authorization": "Bearer ${API_TOKEN}"},
                }
            },
        }
    }
    cfg = load_config(raw)
    assert cfg.servers["auth"].headers["Authorization"] == "Bearer secret-xyz"
