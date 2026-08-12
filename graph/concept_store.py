"""Concept graph store — P5E.6 knowledge map backend.

SQLite-backed store for concept graph data: concepts, relationships,
evidence, candidates, and persisted node positions.

Tables
------
concepts          — confirmed concept nodes (core/detail/cluster)
relationships     — confirmed edges between concepts
evidence          — source evidence anchoring relationships
concept_candidates — LLM-extracted candidates awaiting user review
concept_extraction_runs — durable status for long-running extraction jobs
concept_positions  — per-concept canvas positions (x, y) saved by user
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

from core.db import open_connection


_DDL = """
CREATE TABLE IF NOT EXISTS concepts (
    concept_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    level        TEXT NOT NULL DEFAULT 'core',   -- cluster | core | detail
    definition   TEXT DEFAULT '',
    aliases      TEXT DEFAULT '[]',              -- JSON list of str
    topic_ids    TEXT DEFAULT '[]',              -- JSON list of cluster concept_id
    note         TEXT DEFAULT '',
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_concepts_name ON concepts (name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS relationships (
    rel_id       TEXT PRIMARY KEY,
    from_id      TEXT NOT NULL REFERENCES concepts(concept_id),
    to_id        TEXT NOT NULL REFERENCES concepts(concept_id),
    rel_type     TEXT NOT NULL,                 -- 属于|前置知识|组成部分|对比|应用于|来源于|user:custom
    evidence_level TEXT NOT NULL DEFAULT 'user', -- source|cross|user|ai
    note         TEXT DEFAULT '',
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_rel_from ON relationships (from_id);
CREATE INDEX IF NOT EXISTS ix_rel_to   ON relationships (to_id);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id   TEXT PRIMARY KEY,
    rel_id        TEXT NOT NULL REFERENCES relationships(rel_id) ON DELETE CASCADE,
    document_id   TEXT NOT NULL,
    chunk_id      TEXT,
    document_title TEXT DEFAULT '',
    excerpt       TEXT DEFAULT '',
    location_type TEXT DEFAULT '',              -- page|slide|heading|line
    location_value TEXT DEFAULT '',             -- e.g. "3" or "§ Introduction"
    location_stale INTEGER NOT NULL DEFAULT 0, -- 1 if source changed
    created_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ev_rel ON evidence (rel_id);

CREATE TABLE IF NOT EXISTS concept_candidates (
    candidate_id  TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    level         TEXT NOT NULL DEFAULT 'core',
    definition    TEXT DEFAULT '',
    confidence    TEXT NOT NULL DEFAULT 'medium', -- high|medium|low
    source_doc_id TEXT DEFAULT '',
    source_doc_title TEXT DEFAULT '',
    excerpt       TEXT DEFAULT '',
    suggested_rels TEXT DEFAULT '[]',           -- JSON [{rel_type, to_name}]
    status        TEXT NOT NULL DEFAULT 'pending', -- pending|confirmed|rejected|label
    suppressed_until REAL,                      -- Unix ts, null = not suppressed
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS concept_extraction_runs (
    run_id         TEXT PRIMARY KEY,
    document_id    TEXT NOT NULL,
    document_title TEXT DEFAULT '',
    content_version TEXT DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'queued', -- queued|running|completed|completed_with_warnings|failed
    stage          TEXT DEFAULT '',
    stored_count   INTEGER NOT NULL DEFAULT 0,
    warnings       TEXT DEFAULT '[]',
    failed_sections TEXT DEFAULT '[]',
    error          TEXT DEFAULT '',
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_extraction_runs_document
    ON concept_extraction_runs (document_id, created_at DESC);

CREATE TABLE IF NOT EXISTS concept_positions (
    concept_id TEXT NOT NULL,
    view_id    TEXT NOT NULL DEFAULT 'default',
    x          REAL NOT NULL DEFAULT 0,
    y          REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    PRIMARY KEY (concept_id, view_id)
);
"""


class ConceptStore:
    """SQLite-backed concept graph store."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self):
        return open_connection(self._db_path, busy_timeout_ms=15000)

    def _ensure_schema(self) -> None:
        with self._connect() as con:
            con.executescript(_DDL)
            run_columns = {
                row["name"]
                for row in con.execute("PRAGMA table_info(concept_extraction_runs)")
            }
            if "content_version" not in run_columns:
                con.execute(
                    "ALTER TABLE concept_extraction_runs "
                    "ADD COLUMN content_version TEXT DEFAULT ''"
                )
            if "stage" not in run_columns:
                con.execute(
                    "ALTER TABLE concept_extraction_runs "
                    "ADD COLUMN stage TEXT DEFAULT ''"
                )
            if "warnings" not in run_columns:
                con.execute(
                    "ALTER TABLE concept_extraction_runs "
                    "ADD COLUMN warnings TEXT DEFAULT '[]'"
                )
            if "failed_sections" not in run_columns:
                con.execute(
                    "ALTER TABLE concept_extraction_runs "
                    "ADD COLUMN failed_sections TEXT DEFAULT '[]'"
                )
            if "started_at" not in run_columns:
                con.execute(
                    "ALTER TABLE concept_extraction_runs "
                    "ADD COLUMN started_at REAL"
                )
            evidence_columns = {
                row["name"]
                for row in con.execute("PRAGMA table_info(evidence)")
            }
            if "chunk_id" not in evidence_columns:
                con.execute("ALTER TABLE evidence ADD COLUMN chunk_id TEXT")

    # ------------------------------------------------------------------
    # Concepts
    # ------------------------------------------------------------------

    def upsert_concept(
        self,
        *,
        concept_id: str | None = None,
        name: str,
        level: str = "core",
        definition: str = "",
        aliases: list[str] | None = None,
        topic_ids: list[str] | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        now = time.time()
        cid = concept_id or f"c-{uuid.uuid4().hex[:12]}"
        with self._connect() as con:
            clash = con.execute(
                "SELECT concept_id FROM concepts "
                "WHERE name = ? COLLATE NOCASE AND concept_id != ?",
                (name, cid),
            ).fetchone()
            if clash:
                # A rename onto an existing concept's name would violate the
                # unique ix_concepts_name index mid-UPDATE and surface as an
                # opaque IntegrityError; pre-check so the service can answer 409.
                raise ValueError(f"concept_name_conflict:{name}")
            con.execute(
                """
                INSERT INTO concepts (concept_id, name, level, definition,
                    aliases, topic_ids, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(concept_id) DO UPDATE SET
                    name = excluded.name,
                    level = excluded.level,
                    definition = excluded.definition,
                    aliases = excluded.aliases,
                    topic_ids = excluded.topic_ids,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (
                    cid,
                    name,
                    level,
                    definition,
                    json.dumps(aliases or []),
                    json.dumps(topic_ids or []),
                    note,
                    now,
                    now,
                ),
            )
        return self.get_concept(cid)  # type: ignore[return-value]

    def get_concept(self, concept_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM concepts WHERE concept_id = ?", (concept_id,)
            ).fetchone()
        return _row_to_concept(row) if row else None

    def get_concept_by_name(self, name: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM concepts WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()
        return _row_to_concept(row) if row else None

    def list_concepts(
        self,
        *,
        level: str | None = None,
        topic_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses, params = [], []
        if level:
            clauses.append("level = ?")
            params.append(level)
        if topic_id:
            # Filter in SQL so the LIMIT applies to the topic-filtered set,
            # not the whole table (concepts beyond the limit used to be
            # silently dropped by the old Python-side filter).
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(concepts.topic_ids) je WHERE je.value = ?)"
            )
            params.append(topic_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as con:
            rows = con.execute(
                f"SELECT * FROM concepts {where} ORDER BY level, name LIMIT ?",
                params + [limit],
            ).fetchall()
        return [_row_to_concept(r) for r in rows]

    def delete_concept(self, concept_id: str) -> bool:
        with self._connect() as con:
            cur = con.execute(
                "DELETE FROM concepts WHERE concept_id = ?", (concept_id,)
            )
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    def upsert_relationship(
        self,
        *,
        rel_id: str | None = None,
        from_id: str,
        to_id: str,
        rel_type: str,
        evidence_level: str = "user",
        note: str = "",
    ) -> dict[str, Any]:
        now = time.time()
        rid = rel_id or f"r-{uuid.uuid4().hex[:12]}"
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO relationships
                    (rel_id, from_id, to_id, rel_type, evidence_level, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rel_id) DO UPDATE SET
                    from_id = excluded.from_id,
                    to_id = excluded.to_id,
                    rel_type = excluded.rel_type,
                    evidence_level = excluded.evidence_level,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (rid, from_id, to_id, rel_type, evidence_level, note, now, now),
            )
        return self.get_relationship(rid)  # type: ignore[return-value]

    def get_relationship(self, rel_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM relationships WHERE rel_id = ?", (rel_id,)
            ).fetchone()
        return dict(row) if row else None

    def relationships_for_concept(self, concept_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """SELECT relationships.*, source.name AS from_name, target.name AS to_name
                   FROM relationships
                   JOIN concepts AS source ON source.concept_id = relationships.from_id
                   JOIN concepts AS target ON target.concept_id = relationships.to_id
                   WHERE from_id = ? OR to_id = ?""",
                (concept_id, concept_id),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_relationships(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """SELECT relationships.*, source.name AS from_name, target.name AS to_name
                   FROM relationships
                   JOIN concepts AS source ON source.concept_id = relationships.from_id
                   JOIN concepts AS target ON target.concept_id = relationships.to_id
                   ORDER BY relationships.created_at"""
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_relationship(self, rel_id: str) -> bool:
        with self._connect() as con:
            cur = con.execute(
                "DELETE FROM relationships WHERE rel_id = ?", (rel_id,)
            )
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    def add_evidence(
        self,
        *,
        rel_id: str,
        document_id: str,
        chunk_id: str | None = None,
        document_title: str = "",
        excerpt: str = "",
        location_type: str = "",
        location_value: str = "",
    ) -> dict[str, Any]:
        now = time.time()
        eid = f"e-{uuid.uuid4().hex[:12]}"
        with self._connect() as con:
            con.execute(
                """INSERT INTO evidence
                   (evidence_id, rel_id, document_id, chunk_id, document_title,
                    excerpt, location_type, location_value, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (eid, rel_id, document_id, chunk_id, document_title,
                 excerpt, location_type, location_value, now),
            )
        return {"evidence_id": eid, "rel_id": rel_id,
                "document_id": document_id, "chunk_id": chunk_id,
                "document_title": document_title,
                "excerpt": excerpt, "location_type": location_type,
                "location_value": location_value, "location_stale": False}

    def evidence_for_relationship(self, rel_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM evidence WHERE rel_id = ?", (rel_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def evidence_for_document(self, document_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM evidence WHERE document_id = ?",
                (document_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_evidence_location(
        self,
        evidence_id: str,
        *,
        chunk_id: str | None,
        location_stale: bool,
    ) -> bool:
        with self._connect() as con:
            cur = con.execute(
                """UPDATE evidence
                   SET chunk_id = ?, location_stale = ?
                   WHERE evidence_id = ?""",
                (chunk_id, int(location_stale), evidence_id),
            )
        return cur.rowcount > 0

    def search_concepts(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        pattern = f"%{query.strip()}%"
        with self._connect() as con:
            rows = con.execute(
                """SELECT * FROM concepts
                   WHERE name LIKE ? COLLATE NOCASE
                      OR aliases LIKE ? COLLATE NOCASE
                   ORDER BY CASE WHEN name = ? COLLATE NOCASE THEN 0 ELSE 1 END,
                            name
                   LIMIT ?""",
                (pattern, pattern, query.strip(), limit),
            ).fetchall()
        return [_row_to_concept(row) for row in rows]

    def graph_status(self) -> dict[str, int]:
        with self._connect() as con:
            concepts = con.execute("SELECT COUNT(*) AS count FROM concepts").fetchone()["count"]
            relationships = con.execute(
                "SELECT COUNT(*) AS count FROM relationships"
            ).fetchone()["count"]
            pending = con.execute(
                """SELECT COUNT(*) AS count FROM concept_candidates
                   WHERE status = 'pending'
                     AND (suppressed_until IS NULL OR suppressed_until <= ?)""",
                (time.time(),),
            ).fetchone()["count"]
            stale = con.execute(
                "SELECT COUNT(*) AS count FROM evidence WHERE location_stale = 1"
            ).fetchone()["count"]
        return {
            "concept_count": concepts,
            "relationship_count": relationships,
            "pending_count": pending,
            "stale_evidence_count": stale,
        }

    # ------------------------------------------------------------------
    # Candidates
    # ------------------------------------------------------------------

    def add_candidate(
        self,
        *,
        name: str,
        level: str = "core",
        definition: str = "",
        confidence: str = "medium",
        source_doc_id: str = "",
        source_doc_title: str = "",
        excerpt: str = "",
        suggested_rels: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        cid = f"cand-{uuid.uuid4().hex[:12]}"
        with self._connect() as con:
            existing = con.execute(
                """SELECT candidate_id FROM concept_candidates
                   WHERE source_doc_id = ? AND name = ? COLLATE NOCASE
                     AND status = 'pending'
                   ORDER BY updated_at DESC LIMIT 1""",
                (source_doc_id, name),
            ).fetchone()
            if existing:
                cid = existing["candidate_id"]
                con.execute(
                    """UPDATE concept_candidates
                       SET level = ?, definition = ?, confidence = ?,
                           source_doc_title = ?, excerpt = ?, suggested_rels = ?,
                           suppressed_until = NULL, updated_at = ?
                       WHERE candidate_id = ?""",
                    (
                        level, definition, confidence, source_doc_title, excerpt,
                        json.dumps(suggested_rels or []), now, cid,
                    ),
                )
            else:
                con.execute(
                    """INSERT INTO concept_candidates
                       (candidate_id, name, level, definition, confidence,
                        source_doc_id, source_doc_title, excerpt,
                        suggested_rels, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        cid, name, level, definition, confidence,
                        source_doc_id, source_doc_title, excerpt,
                        json.dumps(suggested_rels or []), now, now,
                    ),
                )
        return self.get_candidate(cid)  # type: ignore[return-value]

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM concept_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        return _row_to_candidate(row) if row else None

    def get_candidate_by_document_and_name(
        self,
        source_doc_id: str,
        name: str,
    ) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                """SELECT * FROM concept_candidates
                   WHERE source_doc_id = ? AND name = ? COLLATE NOCASE
                   ORDER BY
                     CASE status
                       WHEN 'confirmed' THEN 0
                       WHEN 'rejected' THEN 1
                       WHEN 'label' THEN 2
                       WHEN 'pending' THEN 3
                       ELSE 4
                     END,
                     updated_at DESC
                   LIMIT 1""",
                (source_doc_id, name),
            ).fetchone()
        return _row_to_candidate(row) if row else None

    def list_candidates(
        self,
        *,
        status: str = "pending",
        source_doc_id: str | None = None,
    ) -> list[dict[str, Any]]:
        now = time.time()
        source_clause = " AND source_doc_id = ?" if source_doc_id else ""
        params: list[Any] = [status, now]
        if source_doc_id:
            params.append(source_doc_id)
        with self._connect() as con:
            rows = con.execute(
                f"""SELECT * FROM concept_candidates
                   WHERE status = ?
                     AND (suppressed_until IS NULL OR suppressed_until <= ?)
                     {source_clause}
                   ORDER BY
                     CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                     created_at""",
                params,
            ).fetchall()
        return [_row_to_candidate(r) for r in rows]

    # ------------------------------------------------------------------
    # Extraction runs
    # ------------------------------------------------------------------

    def create_extraction_run(
        self,
        *,
        document_id: str,
        document_title: str = "",
        content_version: str = "",
    ) -> dict[str, Any]:
        now = time.time()
        run_id = f"extract-{uuid.uuid4().hex[:12]}"
        with self._connect() as con:
            con.execute(
                """INSERT INTO concept_extraction_runs
                   (run_id, document_id, document_title, content_version,
                    status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'queued', ?, ?)""",
                (run_id, document_id, document_title, content_version, now, now),
            )
        return self.get_extraction_run(run_id)  # type: ignore[return-value]

    def recover_stale_runs(self, timeout_seconds: int = 600) -> int:
        """Mark queued/running runs without recent activity as interrupted.

        Extraction tasks run inside the process; a backend restart leaves
        their rows stuck in ``running`` forever, so the UI shows an eternal
        spinner. Called lazily on extraction status reads (and at startup)
        so stale runs surface as recoverable ``interrupted`` instead.
        """
        cutoff = time.time() - timeout_seconds
        with self._connect() as con:
            cur = con.execute(
                "UPDATE concept_extraction_runs SET status = 'interrupted', "
                "updated_at = ? "
                "WHERE status IN ('queued', 'running') AND updated_at < ?",
                (time.time(), cutoff),
            )
            return cur.rowcount

    def get_extraction_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM concept_extraction_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return _row_to_run(row) if row else None

    def get_latest_extraction_run(self, document_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                """SELECT * FROM concept_extraction_runs
                   WHERE document_id = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (document_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_latest_extraction_runs(self) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """SELECT runs.*
                   FROM concept_extraction_runs AS runs
                   JOIN (
                       SELECT document_id, MAX(created_at) AS created_at
                       FROM concept_extraction_runs
                       GROUP BY document_id
                   ) AS latest
                     ON latest.document_id = runs.document_id
                    AND latest.created_at = runs.created_at
                   ORDER BY runs.updated_at DESC"""
            ).fetchall()
        return [_row_to_run(row) for row in rows]

    def pending_candidates_count_by_document(self) -> dict[str, int]:
        with self._connect() as con:
            rows = con.execute(
                """SELECT source_doc_id, COUNT(*) AS count
                   FROM concept_candidates
                   WHERE status = 'pending'
                     AND (suppressed_until IS NULL OR suppressed_until <= ?)
                   GROUP BY source_doc_id""",
                (time.time(),),
            ).fetchall()
        return {row["source_doc_id"]: row["count"] for row in rows}

    def update_extraction_run(
        self,
        run_id: str,
        *,
        status: str,
        stored_count: int = 0,
        error: str = "",
        stage: str = "",
        warnings: list[str] | None = None,
        failed_sections: list[dict[str, Any]] | None = None,
    ) -> bool:
        warnings_json = json.dumps(warnings or [], ensure_ascii=False)
        failed_sections_json = json.dumps(failed_sections or [], ensure_ascii=False)
        now = time.time()
        with self._connect() as con:
            # First transition into running records the real start time so the
            # frontend can show honest elapsed time across panel close/reopen.
            if status == "running":
                con.execute(
                    "UPDATE concept_extraction_runs SET started_at = ? "
                    "WHERE run_id = ? AND started_at IS NULL",
                    (now, run_id),
                )
            cur = con.execute(
                """UPDATE concept_extraction_runs
                   SET status = ?, stage = ?, stored_count = ?, warnings = ?, failed_sections = ?, error = ?, updated_at = ?
                   WHERE run_id = ?""",
                (status, stage, stored_count, warnings_json, failed_sections_json, error, now, run_id),
            )
        return cur.rowcount > 0

    def archive_pending_candidates(self, source_doc_id: str) -> int:
        with self._connect() as con:
            cur = con.execute(
                """UPDATE concept_candidates
                   SET status = 'archived', updated_at = ?
                   WHERE source_doc_id = ? AND status = 'pending'""",
                (time.time(), source_doc_id),
            )
        return cur.rowcount

    def update_candidate_status(
        self,
        candidate_id: str,
        status: str,
        *,
        suppressed_until: float | None = None,
    ) -> bool:
        now = time.time()
        with self._connect() as con:
            cur = con.execute(
                """UPDATE concept_candidates
                   SET status = ?, suppressed_until = ?, updated_at = ?
                   WHERE candidate_id = ?""",
                (status, suppressed_until, now, candidate_id),
            )
        return cur.rowcount > 0

    def update_candidate_suggested_rels(
        self,
        candidate_id: str,
        suggested_rels: list[dict[str, Any]],
    ) -> bool:
        with self._connect() as con:
            cur = con.execute(
                """UPDATE concept_candidates
                   SET suggested_rels = ?, updated_at = ?
                   WHERE candidate_id = ?""",
                (json.dumps(suggested_rels, ensure_ascii=False), time.time(), candidate_id),
            )
        return cur.rowcount > 0

    def pending_candidates_count(self) -> int:
        with self._connect() as con:
            row = con.execute(
                """SELECT COUNT(*) FROM concept_candidates
                   WHERE status = 'pending'
                     AND (suppressed_until IS NULL OR suppressed_until <= ?)""",
                (time.time(),),
            ).fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def save_positions(
        self,
        positions: list[dict[str, Any]],
        *,
        view_id: str = "default",
    ) -> None:
        now = time.time()
        with self._connect() as con:
            con.executemany(
                """INSERT INTO concept_positions (concept_id, view_id, x, y, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (concept_id, view_id) DO UPDATE SET
                       x = excluded.x, y = excluded.y, updated_at = excluded.updated_at""",
                [
                    (p["concept_id"], view_id, p["x"], p["y"], now)
                    for p in positions
                ],
            )

    def get_positions(self, *, view_id: str = "default") -> dict[str, dict[str, float]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT concept_id, x, y FROM concept_positions WHERE view_id = ?",
                (view_id,),
            ).fetchall()
        return {r["concept_id"]: {"x": r["x"], "y": r["y"]} for r in rows}

    # ------------------------------------------------------------------
    # Graph state query (used by frontend map view)
    # ------------------------------------------------------------------

    def get_graph_state(
        self,
        *,
        topic_id: str | None = None,
        include_candidates: bool = False,
        view_id: str = "default",
        max_nodes: int = 120,
    ) -> dict[str, Any]:
        """Return a subgraph snapshot suitable for the frontend renderer."""
        concepts = self.list_concepts(topic_id=topic_id, limit=max_nodes)
        concept_ids = {c["concept_id"] for c in concepts}

        # Collect relationships between the loaded concepts only
        rels: list[dict[str, Any]] = []
        if concept_ids:
            with self._connect() as con:
                rows = con.execute(
                    """SELECT * FROM relationships
                       WHERE from_id IN ({ph}) AND to_id IN ({ph})
                    """.format(ph=",".join("?" * len(concept_ids))),
                    list(concept_ids) * 2,
                ).fetchall()
                rels = [dict(r) for r in rows]

        positions = self.get_positions(view_id=view_id)
        candidates = self.list_candidates() if include_candidates else []
        pending_count = self.pending_candidates_count()

        for c in concepts:
            pos = positions.get(c["concept_id"], {})
            c["x"] = pos.get("x", 0.0)
            c["y"] = pos.get("y", 0.0)

        return {
            "concepts": concepts,
            "relationships": rels,
            "candidates": candidates,
            "pending_count": pending_count,
            "total_concepts": len(concepts),
        }

    def get_subgraph(
        self,
        concept_id: str,
        *,
        depth: int = 1,
        view_id: str = "default",
    ) -> dict[str, Any] | None:
        """Return concept + its 1-hop neighbourhood for sidebar / expand."""
        root = self.get_concept(concept_id)
        if root is None:
            return None

        with self._connect() as con:
            neighbour_rows = con.execute(
                """SELECT DISTINCT
                       CASE WHEN from_id = ? THEN to_id ELSE from_id END AS neighbour_id
                   FROM relationships
                   WHERE from_id = ? OR to_id = ?""",
                (concept_id, concept_id, concept_id),
            ).fetchall()
            neighbour_ids = [r["neighbour_id"] for r in neighbour_rows]

            all_ids = [concept_id] + neighbour_ids
            concept_rows = con.execute(
                "SELECT * FROM concepts WHERE concept_id IN ({ph})".format(
                    ph=",".join("?" * len(all_ids))
                ),
                all_ids,
            ).fetchall()

            rel_rows = con.execute(
                """SELECT * FROM relationships
                   WHERE (from_id = ? OR to_id = ?)""",
                (concept_id, concept_id),
            ).fetchall()

            ev_rows = con.execute(
                """SELECT * FROM evidence
                   WHERE rel_id IN ({ph})""".format(
                    ph=",".join("?" * len(rel_rows)) if rel_rows else "NULL"
                ),
                [r["rel_id"] for r in rel_rows],
            ).fetchall() if rel_rows else []

        positions = self.get_positions(view_id=view_id)
        concepts = [_row_to_concept(r) for r in concept_rows]
        for c in concepts:
            pos = positions.get(c["concept_id"], {})
            c["x"] = pos.get("x", 0.0)
            c["y"] = pos.get("y", 0.0)

        return {
            "root": root,
            "concepts": concepts,
            "relationships": [dict(r) for r in rel_rows],
            "evidence": [dict(e) for e in ev_rows],
        }


# ------------------------------------------------------------------
# Row converters
# ------------------------------------------------------------------

def _row_to_concept(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["aliases"] = json.loads(d.get("aliases") or "[]")
    d["topic_ids"] = json.loads(d.get("topic_ids") or "[]")
    return d


def _row_to_candidate(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["suggested_rels"] = json.loads(d.get("suggested_rels") or "[]")
    return d


def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    try:
        d["warnings"] = json.loads(d.get("warnings") or "[]")
    except json.JSONDecodeError:
        d["warnings"] = []
    try:
        d["failed_sections"] = json.loads(d.get("failed_sections") or "[]")
    except json.JSONDecodeError:
        d["failed_sections"] = []
    return d
