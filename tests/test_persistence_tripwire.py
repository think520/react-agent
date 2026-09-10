"""Tripwire: every persistent store filename used in Python source must be
declared in core/persistence_registry.py (R0.6).

Scans product code for `<name>.db` / `<name>.json` literals and fails when
an undeclared store appears, so "what writes this file / can it be deleted"
always has an answer before the store ships. Tests, scripts of other tools
and docs are not scanned.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.persistence_registry import STORES

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [
    "service", "rag", "graph", "memory", "knowledge", "core",
    "web/backend", "research", "quiz", "learning", "cli", "providers",
    "obsidian", "wiki", "scripts", "mcp_client",
]
STORE_NAME_RE = re.compile(r"[\"']([a-z][a-z0-9_-]*\.(?:db|sqlite|json))[\"']")
_IGNORE = {
    # Not product data stores: docs/config of other tools, test fixtures.
    "package", "package-lock", "tsconfig", "vitest", "playwright",
    "eslint", "pyproject", "requirements", "server-info-template",
}


def _declared_names() -> set[str]:
    return set(STORES)


def _scan_store_names() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for scan_dir in SCAN_DIRS:
        base = REPO_ROOT / scan_dir
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in STORE_NAME_RE.finditer(text):
                store = match.group(1)
                if store in _IGNORE:
                    continue
                found.setdefault(store, []).append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))
    return found


def test_every_store_filename_in_source_is_declared():
    undeclared = {
        store: files
        for store, files in _scan_store_names().items()
        if store not in _declared_names()
    }
    assert not undeclared, (
        "Undeclared persistent stores found in source. Add them to "
        "core/persistence_registry.py (owner/scope/rebuildable/purpose) "
        "or rename if they are not persistent stores:\n"
        + "\n".join(f"  {store}: {files[0]}" for store, files in sorted(undeclared.items()))
    )


def test_registry_entries_are_well_formed():
    required = {"owner", "scope", "format", "rebuildable", "purpose"}
    for name, entry in STORES.items():
        missing = required - set(entry)
        assert not missing, f"{name}: missing registry fields {missing}"
        assert entry["scope"] in {"library", "global"}, f"{name}: bad scope"
        assert isinstance(entry["rebuildable"], bool), f"{name}: rebuildable must be bool"


def test_declared_stores_are_referenced_somewhere():
    """No stale registry entries: every declared store name must appear in
    the scanned source (guards against renaming a store and leaving a ghost
    declaration behind)."""
    found = _scan_store_names()
    stale = sorted(set(STORES) - set(found))
    assert not stale, (
        f"Registry entries no longer referenced in source: {stale}. "
        "Remove them or restore the store."
    )
