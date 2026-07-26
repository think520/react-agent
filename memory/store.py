"""SQLite index with FTS5 full-text search for memory system.

Stores chunk-level indexes for both daily and permanent memories.
FTS5 provides fast keyword search; the original vector store is kept as fallback.
"""

import hashlib
import os
import sqlite3
from datetime import datetime, timezone

DB_FILENAME = "memory.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    source TEXT NOT NULL,
    text TEXT NOT NULL,
    date TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recall_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id TEXT NOT NULL,
    recalled_at TEXT NOT NULL,
    query_hash TEXT
);
"""


def _make_chunk_id(path: str, text: str) -> str:
    """Deterministic chunk id from path + text hash."""
    h = hashlib.sha256(f"{path}:{text}".encode()).hexdigest()[:12]
    return f"mem_{h}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MemoryIndexStore:
    """SQLite-backed memory index with FTS5 full-text search."""

    def __init__(self, workspace: str, base_dir: str = ".bobodan"):
        self.base_dir = os.path.join(workspace, base_dir)
        self.db_path = os.path.join(self.base_dir, DB_FILENAME)
        os.makedirs(self.base_dir, exist_ok=True)
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA_SQL)
            # FTS5 virtual table — created separately since it's a virtual table
            conn.execute(
                """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                   USING fts5(text, path, source, content='chunks', content_rowid='rowid',
                              tokenize='unicode61')"""
            )
            # Triggers to keep FTS in sync with chunks table
            conn.execute(
                """CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO chunks_fts(rowid, text, path, source)
                    VALUES (new.rowid, new.text, new.path, new.source);
                END"""
            )
            conn.execute(
                """CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, text, path, source)
                    VALUES ('delete', old.rowid, old.text, old.path, old.source);
                END"""
            )
            conn.execute(
                """CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
                    INSERT INTO chunks_fts(chunks_fts, rowid, text, path, source)
                    VALUES ('delete', old.rowid, old.text, old.path, old.source);
                    INSERT INTO chunks_fts(rowid, text, path, source)
                    VALUES (new.rowid, new.text, new.path, new.source);
                END"""
            )
            conn.commit()
        finally:
            conn.close()

    def index_chunk(self, chunk_id: str, path: str, source: str,
                    text: str, date: str | None = None) -> None:
        """Add or update a chunk in the index."""
        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO chunks (id, path, source, text, date, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (chunk_id, path, source, text, date, _now_iso()),
            )
            conn.commit()
        finally:
            conn.close()

    def index_text(self, path: str, source: str, text: str,
                   date: str | None = None) -> str:
        """Index a text block, auto-generating chunk id. Returns chunk id."""
        chunk_id = _make_chunk_id(path, text)
        self.index_chunk(chunk_id, path, source, text, date)
        return chunk_id

    def remove_by_path(self, path: str) -> int:
        """Remove all chunks for a given file path. Returns count removed."""
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM chunks WHERE path = ?", (path,))
            removed = cur.rowcount
            conn.commit()
            return removed
        finally:
            conn.close()

    def remove_by_source(self, source: str) -> int:
        """Remove all chunks with matching source prefix. Returns count removed."""
        conn = self._connect()
        try:
            cur = conn.execute(
                "DELETE FROM chunks WHERE source LIKE ?",
                (f"{source}%",),
            )
            removed = cur.rowcount
            conn.commit()
            return removed
        finally:
            conn.close()

    def search_fts(self, query: str, limit: int = 10,
                   source_filter: str | None = None) -> list[dict]:
        """FTS5 keyword search. Returns list of {id, path, source, text, date, rank}."""
        conn = self._connect()
        try:
            sql = """
                SELECT c.id, c.path, c.source, c.text, c.date, rank
                FROM chunks_fts fts
                JOIN chunks c ON c.rowid = fts.rowid
                WHERE chunks_fts MATCH ?
            """
            params: list = [query]
            if source_filter:
                sql += " AND c.source = ?"
                params.append(source_filter)
            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "id": r["id"],
                    "path": r["path"],
                    "source": r["source"],
                    "text": r["text"],
                    "date": r["date"],
                    "rank": r["rank"],
                }
                for r in rows
            ]
        except sqlite3.OperationalError:
            # FTS5 query syntax error — fall back to LIKE
            return self._search_like(query, limit, source_filter)
        finally:
            conn.close()

    def _search_like(self, query: str, limit: int = 10,
                     source_filter: str | None = None) -> list[dict]:
        """Fallback LIKE search when FTS5 query syntax fails."""
        conn = self._connect()
        try:
            sql = "SELECT id, path, source, text, date FROM chunks WHERE text LIKE ?"
            params: list = [f"%{query}%"]
            if source_filter:
                sql += " AND source = ?"
                params.append(source_filter)
            sql += " LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            return [
                {
                    "id": r["id"],
                    "path": r["path"],
                    "source": r["source"],
                    "text": r["text"],
                    "date": r["date"],
                    "rank": 0,
                }
                for r in rows
            ]
        finally:
            conn.close()

    def record_recall(self, chunk_id: str, query_hash: str | None = None) -> None:
        """Record that a chunk was recalled (for promotion scoring)."""
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO recall_log (chunk_id, recalled_at, query_hash) VALUES (?, ?, ?)",
                (chunk_id, _now_iso(), query_hash),
            )
            conn.commit()
        finally:
            conn.close()

    def get_recall_count(self, path_prefix: str) -> int:
        """Get total recall count for chunks matching a path prefix."""
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT COUNT(*) as cnt FROM recall_log rl
                   JOIN chunks c ON rl.chunk_id = c.id
                   WHERE c.path LIKE ?""",
                (f"{path_prefix}%",),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()






    def count_chunks(self, source: str | None = None) -> int:
        """Count chunks, optionally filtered by source."""
        conn = self._connect()
        try:
            if source:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM chunks WHERE source = ?", (source,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) as cnt FROM chunks").fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def get_stats(self) -> dict:
        """Return memory index statistics."""
        conn = self._connect()
        try:
            total = conn.execute("SELECT COUNT(*) as cnt FROM chunks").fetchone()["cnt"]
            daily = conn.execute(
                "SELECT COUNT(*) as cnt FROM chunks WHERE source = 'daily'"
            ).fetchone()["cnt"]
            permanent = conn.execute(
                "SELECT COUNT(*) as cnt FROM chunks WHERE source = 'permanent'"
            ).fetchone()["cnt"]
            recalls = conn.execute("SELECT COUNT(*) as cnt FROM recall_log").fetchone()["cnt"]
            return {
                "total_chunks": total,
                "daily_chunks": daily,
                "permanent_chunks": permanent,
                "total_recalls": recalls,
            }
        finally:
            conn.close()
