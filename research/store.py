from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge.paths import knowledge_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResearchStore:
    def __init__(self, workspace: str):
        self.path = Path(knowledge_path(workspace, "research.db"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS searches (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, query TEXT NOT NULL,
                    provider TEXT NOT NULL, status TEXT NOT NULL, diagnostics_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY, search_id TEXT NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
                    title TEXT NOT NULL, url TEXT NOT NULL, canonical_url TEXT NOT NULL,
                    domain TEXT NOT NULL, snippet TEXT NOT NULL, published_at TEXT,
                    rank INTEGER NOT NULL, provider TEXT NOT NULL, quality_hint TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY, canonical_url TEXT NOT NULL, final_url TEXT NOT NULL,
                    title TEXT NOT NULL, domain TEXT NOT NULL, content TEXT NOT NULL,
                    content_hash TEXT NOT NULL, excerpt TEXT NOT NULL, accessed_at TEXT NOT NULL,
                    reader TEXT NOT NULL, UNIQUE(canonical_url, content_hash)
                );
                CREATE TABLE IF NOT EXISTS research_runs (
                    id TEXT PRIMARY KEY, search_id TEXT NOT NULL REFERENCES searches(id),
                    session_id TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_sources (
                    research_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
                    candidate_id TEXT NOT NULL REFERENCES candidates(id), snapshot_id TEXT,
                    status TEXT NOT NULL, error TEXT, PRIMARY KEY(research_id, candidate_id)
                );
            """)

    def create_search(self, session_id: str, query: str, provider: str, diagnostics: dict[str, Any]) -> str:
        search_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO searches VALUES (?, ?, ?, ?, 'ready', ?, ?)",
                (search_id, session_id, query, provider, json.dumps(diagnostics, ensure_ascii=False), _now()),
            )
        return search_id

    def add_candidates(self, search_id: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        with self._connect() as conn:
            for item in candidates:
                candidate_id = uuid.uuid4().hex
                row = {"candidate_id": candidate_id, **item}
                conn.execute(
                    """INSERT INTO candidates
                    (id, search_id, title, url, canonical_url, domain, snippet, published_at, rank, provider, quality_hint)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (candidate_id, search_id, item["title"], item["url"], item["canonical_url"], item["domain"],
                     item.get("snippet", ""), item.get("published_at"), item.get("rank", 0), item["provider"], item["quality_hint"]),
                )
                rows.append(row)
        return rows

    def get_search(self, search_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            search = conn.execute("SELECT * FROM searches WHERE id = ?", (search_id,)).fetchone()
            if not search:
                return None
            candidates = conn.execute("SELECT * FROM candidates WHERE search_id = ? ORDER BY rank", (search_id,)).fetchall()
        return {**dict(search), "diagnostics": json.loads(search["diagnostics_json"]), "candidates": [dict(row) for row in candidates]}

    def create_research(self, search_id: str, session_id: str) -> str:
        research_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute("INSERT INTO research_runs VALUES (?, ?, ?, 'fetching', ?)", (research_id, search_id, session_id, _now()))
        return research_id

    def save_snapshot(self, canonical: str, snapshot, excerpt: str) -> str:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM snapshots WHERE canonical_url = ? AND content_hash = ?",
                (canonical, snapshot.content_hash),
            ).fetchone()
            if existing:
                return str(existing["id"])
            snapshot_id = uuid.uuid4().hex
            try:
                conn.execute(
                    """INSERT INTO snapshots
                    (id, canonical_url, final_url, title, domain, content, content_hash, excerpt, accessed_at, reader)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (snapshot_id, canonical, snapshot.final_url, snapshot.title, snapshot.domain, snapshot.content,
                     snapshot.content_hash, excerpt, _now(), snapshot.reader),
                )
            except sqlite3.IntegrityError:
                existing = conn.execute(
                    "SELECT id FROM snapshots WHERE canonical_url = ? AND content_hash = ?",
                    (canonical, snapshot.content_hash),
                ).fetchone()
                if existing:
                    return str(existing["id"])
                raise
        return snapshot_id

    def add_research_source(self, research_id: str, candidate_id: str, status: str, snapshot_id: str | None = None, error: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO research_sources VALUES (?, ?, ?, ?, ?)",
                (research_id, candidate_id, snapshot_id, status, error),
            )

    def finish_research(self, research_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE research_runs SET status = ? WHERE id = ?", (status, research_id))
            conn.execute("UPDATE searches SET status = ? WHERE id = (SELECT search_id FROM research_runs WHERE id = ?)", ("used" if status in {"ready", "partial"} else "failed", research_id))

    def get_research(self, research_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            run = conn.execute("SELECT * FROM research_runs WHERE id = ?", (research_id,)).fetchone()
            if not run:
                return None
            rows = conn.execute("""
                SELECT rs.status, rs.error, c.id AS candidate_id, c.url, c.title AS candidate_title,
                       s.id AS snapshot_id, s.final_url, s.title, s.domain, s.excerpt,
                       s.accessed_at, s.reader
                FROM research_sources rs
                JOIN candidates c ON c.id = rs.candidate_id
                LEFT JOIN snapshots s ON s.id = rs.snapshot_id
                WHERE rs.research_id = ? ORDER BY c.rank
            """, (research_id,)).fetchall()
        return {**dict(run), "sources": [dict(row) for row in rows]}

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        return dict(row) if row else None
