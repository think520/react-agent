"""Concept graph store — P5E.6 knowledge map backend.

SQLite-backed store for concept graph data: concepts, relationships,
evidence, candidates, and persisted node positions.

Tables
------
concepts          — confirmed concept nodes (core/detail/cluster)
relationships     — confirmed edges between concepts
evidence          — source evidence anchoring relationships
concept_candidates — LLM-extracted candidates awaiting user review
concept_positions  — per-concept canvas positions (x, y) saved by user
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Generator


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

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        con = sqlite3.connect(self._db_path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _ensure_schema(self) -> None:
        with self._connect() as con:
            con.executescript(_DDL)

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
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as con:
            rows = con.execute(
                f"SELECT * FROM concepts {where} ORDER BY level, name LIMIT ?",
                params + [limit],
            ).fetchall()
        result = [_row_to_concept(r) for r in rows]
        if topic_id:
            result = [c for c in result if topic_id in c.get("topic_ids", [])]
        return result

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
                "SELECT * FROM relationships WHERE from_id = ? OR to_id = ?",
                (concept_id, concept_id),
            ).fetchall()
        return [dict(r) for r in rows]

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
                   (evidence_id, rel_id, document_id, document_title,
                    excerpt, location_type, location_value, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (eid, rel_id, document_id, document_title,
                 excerpt, location_type, location_value, now),
            )
        return {"evidence_id": eid, "rel_id": rel_id,
                "document_id": document_id, "document_title": document_title,
                "excerpt": excerpt, "location_type": location_type,
                "location_value": location_value, "location_stale": False}

    def evidence_for_relationship(self, rel_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM evidence WHERE rel_id = ?", (rel_id,)
            ).fetchall()
        return [dict(r) for r in rows]

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

    def list_candidates(self, *, status: str = "pending") -> list[dict[str, Any]]:
        now = time.time()
        with self._connect() as con:
            rows = con.execute(
                """SELECT * FROM concept_candidates
                   WHERE status = ?
                     AND (suppressed_until IS NULL OR suppressed_until <= ?)
                   ORDER BY
                     CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                     created_at""",
                (status, now),
            ).fetchall()
        return [_row_to_candidate(r) for r in rows]

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
        seen_rels: set[str] = set()
        with self._connect() as con:
            rows = con.execute(
                """SELECT * FROM relationships
                   WHERE from_id IN ({ph}) AND to_id IN ({ph})
                """.format(ph=",".join("?" * len(concept_ids))),
                list(concept_ids) * 2,
            ).fetchall()
            rels = [dict(r) for r in rows]
            seen_rels = {r["rel_id"] for r in rels}

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
