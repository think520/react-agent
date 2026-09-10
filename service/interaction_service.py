"""Interaction lifecycle store (E4).

Tracks the structured questions the agent asks the user (ask_user). The
lifecycle is registered -> awaiting_input -> answered -> graded and is persisted
in SQLite so an interrupted turn can still be answered after a page reload, a
disconnect or a backend restart.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from core.db import create_connection, ensure_columns
from knowledge.paths import knowledge_path

DB_FILENAME = "bobodan.db"

STATUS_REGISTERED = "registered"
STATUS_AWAITING = "awaiting_input"
STATUS_ANSWERED = "answered"
STATUS_GRADED = "graded"

# A question stays actionable for the user while it is in one of these states.
_OPEN_STATUSES = (STATUS_REGISTERED, STATUS_AWAITING)

# Data hygiene only: the ACTION boundary (the session moving on) decides whether
# a card is still answerable. This window just stops orphan rows accumulating.
DEFAULT_TTL_DAYS = 7

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS interactions (
    interaction_id TEXT PRIMARY KEY,
    chat_session_id TEXT NOT NULL DEFAULT '',
    library_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'registered',
    questions TEXT NOT NULL DEFAULT '[]',
    answers TEXT NOT NULL DEFAULT '[]',
    outcome TEXT NOT NULL DEFAULT '{}',
    tool_call_id TEXT NOT NULL DEFAULT '',
    closure TEXT NOT NULL DEFAULT '',
    expires_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT '',
    answered_at TEXT NOT NULL DEFAULT '',
    graded_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_interactions_session ON interactions(chat_session_id);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def grade_answers(questions: list[dict], answers: list[dict]) -> dict:
    """Deterministically grade answers whose question carried a correct option.

    Open questions simply record the answer and complete with graded=False, so
    callers never have to special-case them.
    """
    answers_by_id: dict[str, Any] = {}
    for answer in answers or []:
        if isinstance(answer, dict) and answer.get("id"):
            answers_by_id[str(answer["id"])] = answer.get("answer")

    graded = False
    correct = 0
    results = []
    for question in questions or []:
        expected = question.get("answer")
        if not expected:
            continue
        given = answers_by_id.get(str(question.get("id")))
        is_correct = _normalize(given) == _normalize(expected)
        graded = True
        correct += 1 if is_correct else 0
        results.append({"id": question.get("id"), "correct": is_correct})
    return {
        "graded": graded,
        "correct": correct,
        "total": len(questions or []),
        "results": results,
    }


def _row_to_dict(row: Any) -> dict:
    return {
        "interaction_id": row["interaction_id"],
        "chat_session_id": row["chat_session_id"],
        "library_id": row["library_id"],
        "status": row["status"],
        "questions": json.loads(row["questions"] or "[]"),
        "answers": json.loads(row["answers"] or "[]"),
        "outcome": json.loads(row["outcome"] or "{}"),
        "tool_call_id": row["tool_call_id"],
        "closure": row["closure"],
        "expires_at": row["expires_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "answered_at": row["answered_at"],
        "graded_at": row["graded_at"],
    }


class InteractionService:
    """SQLite-backed lifecycle for agent to user questions."""

    def __init__(self, workspace: str):
        self.workspace = workspace
        self.db_path = knowledge_path(workspace, DB_FILENAME)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _connect(self):
        return create_connection(self.db_path)

    def init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA_SQL)
            ensure_columns(conn, "interactions", {
                "tool_call_id": "TEXT NOT NULL DEFAULT ''",
                "closure": "TEXT NOT NULL DEFAULT ''",
                "expires_at": "TEXT NOT NULL DEFAULT ''",
            })
            conn.commit()
        finally:
            conn.close()

    def register(
        self,
        interaction_id: str,
        *,
        chat_session_id: str = "",
        library_id: str = "",
        questions: list[dict] | None = None,
    ) -> dict:
        self.init_db()
        now = _now_iso()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=DEFAULT_TTL_DAYS)).isoformat()
        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO interactions
                   (interaction_id, chat_session_id, library_id, status, questions, created_at, updated_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    interaction_id,
                    chat_session_id or "",
                    library_id or "",
                    STATUS_REGISTERED,
                    json.dumps(questions or [], ensure_ascii=False),
                    now,
                    now,
                    expires_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get(interaction_id) or {}

    def get(self, interaction_id: str) -> dict | None:
        self.init_db()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM interactions WHERE interaction_id = ?",
                (interaction_id,),
            ).fetchone()
        finally:
            conn.close()
        return _row_to_dict(row) if row else None

    def mark_awaiting(self, interaction_id: str) -> dict | None:
        record = self.get(interaction_id)
        if not record or record["status"] != STATUS_REGISTERED:
            return record
        self._update(interaction_id, status=STATUS_AWAITING)
        return self.get(interaction_id)

    def answer(self, interaction_id: str, answers: list[dict]) -> dict | None:
        """Record the user's answers and complete the lifecycle.

        Idempotent: an already answered or graded interaction is returned as is.
        """
        record = self.get(interaction_id)
        if not record:
            return None
        if record["status"] in (STATUS_ANSWERED, STATUS_GRADED):
            return record
        now = _now_iso()
        outcome = grade_answers(record["questions"], answers or [])
        self._update(
            interaction_id,
            status=STATUS_GRADED,
            closure="answered",
            answers=json.dumps(answers or [], ensure_ascii=False),
            outcome=json.dumps(outcome, ensure_ascii=False),
            answered_at=now,
            graded_at=now,
        )
        return self.get(interaction_id)

    def attach_tool_call(self, interaction_id: str, tool_call_id: str) -> dict | None:
        """Bind the paused tool call that this interaction must resume.

        A tool never learns its own tool_call_id -- only the agent loop does -- so
        the loop stamps it into the pause payload and the web layer records it
        here. This is what lets the resume fill the right tool message.
        """
        if not tool_call_id:
            return self.get(interaction_id)
        self._update(interaction_id, tool_call_id=tool_call_id)
        return self.get(interaction_id)

    def close(self, interaction_id: str, *, closure: str, outcome: dict | None = None) -> dict | None:
        """Close a pending interaction without an answer (skipped / expired)."""
        record = self.get(interaction_id)
        if not record:
            return None
        if record["status"] in (STATUS_ANSWERED, STATUS_GRADED):
            return record
        self._update(
            interaction_id,
            status=STATUS_GRADED,
            closure=closure,
            outcome=json.dumps(outcome or {"graded": False, "skipped": True}, ensure_ascii=False),
            graded_at=_now_iso(),
        )
        return self.get(interaction_id)

    def expire_stale(self, chat_session_id: str | None = None) -> int:
        """Close interactions past the data-hygiene window; returns how many."""
        now = _now_iso()
        sql = (
            "UPDATE interactions SET status = ?, closure = 'expired', graded_at = ?, updated_at = ? "
            "WHERE status IN (?, ?) AND expires_at != '' AND expires_at < ?"
        )
        params: list[Any] = [STATUS_GRADED, now, now, _OPEN_STATUSES[0], _OPEN_STATUSES[1], now]
        if chat_session_id is not None:
            sql += " AND chat_session_id = ?"
            params.append(chat_session_id)
        conn = self._connect()
        try:
            cursor = conn.execute(sql, tuple(params))
            conn.commit()
            return int(cursor.rowcount or 0)
        finally:
            conn.close()

    def list_open(self, chat_session_id: str) -> list[dict]:
        self.init_db()
        self.expire_stale(chat_session_id)
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM interactions WHERE chat_session_id = ? AND status IN (?, ?) ORDER BY created_at",
                (chat_session_id, _OPEN_STATUSES[0], _OPEN_STATUSES[1]),
            ).fetchall()
        finally:
            conn.close()
        return [_row_to_dict(row) for row in rows]

    def _update(self, interaction_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = _now_iso()
        assignments = ", ".join(f"{name} = ?" for name in fields)
        conn = self._connect()
        try:
            conn.execute(
                f"UPDATE interactions SET {assignments} WHERE interaction_id = ?",
                (*fields.values(), interaction_id),
            )
            conn.commit()
        finally:
            conn.close()
