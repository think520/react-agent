"""SQLite + FTS5 storage layer for RAG v2.

Stores documents, chunks, FTS5 full-text index, directory entries, and retrieval logs.
SQLite is the truth source — Qdrant failures never roll back SQLite writes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from rag.schema import RetrievalHit


def _stable_hash(text: str) -> str:
    """Deterministic hash for document_id (source path) and chunk_id."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class KBSQLiteStore:
    """SQLite + FTS5 knowledge base storage."""

    def __init__(self, workspace: str):
        self.workspace = Path(workspace)
        self.db_path = self.workspace / ".knowledge" / "knowledge.db"
        self._conn: sqlite3.Connection | None = None

    # ── connection ──────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── schema ──────────────────────────────────────────────────────────

    def init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_conn()
        conn.executescript(_SCHEMA_SQL)

    # ── document CRUD ───────────────────────────────────────────────────

    def upsert_document(
        self,
        document_id: str,
        source: str,
        content_hash: str,
        *,
        path: str | None = None,
        kind: str | None = None,
        title: str | None = None,
        course: str | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        vector_status: str = "pending",
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO documents
                (id, source, path, kind, title, course, tags_json, summary,
                 content_hash, vector_status, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(id) DO UPDATE SET
                 source=excluded.source, path=excluded.path, kind=excluded.kind,
                 title=excluded.title, course=excluded.course,
                 tags_json=excluded.tags_json, summary=excluded.summary,
                 content_hash=excluded.content_hash,
                 vector_status=excluded.vector_status,
                 updated_at=datetime('now')""",
            (
                document_id, source, path, kind, title, course,
                json.dumps(tags or []), summary, content_hash, vector_status,
            ),
        )
        conn.commit()

    def delete_document(self, document_id: str) -> None:
        """Delete document and cascade to chunks, fts, directory entries."""
        conn = self._get_conn()
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        conn.commit()

    def get_document_id_by_source(self, source: str) -> str | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id FROM documents WHERE source = ?", (source,)
        ).fetchone()
        return row["id"] if row else None

    def get_document(self, document_id: str) -> dict | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_documents(self, course: str | None = None) -> list[dict]:
        conn = self._get_conn()
        if course:
            rows = conn.execute(
                "SELECT * FROM documents WHERE course = ? ORDER BY source",
                (course,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY source"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── chunk CRUD ──────────────────────────────────────────────────────

    def insert_chunks(self, chunks: list[dict]) -> None:
        """Insert chunks. Each dict must have:
        id, document_id, source, chunk_index, text,
        heading_path_json, heading_text, heading_level, section_id,
        chunk_index_in_section, page_start, page_end,
        slide_start, slide_end, char_start, char_end, metadata_json

        Optional: title, course (denormalized from documents for FTS5).
        If not provided, looked up from the documents table.
        """
        conn = self._get_conn()

        # Pre-fetch document title/course for denormalization
        doc_cache: dict[str, tuple[str, str]] = {}

        rows = []
        for c in chunks:
            doc_id = c["document_id"]
            if doc_id not in doc_cache:
                doc = conn.execute(
                    "SELECT title, course FROM documents WHERE id = ?", (doc_id,)
                ).fetchone()
                doc_cache[doc_id] = (
                    doc["title"] if doc else "",
                    doc["course"] if doc else "",
                )

            title = c.get("title") or doc_cache[doc_id][0]
            course = c.get("course") or doc_cache[doc_id][1]

            rows.append((
                c["id"], c["document_id"], c["source"], c["chunk_index"],
                c["text"], title, course,
                c.get("heading_path_json", "[]"),
                c.get("heading_text", ""), c.get("heading_level", 0),
                c.get("section_id", ""), c.get("chunk_index_in_section", 0),
                c.get("page_start"), c.get("page_end"),
                c.get("slide_start"), c.get("slide_end"),
                c.get("char_start"), c.get("char_end"),
                c.get("metadata_json", "{}"),
            ))

        conn.executemany(
            """INSERT OR REPLACE INTO chunks
                (id, document_id, source, chunk_index, text, title, course,
                 heading_path_json, heading_text, heading_level, section_id,
                 chunk_index_in_section, page_start, page_end,
                 slide_start, slide_end, char_start, char_end, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()

    def delete_chunks_by_document(self, document_id: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM chunks WHERE document_id = ?", (document_id,)
        )
        conn.commit()

    def get_chunk_by_id(self, chunk_id: str) -> dict | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_chunks_by_document(self, document_id: str) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            (document_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_chunks(self, course: str | None = None) -> int:
        conn = self._get_conn()
        if course:
            row = conn.execute(
                """SELECT COUNT(*) as cnt FROM chunks c
                   JOIN documents d ON c.document_id = d.id
                   WHERE d.course = ?""",
                (course,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) as cnt FROM chunks").fetchone()
        return row["cnt"]

    # ── FTS5 search ─────────────────────────────────────────────────────

    def search_fts5(
        self, query: str, top_k: int = 30, course: str | None = None
    ) -> list[RetrievalHit]:
        """Full-text search using FTS5 BM25 ranking."""
        conn = self._get_conn()

        # Build FTS5 query — escape special chars, support multi-word
        fts_query = _build_fts_query(query)
        if not fts_query:
            return []

        if course:
            rows = conn.execute(
                """SELECT c.*, d.title as doc_title, d.course as doc_course,
                          rank as bm25_rank
                   FROM chunks_fts fts
                   JOIN chunks c ON c.rowid = fts.rowid
                   JOIN documents d ON c.document_id = d.id
                   WHERE chunks_fts MATCH ? AND d.course = ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, course, top_k),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT c.*, d.title as doc_title, d.course as doc_course,
                          rank as bm25_rank
                   FROM chunks_fts fts
                   JOIN chunks c ON c.rowid = fts.rowid
                   JOIN documents d ON c.document_id = d.id
                   WHERE chunks_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (fts_query, top_k),
            ).fetchall()

        hits = []
        for i, row in enumerate(rows):
            heading_path = json.loads(row["heading_path_json"]) if row["heading_path_json"] else []
            hits.append(
                RetrievalHit(
                    chunk_id=row["id"],
                    document_id=row["document_id"],
                    source=row["source"],
                    text=row["text"],
                    heading_path=heading_path,
                    heading_text=row["heading_text"] or "",
                    page_start=row["page_start"],
                    page_end=row["page_end"],
                    slide_start=row["slide_start"],
                    slide_end=row["slide_end"],
                    char_start=row["char_start"],
                    char_end=row["char_end"],
                    score=abs(row["bm25_rank"]),  # FTS5 rank is negative (lower = better)
                    retrievers=["fts5"],
                    debug={"fts_rank": i + 1, "bm25_score": row["bm25_rank"]},
                )
            )
        return hits

    # ── vector status ───────────────────────────────────────────────────

    def mark_vector_indexed(self, document_id: str, content_hash: str) -> None:
        conn = self._get_conn()
        conn.execute(
            """UPDATE documents
               SET vector_status = 'indexed', vector_indexed_hash = ?, vector_error = NULL
               WHERE id = ?""",
            (content_hash, document_id),
        )
        conn.commit()

    def mark_vector_error(self, document_id: str, error: str) -> None:
        conn = self._get_conn()
        conn.execute(
            """UPDATE documents
               SET vector_status = 'error', vector_error = ?
               WHERE id = ?""",
            (error, document_id),
        )
        conn.commit()

    def get_pending_vector_documents(self) -> list[dict]:
        """Documents where vector_status != 'indexed' (pending or error)."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM documents WHERE vector_status != 'indexed'"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── directory entries ────────────────────────────────────────────────

    def upsert_directory_entry(
        self,
        document_id: str,
        *,
        title: str | None = None,
        summary: str | None = None,
        keywords: list[str] | None = None,
        source: str | None = None,
        path: str | None = None,
        course: str | None = None,
        chunk_count: int = 0,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO directory_entries
                (document_id, title, summary, keywords_json, source, path, course, chunk_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(document_id) DO UPDATE SET
                 title=excluded.title, summary=excluded.summary,
                 keywords_json=excluded.keywords_json, source=excluded.source,
                 path=excluded.path, course=excluded.course,
                 chunk_count=excluded.chunk_count""",
            (
                document_id, title, summary,
                json.dumps(keywords or []), source, path, course, chunk_count,
            ),
        )
        conn.commit()

    def search_directory(
        self, query: str, top_k: int = 8, course: str | None = None
    ) -> list[dict]:
        """Search directory entries by metadata (title, summary, keywords, source)."""
        conn = self._get_conn()
        fts_query = _build_fts_query(query)
        if not fts_query:
            return []

        # Try FTS5 on directory_entries_fts first, fall back to LIKE
        try:
            if course:
                rows = conn.execute(
                    """SELECT de.*, rank as bm25_rank
                       FROM directory_entries_fts fts
                       JOIN directory_entries de ON de.rowid = fts.rowid
                       WHERE directory_entries_fts MATCH ? AND de.course = ?
                       ORDER BY rank
                       LIMIT ?""",
                    (fts_query, course, top_k),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT de.*, rank as bm25_rank
                       FROM directory_entries_fts fts
                       JOIN directory_entries de ON de.rowid = fts.rowid
                       WHERE directory_entries_fts MATCH ?
                       ORDER BY rank
                       LIMIT ?""",
                    (fts_query, top_k),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            # FTS query syntax error or empty — fall back to LIKE
            pass

        # LIKE fallback
        like_pattern = f"%{query}%"
        if course:
            rows = conn.execute(
                """SELECT * FROM directory_entries
                   WHERE course = ?
                     AND (title LIKE ? OR summary LIKE ? OR keywords_json LIKE ? OR source LIKE ?)
                   LIMIT ?""",
                (course, like_pattern, like_pattern, like_pattern, like_pattern, top_k),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM directory_entries
                   WHERE title LIKE ? OR summary LIKE ? OR keywords_json LIKE ? OR source LIKE ?
                   LIMIT ?""",
                (like_pattern, like_pattern, like_pattern, like_pattern, top_k),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── retrieval log ───────────────────────────────────────────────────

    def log_retrieval(self, query: str, mode: str, result_count: int) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO retrieval_runs (query, mode, result_count, created_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (query, mode, result_count),
        )
        conn.commit()

    # ── bulk operations ─────────────────────────────────────────────────

    def clear_all(self) -> None:
        """Delete all data from all tables (for full reindex)."""
        conn = self._get_conn()
        conn.executescript(
            """DELETE FROM retrieval_runs;
               DELETE FROM directory_entries;
               DELETE FROM chunks;
               DELETE FROM documents;"""
        )
        conn.commit()

    def rebuild_fts(self) -> None:
        """Rebuild FTS5 index from chunks table.

        Drops and recreates the FTS5 table, then re-populates from chunks.
        Title and course are denormalized in chunks table.
        """
        conn = self._get_conn()
        # Drop triggers first (they reference chunks_fts)
        for trig in ("chunks_ai", "chunks_ad", "chunks_au"):
            conn.execute(f"DROP TRIGGER IF EXISTS {trig}")
        conn.execute("DROP TABLE IF EXISTS chunks_fts")
        conn.execute(
            """CREATE VIRTUAL TABLE chunks_fts USING fts5(
                text, title, heading_text, source, course,
                content='chunks',
                content_rowid='rowid'
            )"""
        )
        conn.execute(
            """INSERT INTO chunks_fts(rowid, text, title, heading_text, source, course)
               SELECT rowid, text, title, heading_text, source, course FROM chunks"""
        )
        # Recreate triggers
        conn.execute(_CHUNKS_AI_TRIGGER)
        conn.execute(_CHUNKS_AD_TRIGGER)
        conn.execute(_CHUNKS_AU_TRIGGER)
        conn.commit()

    def get_stats(self) -> dict:
        conn = self._get_conn()
        doc_count = conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()["cnt"]
        chunk_count = conn.execute("SELECT COUNT(*) as cnt FROM chunks").fetchone()["cnt"]
        dir_count = conn.execute("SELECT COUNT(*) as cnt FROM directory_entries").fetchone()["cnt"]
        indexed = conn.execute(
            "SELECT COUNT(*) as cnt FROM documents WHERE vector_status = 'indexed'"
        ).fetchone()["cnt"]
        errored = conn.execute(
            "SELECT COUNT(*) as cnt FROM documents WHERE vector_status = 'error'"
        ).fetchone()["cnt"]
        return {
            "documents": doc_count,
            "chunks": chunk_count,
            "directory_entries": dir_count,
            "vector_indexed": indexed,
            "vector_error": errored,
            "vector_pending": doc_count - indexed - errored,
        }


# ── helpers ─────────────────────────────────────────────────────────────

def _build_fts_query(query: str) -> str:
    """Build FTS5 query from user input.

    Multi-word queries become OR queries for broader recall.
    Special FTS5 characters are escaped.
    """
    # Tokenize: split on whitespace, escape FTS5 special chars
    tokens = query.strip().split()
    if not tokens:
        return ""

    escaped = []
    for t in tokens:
        # Escape FTS5 special characters: " * ( ) AND OR NOT NEAR :
        t = t.replace('"', '""')
        for ch in ("*", "(", ")", ":", "AND", "OR", "NOT", "NEAR"):
            if ch in ("AND", "OR", "NOT", "NEAR"):
                continue  # handle below
            t = t.replace(ch, f'"{ch}"')
        if t:
            escaped.append(f'"{t}"')

    if not escaped:
        return ""

    # OR for broader recall
    return " OR ".join(escaped)


def make_chunk_row(
    chunk_id: str,
    document_id: str,
    source: str,
    chunk_index: int,
    text: str,
    *,
    title: str = "",
    course: str = "",
    heading_path: list[str] | None = None,
    heading_text: str = "",
    heading_level: int = 0,
    section_id: str = "",
    chunk_index_in_section: int = 0,
    page_start: int | None = None,
    page_end: int | None = None,
    slide_start: int | None = None,
    slide_end: int | None = None,
    char_start: int | None = None,
    char_end: int | None = None,
    metadata: dict | None = None,
) -> dict:
    """Build a chunk dict ready for insert_chunks()."""
    return {
        "id": chunk_id,
        "document_id": document_id,
        "source": source,
        "chunk_index": chunk_index,
        "text": text,
        "title": title,
        "course": course,
        "heading_path_json": json.dumps(heading_path or []),
        "heading_text": heading_text,
        "heading_level": heading_level,
        "section_id": section_id,
        "chunk_index_in_section": chunk_index_in_section,
        "page_start": page_start,
        "page_end": page_end,
        "slide_start": slide_start,
        "slide_end": slide_end,
        "char_start": char_start,
        "char_end": char_end,
        "metadata_json": json.dumps(metadata or {}),
    }


def chunk_row_to_hit(row: dict) -> RetrievalHit:
    """Convert a SQLite chunk row to a RetrievalHit."""
    heading_path = json.loads(row["heading_path_json"]) if row.get("heading_path_json") else []
    return RetrievalHit(
        chunk_id=row["id"],
        document_id=row["document_id"],
        source=row["source"],
        text=row["text"],
        heading_path=heading_path,
        heading_text=row.get("heading_text", ""),
        page_start=row.get("page_start"),
        page_end=row.get("page_end"),
        slide_start=row.get("slide_start"),
        slide_end=row.get("slide_end"),
        char_start=row.get("char_start"),
        char_end=row.get("char_end"),
    )


# ── SQL schema ──────────────────────────────────────────────────────────

_CHUNKS_AI_TRIGGER = """CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, title, heading_text, source, course)
    VALUES (new.rowid, new.text, new.title, new.heading_text, new.source, new.course);
END;"""

_CHUNKS_AD_TRIGGER = """CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, title, heading_text, source, course)
    VALUES ('delete', old.rowid, old.text, old.title, old.heading_text, old.source, old.course);
END;"""

_CHUNKS_AU_TRIGGER = """CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, title, heading_text, source, course)
    VALUES ('delete', old.rowid, old.text, old.title, old.heading_text, old.source, old.course);
    INSERT INTO chunks_fts(rowid, text, title, heading_text, source, course)
    VALUES (new.rowid, new.text, new.title, new.heading_text, new.source, new.course);
END;"""

_SCHEMA_SQL = """
-- Document metadata
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL UNIQUE,
    path TEXT,
    kind TEXT,
    title TEXT,
    course TEXT,
    tags_json TEXT,
    summary TEXT,
    content_hash TEXT,
    vector_status TEXT DEFAULT 'pending',
    vector_indexed_hash TEXT,
    vector_error TEXT,
    updated_at TEXT
);

-- Text chunks (title, course denormalized from documents for FTS5)
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    chunk_index INTEGER,
    text TEXT NOT NULL,
    title TEXT,
    course TEXT,
    heading_path_json TEXT,
    heading_text TEXT,
    heading_level INTEGER,
    section_id TEXT,
    chunk_index_in_section INTEGER,
    page_start INTEGER,
    page_end INTEGER,
    slide_start INTEGER,
    slide_end INTEGER,
    char_start INTEGER,
    char_end INTEGER,
    metadata_json TEXT
);

-- FTS5 full-text index (content-synced with chunks table)
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, title, heading_text, source, course,
    content='chunks',
    content_rowid='rowid'
);

-- Directory entries
CREATE TABLE IF NOT EXISTS directory_entries (
    document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    title TEXT,
    summary TEXT,
    keywords_json TEXT,
    source TEXT,
    path TEXT,
    course TEXT,
    chunk_count INTEGER
);

-- Directory FTS5 (content-synced with directory_entries)
CREATE VIRTUAL TABLE IF NOT EXISTS directory_entries_fts USING fts5(
    title, summary, keywords_json, source,
    content='directory_entries',
    content_rowid='rowid'
);

-- Retrieval log
CREATE TABLE IF NOT EXISTS retrieval_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT,
    mode TEXT,
    result_count INTEGER,
    created_at TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source);
CREATE INDEX IF NOT EXISTS idx_documents_course ON documents(course);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_documents_vector_status ON documents(vector_status);

-- FTS5 triggers for chunks
""" + _CHUNKS_AI_TRIGGER + "\n" + _CHUNKS_AD_TRIGGER + "\n" + _CHUNKS_AU_TRIGGER + """

-- FTS5 triggers for directory_entries (insert)
CREATE TRIGGER IF NOT EXISTS dir_ai AFTER INSERT ON directory_entries BEGIN
    INSERT INTO directory_entries_fts(rowid, title, summary, keywords_json, source)
    VALUES (new.rowid, new.title, new.summary, new.keywords_json, new.source);
END;

-- FTS5 triggers for directory_entries (delete)
CREATE TRIGGER IF NOT EXISTS dir_ad AFTER DELETE ON directory_entries BEGIN
    INSERT INTO directory_entries_fts(directory_entries_fts, rowid, title, summary, keywords_json, source)
    VALUES ('delete', old.rowid, old.title, old.summary, old.keywords_json, old.source);
END;

-- FTS5 triggers for directory_entries (update)
CREATE TRIGGER IF NOT EXISTS dir_au AFTER UPDATE ON directory_entries BEGIN
    INSERT INTO directory_entries_fts(directory_entries_fts, rowid, title, summary, keywords_json, source)
    VALUES ('delete', old.rowid, old.title, old.summary, old.keywords_json, old.source);
    INSERT INTO directory_entries_fts(rowid, title, summary, keywords_json, source)
    VALUES (new.rowid, new.title, new.summary, new.keywords_json, new.source);
END;
"""
