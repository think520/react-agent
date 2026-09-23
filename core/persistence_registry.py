"""Persistence store registry (R0.6, modeled on openhanako's store registry).

Every file the product writes that survives a restart must be declared
here: where it lives, what owns it, and whether it is rebuildable. The
tripwire test (tests/test_persistence_tripwire.py) scans the Python source
for store filenames and fails when someone introduces a store without
declaring it — the "where did this data come from / can we delete it"
question must always have an answer.

Fields:
- owner: module primarily responsible for reading/writing it
- scope: "library" (inside a library workspace) or "global" (~/.bobodan)
- format: sqlite | json | jsonl | directory
- rebuildable: True = safely derivable from other stores/originals;
  False = user data that must never be silently deleted (migrations
  and explicit user action only)
- purpose: one line a maintainer can act on
"""

from __future__ import annotations

from typing import Any

STORES: dict[str, dict[str, Any]] = {
    # --- SQLite stores -----------------------------------------------------
    "knowledge.db": {
        "owner": "rag/sqlite_store.py",
        "scope": "library",
        "format": "sqlite",
        "rebuildable": True,  # re-indexed from original materials
        "purpose": "RAG truth source: documents, chunks, FTS index, retrieval records",
    },
    "events.db": {
        "owner": "core/event_log.py",
        "scope": "library",
        "format": "sqlite",
        "rebuildable": True,  # reconnect log; losing it only costs a re-render
        "purpose": "Append-only SSE event log for reconnect replay (P1-17)",
    },
    "embedding_signature.json": {
        "owner": "rag/embedding_signature.py",
        "scope": "library",
        "format": "json",
        "rebuildable": True,  # re-written by the next sync; losing it just disables the guard
        "purpose": "Which provider/model/dimension built the vectors in this library (G2)",
    },
    "bobodan.db": {
        "owner": "memory/personal_store.py",
        "scope": "library",
        "format": "sqlite",
        "rebuildable": False,
        "purpose": "Per-library personal knowledge, candidates, learning events",
    },
    "concept_graph.db": {
        "owner": "graph/concept_store.py",
        "scope": "library",
        "format": "sqlite",
        "rebuildable": False,
        "purpose": "User-reviewed concept graph: concepts, relationships, evidence, candidates, positions",
    },
    "personal-knowledge.db": {
        "owner": "memory/personal_store.py",
        "scope": "global",
        "format": "sqlite",
        "rebuildable": False,
        "purpose": "Global (cross-library) confirmed personal knowledge",
    },
    "usage.db": {
        "owner": "service/usage_service.py",
        "scope": "global",
        "format": "sqlite",
        "rebuildable": False,
        "purpose": "LLM usage ledger (request metadata, tokens, errors)",
    },
    "research.db": {
        "owner": "research/",
        "scope": "library",
        "format": "sqlite",
        "rebuildable": False,
        "purpose": "Web research: searches, source candidates, immutable evidence snapshots",
    },
    # --- Global JSON config -------------------------------------------------
    "provider.json": {
        "owner": "providers/catalog.py",
        "scope": "global",
        "format": "json",
        "rebuildable": False,
        "purpose": "Provider catalog and API keys (P5G.4)",
    },
    "preferences.json": {
        "owner": "service/preferences_service.py",
        "scope": "global",
        "format": "json",
        "rebuildable": False,
        "purpose": "User preferences (schema-versioned, atomic writes)",
    },
    "libraries.json": {
        "owner": "service/library_service.py",
        "scope": "global",
        "format": "json",
        "rebuildable": False,
        "purpose": "Library registry (ids, names, paths, active selection)",
    },
    "settings-proposals.json": {
        "owner": "service/preferences_service.py",
        "scope": "global",
        "format": "json",
        "rebuildable": True,
        "purpose": "Pending conversational settings proposals",
    },
    "server-info.json": {
        "owner": "scripts/dev.py",
        "scope": "global",
        "format": "json",
        "rebuildable": True,
        "purpose": "Dev-stack handshake file (port/pid) for scripts and tests",
    },
    # --- Library-scoped state ------------------------------------------------
    "source_roots.json": {
        "owner": "service/kb_service.py",
        "scope": "library",
        "format": "json",
        "rebuildable": False,
        "purpose": "Registered vault/course source roots for syncing",
    },
    "sync_state.json": {
        "owner": "rag/",
        "scope": "library",
        "format": "json",
        "rebuildable": True,
        "purpose": "Incremental sync bookkeeping (derived)",
    },
    "import_report.json": {
        "owner": "service/kb_service.py",
        "scope": "library",
        "format": "json",
        "rebuildable": True,
        "purpose": "Result report of the most recent import run",
    },
    "page-archives.json": {
        "owner": "service/kb_service.py",
        "scope": "library",
        "format": "json",
        "rebuildable": False,
        "purpose": "Index of archived Wiki pages",
    },
    "manifest.json": {
        "owner": "service/document_edit_service.py",
        "scope": "library",
        "format": "json",
        "rebuildable": False,
        "purpose": "Per-document checkpoint manifest (last 10 edit versions)",
    },
    "cache.db": {
        "owner": "wiki/orchestration.py",
        "scope": "library",
        "format": "sqlite",
        "rebuildable": True,
        "purpose": "Wiki orchestration LLM cache (derived, safe to delete)",
    },
    "checkpoint.json": {
        "owner": "wiki/workflow.py",
        "scope": "library",
        "format": "json",
        "rebuildable": False,
        "purpose": "Wiki plan checkpoint (resume state and user draft decisions)",
    },
    "source_registry.json": {
        "owner": "wiki/schema.py",
        "scope": "library",
        "format": "json",
        "rebuildable": True,
        "purpose": "Wiki page-to-source registry (deterministically rebuildable from pages)",
    },
    "tasks.json": {
        "owner": "wiki/reliability.py",
        "scope": "library",
        "format": "json",
        "rebuildable": True,
        "purpose": "Wiki task persistence for resume/retry (re-scannable from disk)",
    },
    # --- Legacy (migration source only, never written at runtime) -----------
    "graph_store.json": {
        "owner": "web/backend (lazy migration detection only)",
        "scope": "library",
        "format": "json",
        "rebuildable": False,
        "purpose": "LEGACY concept graph; read for migration preview, archived after import",
    },
}
