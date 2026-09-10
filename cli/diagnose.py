"""bobodan diagnose — read-only health report for bug reports (R0.5).

Prints a redacted, one-screen summary of the local installation: app data
home, provider catalog (names + configured flags, never keys), library
registry, per-library store counts, and log-file pointers. Every section
fails soft: a broken store prints as unavailable instead of crashing the
report. Output is safe to paste into an issue.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

SECTION_RULE = "-" * 62


def _section(title: str) -> None:
    print(f"\n{SECTION_RULE}\n{title}\n{SECTION_RULE}")


def _kv(key: str, value: Any) -> None:
    print(f"  {key:<24} {value}")


def _sqlite_counts(db_path: Path, queries: dict[str, str]) -> dict[str, Any]:
    """Run scalar COUNT queries against a SQLite file; fail soft per query."""
    import sqlite3

    out: dict[str, Any] = {}
    if not db_path.exists():
        return {"status": "missing"}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for label, query in queries.items():
            try:
                out[label] = con.execute(query).fetchone()[0]
            except Exception as exc:  # noqa: BLE001 — diagnostics never crash
                out[label] = f"error: {exc}"
    finally:
        con.close()
    return out


def _diagnose_providers() -> None:
    _section("AI Providers (~/.bobodan/provider.json)")
    try:
        from providers.catalog import load_catalog, resolve_home

        catalog = load_catalog()
        providers = catalog.get("providers", {})
        _kv("catalog path", os.path.join(resolve_home(), "provider.json"))
        if not providers:
            print("  (no providers configured)")
        for name, entry in providers.items():
            has_key = bool(entry.get("api_key"))
            models = entry.get("models") or []
            model_label = entry.get("model") or (f"{len(models)} models" if models else "no default model")
            _kv(name, f"configured={has_key}, default={model_label}")
    except Exception as exc:  # noqa: BLE001
        _kv("unavailable", str(exc))


def _diagnose_libraries() -> None:
    _section("Libraries (registry)")
    try:
        from service.library_service import LibraryService

        service = LibraryService()
        registry = service.list_libraries()
        libraries = registry.get("libraries", [])
        if not libraries:
            print("  (no libraries registered)")
        resolved = []
        for record in libraries:
            try:
                full = service.resolve(record.get("library_id"))
                path = full.get("path") if full else None
            except Exception as exc:  # noqa: BLE001 — folder moved/deleted
                path = f"unavailable: {exc}"
            _kv(record.get("name", "?"), f"path={path}  available={record.get('available')}")
            if isinstance(path, str):
                resolved.append((record, Path(path)))
    except Exception as exc:  # noqa: BLE001
        _kv("unavailable", str(exc))
        return

    for record, path in resolved:
        name = record.get("name") or path.name
        _section(f"Library「{name}」 stores")
        knowledge = _sqlite_counts(path / ".bobodan" / "knowledge.db" if (path / ".bobodan" / "knowledge.db").exists() else path / "knowledge.db", {
            "documents": "SELECT COUNT(*) FROM documents",
            "chunks": "SELECT COUNT(*) FROM chunks",
        })
        _kv("knowledge.db", knowledge)
        graph_counts = _sqlite_counts(_find_concept_db(path), {
            "concepts": "SELECT COUNT(*) FROM concepts",
            "relationships": "SELECT COUNT(*) FROM relationships",
        })
        _kv("concept_graph.db", graph_counts)
        sessions_dir = path / ".bobodan" / "sessions"
        if not sessions_dir.exists():
            sessions_dir = path / ".session"
        session_count = len(list(sessions_dir.glob("*.json"))) if sessions_dir.exists() else "n/a"
        _kv("chat sessions", session_count)


def _find_concept_db(library_path: Path) -> Path:
    for candidate in (library_path / ".bobodan" / "concept_graph.db", library_path / "concept_graph.db"):
        if candidate.exists():
            return candidate
    return library_path / ".bobodan" / "concept_graph.db"


def _diagnose_runtime() -> None:
    _section("Runtime")
    from providers.catalog import resolve_home

    home = resolve_home()
    _kv("bobodan home", home)
    _kv("python", sys.version.split()[0])
    _kv("platform", f"{platform.system()} {platform.release()}")
    server_info = Path(home) / "server-info.json"
    if server_info.exists():
        try:
            info = json.loads(server_info.read_text(encoding="utf-8"))
            _kv("dev server-info", f"port={info.get('port')}, started={info.get('started_at')}")
        except Exception as exc:  # noqa: BLE001
            _kv("dev server-info", f"unreadable: {exc}")
    else:
        _kv("dev server-info", "(not running via scripts/dev.py)")
    logs_dir = Path(os.getenv("LOCALAPPDATA", "")) / "Bobodan" / "logs"
    if logs_dir.exists():
        logs = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        for log_file in logs[:3]:
            size_kb = max(1, log_file.stat().st_size // 1024)
            _kv("log", f"{log_file} ({size_kb} KB)")
    else:
        _kv("logs", f"none found in {logs_dir}")


def run_diagnose() -> int:
    print("Bobodan diagnose — paste everything below into your issue report.")
    print("(No API keys or library contents are included.)")
    _diagnose_runtime()
    _diagnose_providers()
    _diagnose_libraries()
    print()
    return 0
