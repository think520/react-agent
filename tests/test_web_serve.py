"""P5G.1: `bobodan web` port selection and platform data directories."""

import socket

import pytest

from cli.web_serve import find_free_port, resolve_home, resolve_log_dir


def _listen(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", port))
    sock.listen(1)
    return sock


def test_find_free_port_uses_preferred_when_free():
    port = find_free_port("127.0.0.1", 8019)
    assert port == 8019


def test_find_free_port_skips_occupied():
    occupied = _listen(8023)
    try:
        port = find_free_port("127.0.0.1", 8023)
        assert port != 8023
        assert port in (8024, 8025)
    finally:
        occupied.close()


def test_resolve_home_uses_configured_env(monkeypatch):
    monkeypatch.setenv("BOBODAN_HOME", "C:/tmp/custom-home")
    assert resolve_home().replace("\\", "/") == "C:/tmp/custom-home"


def test_resolve_home_defaults_to_dot_directory(monkeypatch):
    """~/.bobodan dot-directory is the production default on every OS
    (2026-08-12 decision, Codex/OpenHanako style)."""
    monkeypatch.delenv("BOBODAN_HOME", raising=False)
    monkeypatch.setenv("USERPROFILE", "C:/users/test")
    monkeypatch.delenv("HOMEDRIVE", raising=False)
    monkeypatch.delenv("HOMEPATH", raising=False)
    monkeypatch.setattr("os.name", "nt")
    assert resolve_home().replace("\\", "/") == "C:/users/test/.bobodan"

    monkeypatch.setattr("os.name", "posix")
    assert resolve_home().replace("\\", "/") == "C:/users/test/.bobodan"


def test_resolve_log_dir_windows_localappdata(monkeypatch):
    monkeypatch.setattr("os.name", "nt")
    monkeypatch.setenv("LOCALAPPDATA", "C:/Users/test/AppData/Local")
    assert resolve_log_dir().replace("\\", "/") == "C:/Users/test/AppData/Local/Bobodan/logs"
