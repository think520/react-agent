"""Tests for `bobodan diagnose` (cli/diagnose.py, R0.5).

The report is meant to be pasted into public issues, so the critical
contract is: it never prints API keys, and every section fails soft.
"""

import json
from pathlib import Path

from cli import diagnose as diagnose_module


def _capture(capsys):
    out = capsys.readouterr().out
    return out


def test_run_diagnose_reports_sections_and_exits_zero(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("BOBODAN_HOME", str(tmp_path))
    (tmp_path / "provider.json").write_text(json.dumps({
        "version": 1,
        "providers": {
            "deepseek": {"name": "deepseek", "api_key": "sk-SUPERSECRET", "model": "deepseek-chat"},
        },
    }), encoding="utf-8")

    code = diagnose_module.run_diagnose()
    out = _capture(capsys)

    assert code == 0
    assert "Runtime" in out
    assert "AI Providers" in out
    assert "deepseek" in out
    # Redaction contract: the report must never contain the key itself.
    assert "sk-SUPERSECRET" not in out
    assert "configured=True" in out


def test_provider_section_fails_soft_on_broken_catalog(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("BOBODAN_HOME", str(tmp_path))
    (tmp_path / "provider.json").write_text("{not json", encoding="utf-8")

    code = diagnose_module.run_diagnose()
    out = _capture(capsys)

    # load_catalog treats a corrupt catalog as empty upstream; the section
    # must still render and the command must not crash.
    assert code == 0
    assert "AI Providers" in out


def test_library_section_fails_soft_when_folder_missing(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("BOBODAN_HOME", str(tmp_path))
    monkeypatch.setattr(diagnose_module, "_diagnose_runtime", lambda: None)
    # Point the registry at a library whose folder no longer exists.
    home = Path(tmp_path)
    (home / "libraries.json").write_text(json.dumps({
        "active_library_id": "lib-1",
        "libraries": [{"library_id": "lib-1", "name": "ghost", "created_at": "", "last_opened_at": "", "active": True, "available": True}],
    }), encoding="utf-8")

    monkeypatch.setattr("service.library_service.LibraryService", lambda: _FakeService(home))
    code = diagnose_module.run_diagnose()
    out = _capture(capsys)

    assert code == 0
    assert "ghost" in out


class _FakeService:
    def __init__(self, home: Path) -> None:
        self._home = home

    def list_libraries(self):
        return {"libraries": [{"library_id": "lib-1", "name": "ghost", "available": True}]}

    def resolve(self, library_id):
        return {"library_id": "lib-1", "name": "ghost", "path": str(self._home / "does-not-exist")}
