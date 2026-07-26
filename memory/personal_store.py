"""Structured personal knowledge and learning-event storage."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knowledge.paths import knowledge_path
from core.db import create_connection, open_connection


GLOBAL_DB_FILENAME = "personal-knowledge.db"
LIBRARY_DB_FILENAME = "bobodan.db"

KNOWLEDGE_KINDS = {
    "preference", "goal", "profile_fact", "learning_strategy",
    "course_insight", "study_pattern",
}
KNOWLEDGE_SCOPES = {"global", "library"}
EVENT_TYPES = {
    "quiz_answered", "practice_completed", "review_started", "review_completed",
    "document_opened", "reading_progress", "chat_completed",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _home() -> Path:
    configured = os.getenv("BOBODAN_HOME")
    return Path(configured).expanduser().resolve() if configured else Path.home() / ".bobodan"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold().strip()
    return re.sub(r"[^\w\u3400-\u9fff]+", "", normalized)


def content_fingerprint(scope: str, kind: str, content: str) -> str:
    import hashlib
    raw = f"{scope}:{kind}:{normalize_text(content)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _search_text(title: str, content: str, kind: str) -> str:
    base = unicodedata.normalize("NFKC", f"{title} {content} {kind}").casefold()
    cjk = re.findall(r"[\u3400-\u9fff]+", base)
    grams: list[str] = []
    for run in cjk:
        chars = list(run)
        grams.extend("".join(chars[index:index + 2]) for index in range(max(0, len(chars) - 1)))
    return " ".join(dict.fromkeys([base, *grams]))


_SCHEMA = """
CREATE TABLE IF NOT EXISTS personal_knowledge (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL CHECK(scope IN ('global', 'library')),
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    search_text TEXT NOT NULL DEFAULT '',
    pinned INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 1.0,
    evidence TEXT NOT NULL DEFAULT '[]',
    source_candidate_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS knowledge_candidates (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL CHECK(scope IN ('global', 'library')),
    kind TEXT NOT NULL,
    operation TEXT NOT NULL CHECK(operation IN ('create', 'update')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    target_item_id TEXT,
    confidence REAL NOT NULL DEFAULT 0.5,
    reason TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending',
    fingerprint TEXT NOT NULL,
    rejected_until TEXT,
    generated_by TEXT NOT NULL DEFAULT 'bobodan',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS learning_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    concept TEXT,
    payload TEXT NOT NULL DEFAULT '{}',
    dedupe_key TEXT NOT NULL UNIQUE,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reading_progress (
    document_id TEXT PRIMARY KEY,
    progress INTEGER NOT NULL DEFAULT 0,
    opened_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_jobs (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    not_before TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    cursor INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_type, source_id)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_scope_updated ON personal_knowledge(scope, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_candidates_status_updated ON knowledge_candidates(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_time ON learning_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status_due ON memory_jobs(status, not_before);
"""


class PersonalKnowledgeStore:
    def __init__(self, workspace: str, home: str | None = None):
        self.workspace = str(Path(workspace).resolve())
        self.home = Path(home).expanduser().resolve() if home else _home()
        self.global_path = self.home / GLOBAL_DB_FILENAME
        self.library_path = Path(knowledge_path(self.workspace, LIBRARY_DB_FILENAME))
        self._ensure(self.global_path)
        self._ensure(self.library_path)

    @contextmanager
    def _conn(self, scope: str):
        path = self.global_path if scope == "global" else self.library_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open_connection(str(path)) as conn:
            yield conn

    def _ensure(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = create_connection(str(path))
        try:
            conn.executescript(_SCHEMA)
            try:
                conn.execute(
                    """CREATE VIRTUAL TABLE IF NOT EXISTS personal_knowledge_fts
                       USING fts5(title, content, search_text, content='personal_knowledge', content_rowid='rowid', tokenize='unicode61')"""
                )
                conn.executescript("""
                    CREATE TRIGGER IF NOT EXISTS personal_knowledge_ai AFTER INSERT ON personal_knowledge BEGIN
                        INSERT INTO personal_knowledge_fts(rowid, title, content, search_text)
                        VALUES (new.rowid, new.title, new.content, new.search_text);
                    END;
                    CREATE TRIGGER IF NOT EXISTS personal_knowledge_ad AFTER DELETE ON personal_knowledge BEGIN
                        INSERT INTO personal_knowledge_fts(personal_knowledge_fts, rowid, title, content, search_text)
                        VALUES ('delete', old.rowid, old.title, old.content, old.search_text);
                    END;
                    CREATE TRIGGER IF NOT EXISTS personal_knowledge_au AFTER UPDATE ON personal_knowledge BEGIN
                        INSERT INTO personal_knowledge_fts(personal_knowledge_fts, rowid, title, content, search_text)
                        VALUES ('delete', old.rowid, old.title, old.content, old.search_text);
                        INSERT INTO personal_knowledge_fts(rowid, title, content, search_text)
                        VALUES (new.rowid, new.title, new.content, new.search_text);
                    END;
                """)
                source_count = conn.execute("SELECT COUNT(*) FROM personal_knowledge").fetchone()[0]
                fts_count = conn.execute("SELECT COUNT(*) FROM personal_knowledge_fts").fetchone()[0]
                if source_count != fts_count:
                    conn.execute("INSERT INTO personal_knowledge_fts(personal_knowledge_fts) VALUES ('rebuild')")
            except sqlite3.OperationalError:
                pass
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _item(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "scope": row["scope"], "kind": row["kind"],
            "title": row["title"], "content": row["content"], "pinned": bool(row["pinned"]),
            "confidence": row["confidence"], "evidence": _loads(row["evidence"], []),
            "source_candidate_id": row["source_candidate_id"], "created_at": row["created_at"],
            "updated_at": row["updated_at"], "revision": row["revision"],
        }

    @staticmethod
    def _candidate(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "scope": row["scope"], "kind": row["kind"],
            "operation": row["operation"], "title": row["title"], "content": row["content"],
            "target_item_id": row["target_item_id"], "confidence": row["confidence"],
            "reason": row["reason"], "evidence": _loads(row["evidence"], []),
            "status": row["status"], "fingerprint": row["fingerprint"],
            "rejected_until": row["rejected_until"], "generated_by": row["generated_by"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "resolved_at": row["resolved_at"],
        }

    def create_item(self, *, scope: str, kind: str, title: str, content: str,
                    pinned: bool = False, confidence: float = 1.0,
                    evidence: list[dict] | None = None, source_candidate_id: str | None = None) -> dict:
        if scope not in KNOWLEDGE_SCOPES or kind not in KNOWLEDGE_KINDS:
            raise ValueError("Unsupported personal knowledge scope or kind")
        if not title.strip() or not content.strip():
            raise ValueError("Personal knowledge title and content are required")
        item_id = uuid.uuid4().hex
        timestamp = _now()
        with self._conn(scope) as conn:
            conn.execute(
                """INSERT INTO personal_knowledge
                   (id, scope, kind, title, content, search_text, pinned, confidence, evidence,
                    source_candidate_id, created_at, updated_at, revision)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (item_id, scope, kind, title.strip(), content.strip(), _search_text(title, content, kind),
                 1 if pinned else 0, max(0.0, min(float(confidence), 1.0)), _json(evidence or []),
                 source_candidate_id, timestamp, timestamp),
            )
            row = conn.execute("SELECT * FROM personal_knowledge WHERE id = ?", (item_id,)).fetchone()
        return self._item(row)

    def list_items(self, scope: str = "all", query: str = "", kind: str | None = None,
                   limit: int = 100) -> list[dict]:
        scopes = [scope] if scope in KNOWLEDGE_SCOPES else ["global", "library"]
        result: list[dict] = []
        for current in scopes:
            with self._conn(current) as conn:
                sql = "SELECT * FROM personal_knowledge WHERE 1=1"
                params: list[Any] = []
                if kind:
                    sql += " AND kind = ?"
                    params.append(kind)
                if query.strip():
                    normalized = unicodedata.normalize("NFKC", query).casefold().strip()
                    terms = re.findall(r"[\w\u3400-\u9fff]+", normalized)
                    cjk = "".join(re.findall(r"[\u3400-\u9fff]", normalized))
                    terms.extend(cjk[index:index + 2] for index in range(max(0, len(cjk) - 1)))
                    match = " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in dict.fromkeys(terms) if term)
                    if match:
                        try:
                            fts_sql = """SELECT personal_knowledge.* FROM personal_knowledge_fts
                                         JOIN personal_knowledge ON personal_knowledge.rowid = personal_knowledge_fts.rowid
                                         WHERE personal_knowledge_fts MATCH ?"""
                            fts_params: list[Any] = [match]
                            if kind:
                                fts_sql += " AND personal_knowledge.kind = ?"
                                fts_params.append(kind)
                            fts_sql += " ORDER BY personal_knowledge.pinned DESC, personal_knowledge.updated_at DESC LIMIT ?"
                            fts_params.append(max(1, min(limit, 500)))
                            rows = conn.execute(fts_sql, fts_params).fetchall()
                            if rows:
                                result.extend(self._item(row) for row in rows)
                                continue
                        except sqlite3.OperationalError:
                            pass
                    sql += " AND (title LIKE ? OR content LIKE ? OR search_text LIKE ?)"
                    token = f"%{unicodedata.normalize('NFKC', query).strip()}%"
                    params.extend([token, token, token.casefold()])
                sql += " ORDER BY pinned DESC, updated_at DESC LIMIT ?"
                params.append(max(1, min(limit, 500)))
                result.extend(self._item(row) for row in conn.execute(sql, params).fetchall())
        result.sort(key=lambda item: item["updated_at"], reverse=True)
        result.sort(key=lambda item: item["pinned"], reverse=True)
        return result[:limit]

    def get_item(self, item_id: str) -> dict | None:
        for scope in ("global", "library"):
            with self._conn(scope) as conn:
                row = conn.execute("SELECT * FROM personal_knowledge WHERE id = ?", (item_id,)).fetchone()
                if row:
                    return self._item(row)
        return None

    def update_item(self, item_id: str, revision: int, patch: dict[str, Any]) -> dict:
        item = self.get_item(item_id)
        if not item:
            raise FileNotFoundError("Personal knowledge item not found")
        if revision != item["revision"]:
            raise RuntimeError("knowledge_revision_conflict")
        allowed = {"title", "content", "pinned", "kind"}
        updated = {**item, **{key: value for key, value in patch.items() if key in allowed}}
        if updated["kind"] not in KNOWLEDGE_KINDS or not str(updated["title"]).strip() or not str(updated["content"]).strip():
            raise ValueError("Invalid personal knowledge update")
        with self._conn(item["scope"]) as conn:
            cursor = conn.execute(
                """UPDATE personal_knowledge SET kind=?, title=?, content=?, search_text=?, pinned=?,
                   updated_at=?, revision=revision+1 WHERE id=? AND revision=?""",
                (updated["kind"], str(updated["title"]).strip(), str(updated["content"]).strip(),
                 _search_text(str(updated["title"]), str(updated["content"]), updated["kind"]),
                 1 if updated["pinned"] else 0, _now(), item_id, revision),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("knowledge_revision_conflict")
            row = conn.execute("SELECT * FROM personal_knowledge WHERE id = ?", (item_id,)).fetchone()
        return self._item(row)

    def delete_item(self, item_id: str) -> bool:
        item = self.get_item(item_id)
        if not item:
            return False
        with self._conn(item["scope"]) as conn:
            conn.execute("DELETE FROM personal_knowledge WHERE id = ?", (item_id,))
        return True

    def add_candidate(self, *, scope: str, kind: str, operation: str, title: str,
                      content: str, confidence: float, reason: str,
                      evidence: list[dict] | None = None, target_item_id: str | None = None,
                      generated_by: str = "bobodan") -> dict | None:
        if scope not in KNOWLEDGE_SCOPES or kind not in KNOWLEDGE_KINDS or operation not in {"create", "update"}:
            raise ValueError("Unsupported knowledge candidate")
        if not title.strip() or not content.strip():
            raise ValueError("Knowledge candidate title and content are required")
        fingerprint = content_fingerprint(scope, kind, content)
        with self._conn(scope) as conn:
            existing = conn.execute(
                """SELECT * FROM knowledge_candidates WHERE fingerprint = ?
                   AND (status = 'pending' OR (status = 'rejected' AND rejected_until > ?))
                   ORDER BY updated_at DESC LIMIT 1""",
                (fingerprint, _now()),
            ).fetchone()
            if existing:
                return None
            candidate_id = uuid.uuid4().hex
            timestamp = _now()
            conn.execute(
                """INSERT INTO knowledge_candidates
                   (id, scope, kind, operation, title, content, target_item_id, confidence,
                    reason, evidence, status, fingerprint, generated_by, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
                (candidate_id, scope, kind, operation, title.strip(), content.strip(), target_item_id,
                 max(0.0, min(float(confidence), 1.0)), reason.strip(), _json(evidence or []),
                 fingerprint, generated_by, timestamp, timestamp),
            )
            row = conn.execute("SELECT * FROM knowledge_candidates WHERE id = ?", (candidate_id,)).fetchone()
        return self._candidate(row)

    def list_candidates(self, status: str = "pending", scope: str = "all", limit: int = 100) -> list[dict]:
        scopes = [scope] if scope in KNOWLEDGE_SCOPES else ["global", "library"]
        result: list[dict] = []
        for current in scopes:
            with self._conn(current) as conn:
                rows = conn.execute(
                    "SELECT * FROM knowledge_candidates WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                    (status, max(1, min(limit, 500))),
                ).fetchall()
                result.extend(self._candidate(row) for row in rows)
        return sorted(result, key=lambda item: item["updated_at"], reverse=True)[:limit]

    def get_candidate(self, candidate_id: str) -> dict | None:
        for scope in ("global", "library"):
            with self._conn(scope) as conn:
                row = conn.execute("SELECT * FROM knowledge_candidates WHERE id = ?", (candidate_id,)).fetchone()
                if row:
                    return self._candidate(row)
        return None

    def confirm_candidate(self, candidate_id: str, edits: dict[str, Any] | None = None) -> tuple[dict, dict]:
        candidate = self.get_candidate(candidate_id)
        if not candidate or candidate["status"] != "pending":
            raise FileNotFoundError("Pending knowledge candidate not found")
        values = {**candidate, **(edits or {})}
        if values["scope"] not in KNOWLEDGE_SCOPES or values["kind"] not in KNOWLEDGE_KINDS:
            raise ValueError("Invalid candidate confirmation")
        target = self.get_item(str(values.get("target_item_id") or "")) if values["operation"] == "update" else None
        if target:
            if target["scope"] == values["scope"]:
                item = self.update_item(target["id"], target["revision"], {
                    "title": values["title"], "content": values["content"], "kind": values["kind"],
                })
            else:
                item = self.create_item(
                    scope=values["scope"], kind=values["kind"], title=values["title"],
                    content=values["content"], confidence=values["confidence"],
                    evidence=values["evidence"], source_candidate_id=candidate_id,
                )
                self.delete_item(target["id"])
        else:
            item = self.create_item(
                scope=values["scope"], kind=values["kind"], title=values["title"],
                content=values["content"], confidence=values["confidence"],
                evidence=values["evidence"], source_candidate_id=candidate_id,
            )
        with self._conn(candidate["scope"]) as conn:
            timestamp = _now()
            conn.execute(
                "UPDATE knowledge_candidates SET status='confirmed', resolved_at=?, updated_at=? WHERE id=?",
                (timestamp, timestamp, candidate_id),
            )
            row = conn.execute("SELECT * FROM knowledge_candidates WHERE id = ?", (candidate_id,)).fetchone()
        return item, self._candidate(row)

    def reject_candidate(self, candidate_id: str, days: int = 30) -> dict:
        from datetime import timedelta
        candidate = self.get_candidate(candidate_id)
        if not candidate or candidate["status"] != "pending":
            raise FileNotFoundError("Pending knowledge candidate not found")
        timestamp = datetime.now(timezone.utc)
        with self._conn(candidate["scope"]) as conn:
            conn.execute(
                """UPDATE knowledge_candidates SET status='rejected', rejected_until=?,
                   resolved_at=?, updated_at=? WHERE id=?""",
                ((timestamp + timedelta(days=days)).isoformat(timespec="seconds"),
                 timestamp.isoformat(timespec="seconds"), timestamp.isoformat(timespec="seconds"), candidate_id),
            )
            row = conn.execute("SELECT * FROM knowledge_candidates WHERE id = ?", (candidate_id,)).fetchone()
        return self._candidate(row)

    def record_event(self, *, event_type: str, source_type: str, source_id: str,
                     concept: str | None = None, payload: dict | None = None,
                     occurred_at: str | None = None, dedupe_key: str | None = None) -> dict:
        if event_type not in EVENT_TYPES:
            raise ValueError("Unsupported learning event type")
        event_id = uuid.uuid4().hex
        key = dedupe_key or f"{event_type}:{source_type}:{source_id}:{concept or ''}"
        timestamp = occurred_at or _now()
        with self._conn("library") as conn:
            conn.execute(
                """INSERT OR IGNORE INTO learning_events
                   (id, event_type, source_type, source_id, concept, payload, dedupe_key, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, event_type, source_type, source_id, concept, _json(payload or {}), key, timestamp),
            )
            row = conn.execute("SELECT * FROM learning_events WHERE dedupe_key = ?", (key,)).fetchone()
        return {
            "id": row["id"], "type": row["event_type"], "source_type": row["source_type"],
            "source_id": row["source_id"], "concept": row["concept"],
            "payload": _loads(row["payload"], {}), "occurred_at": row["occurred_at"],
        }

    def list_events(self, limit: int = 100, event_type: str | None = None) -> list[dict]:
        with self._conn("library") as conn:
            if event_type:
                rows = conn.execute(
                    "SELECT * FROM learning_events WHERE event_type=? ORDER BY occurred_at DESC LIMIT ?",
                    (event_type, max(1, min(limit, 500))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM learning_events ORDER BY occurred_at DESC LIMIT ?",
                    (max(1, min(limit, 500)),),
                ).fetchall()
        return [{
            "id": row["id"], "type": row["event_type"], "source_type": row["source_type"],
            "source_id": row["source_id"], "concept": row["concept"],
            "payload": _loads(row["payload"], {}), "occurred_at": row["occurred_at"],
        } for row in rows]

    def update_reading_progress(self, document_id: str, progress: int, opened: bool = False) -> dict:
        progress = max(0, min(int(progress), 100))
        progress = 100 if progress == 100 else (progress // 10) * 10
        timestamp = _now()
        with self._conn("library") as conn:
            existing = conn.execute("SELECT * FROM reading_progress WHERE document_id=?", (document_id,)).fetchone()
            highest = max(progress, int(existing["progress"]) if existing else 0)
            opened_at = (existing["opened_at"] if existing else None) or (timestamp if opened else None)
            conn.execute(
                """INSERT INTO reading_progress(document_id, progress, opened_at, updated_at)
                   VALUES (?, ?, ?, ?) ON CONFLICT(document_id) DO UPDATE SET
                   progress=excluded.progress, opened_at=COALESCE(reading_progress.opened_at, excluded.opened_at),
                   updated_at=excluded.updated_at""",
                (document_id, highest, opened_at, timestamp),
            )
        if opened:
            self.record_event(event_type="document_opened", source_type="document", source_id=document_id,
                              payload={"progress": highest}, dedupe_key=f"document_opened:{document_id}:{timestamp[:10]}")
        if highest >= 10 and (not existing or highest >= int(existing["progress"]) + 10 or highest == 100):
            self.record_event(event_type="reading_progress", source_type="document", source_id=document_id,
                              payload={"progress": highest}, dedupe_key=f"reading_progress:{document_id}:{highest // 10}")
        return {"document_id": document_id, "progress": highest, "opened_at": opened_at, "updated_at": timestamp}

    def overview(self) -> dict:
        items = self.list_items(limit=500)
        candidates = self.list_candidates(limit=500)
        with self._conn("library") as conn:
            event_count = conn.execute("SELECT COUNT(*) FROM learning_events").fetchone()[0]
            failed_jobs = conn.execute("SELECT COUNT(*) FROM memory_jobs WHERE status='failed'").fetchone()[0]
            pending_jobs = conn.execute("SELECT COUNT(*) FROM memory_jobs WHERE status IN ('pending','running')").fetchone()[0]
        return {
            "knowledge_count": len(items),
            "global_count": sum(1 for item in items if item["scope"] == "global"),
            "library_count": sum(1 for item in items if item["scope"] == "library"),
            "pending_candidate_count": len(candidates),
            "event_count": event_count,
            "jobs": {"pending": pending_jobs, "failed": failed_jobs},
        }

    def recover_jobs(self) -> int:
        with self._conn("library") as conn:
            cursor = conn.execute(
                """UPDATE memory_jobs SET status='pending', error='The previous process stopped before consolidation completed.',
                   updated_at=? WHERE status='running'""",
                (_now(),),
            )
            return cursor.rowcount

    def enqueue_job(self, source_type: str, source_id: str, cursor: int, not_before: str) -> dict:
        timestamp = _now()
        with self._conn("library") as conn:
            existing = conn.execute(
                "SELECT * FROM memory_jobs WHERE source_type=? AND source_id=?",
                (source_type, source_id),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE memory_jobs SET status='pending', not_before=?, cursor=?, error=NULL,
                       attempts=CASE WHEN status='completed' THEN 0 ELSE attempts END,
                       updated_at=? WHERE id=?""",
                    (not_before, max(cursor, int(existing["cursor"])), timestamp, existing["id"]),
                )
                job_id = existing["id"]
            else:
                job_id = uuid.uuid4().hex
                conn.execute(
                    """INSERT INTO memory_jobs
                       (id, source_type, source_id, status, not_before, attempts, cursor, created_at, updated_at)
                       VALUES (?, ?, ?, 'pending', ?, 0, ?, ?, ?)""",
                    (job_id, source_type, source_id, not_before, cursor, timestamp, timestamp),
                )
            row = conn.execute("SELECT * FROM memory_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row)

    def claim_due_job(self) -> dict | None:
        with self._conn("library") as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT * FROM memory_jobs WHERE status='pending' AND not_before<=?
                   ORDER BY not_before, created_at LIMIT 1""",
                (_now(),),
            ).fetchone()
            if not row:
                return None
            cursor = conn.execute(
                """UPDATE memory_jobs SET status='running', attempts=attempts+1, updated_at=?
                   WHERE id=? AND status='pending'""",
                (_now(), row["id"]),
            )
            if cursor.rowcount != 1:
                return None
            claimed = conn.execute("SELECT * FROM memory_jobs WHERE id=?", (row["id"],)).fetchone()
        return dict(claimed)

    def finish_job(self, job_id: str, cursor: int | None = None) -> None:
        with self._conn("library") as conn:
            if cursor is None:
                conn.execute("UPDATE memory_jobs SET status='completed', error=NULL, updated_at=? WHERE id=?", (_now(), job_id))
            else:
                conn.execute(
                    """UPDATE memory_jobs SET status='completed', error=NULL, updated_at=?
                       WHERE id=? AND cursor<=?""",
                    (_now(), job_id, cursor),
                )

    def fail_job(self, job_id: str, error: str, retry_at: str | None, cursor: int | None = None) -> None:
        with self._conn("library") as conn:
            if cursor is not None:
                row = conn.execute("SELECT cursor FROM memory_jobs WHERE id=?", (job_id,)).fetchone()
                if row and int(row["cursor"]) > cursor:
                    return
            if retry_at:
                conn.execute(
                    "UPDATE memory_jobs SET status='pending', error=?, not_before=?, updated_at=? WHERE id=?",
                    (error[:1000], retry_at, _now(), job_id),
                )
            else:
                conn.execute(
                    "UPDATE memory_jobs SET status='failed', error=?, updated_at=? WHERE id=?",
                    (error[:1000], _now(), job_id),
                )

    def list_jobs(self, limit: int = 50) -> list[dict]:
        with self._conn("library") as conn:
            rows = conn.execute(
                "SELECT * FROM memory_jobs ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_job(self, job_id: str) -> dict | None:
        with self._conn("library") as conn:
            row = conn.execute("SELECT * FROM memory_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def export_markdown(self, scope: str = "all") -> str:
        items = self.list_items(scope=scope, limit=500)
        lines = ["# Bobodan Personal Knowledge", ""]
        for group_scope, label in (("global", "Global"), ("library", "Current Library")):
            selected = [item for item in items if item["scope"] == group_scope]
            if not selected:
                continue
            lines.extend([f"## {label}", ""])
            for item in selected:
                pin = " [Pinned]" if item["pinned"] else ""
                lines.extend([f"### {item['title']}{pin}", "", item["content"], "", f"- Type: {item['kind']}", f"- Updated: {item['updated_at']}", ""])
        return "\n".join(lines).rstrip() + "\n"
