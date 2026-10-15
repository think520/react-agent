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

# W1 E4：**语义**超时 —— 等这么久还没回答，就别再让"挂起的问题"挡着下一步了。
# 与上面的数据卫生窗口不同：数据卫生只是别攒垃圾，这个决定"还要不要等"。
# 用户**迟到的回答仍然算数**（见 answer()）：超时只是让系统不再等，不是禁止作答。
DEFAULT_ANSWER_TIMEOUT_HOURS = 48


def resolve_interaction_timeout_hours(config: dict | None) -> int:
    """等待回答的时限（小时）；没配或配得不合理就用默认值，不猜。"""
    section = (config or {}).get("agent") or {}
    if not isinstance(section, dict):
        return DEFAULT_ANSWER_TIMEOUT_HOURS
    raw = section.get("interaction_timeout_hours")
    if raw is None:
        return DEFAULT_ANSWER_TIMEOUT_HOURS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_ANSWER_TIMEOUT_HOURS
    return value if value > 0 else DEFAULT_ANSWER_TIMEOUT_HOURS

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
    # W1 E4：multi_select 的答案是**集合**，顺序不该影响判定；
    # 也要能吃下数组载荷（前端直接送 ["甲","丙"] 时不该成为陷阱）。
    if isinstance(value, (list, tuple, set)):
        parts = [_normalize(item) for item in value]
        return ",".join(sorted(part for part in parts if part))
    parts = [part.strip() for part in str(value or "").split(",")]
    return ",".join(sorted(" ".join(part.split()).casefold() for part in parts if part))


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

    def __init__(self, workspace: str, *, timeout_hours: int | None = None):
        self.workspace = workspace
        self.db_path = knowledge_path(workspace, DB_FILENAME)
        # W1 E4：等回答的时限；调用方可以按配置覆盖（resolve_interaction_timeout_hours）。
        self.timeout_hours = int(timeout_hours or DEFAULT_ANSWER_TIMEOUT_HOURS)
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
        # W1 E4：只有"已经作答过"才幂等返回。超时/跳过/过期的记录**没有答案**，
        # 用户迟到回来作答必须算数 —— 旧实现把所有 graded 都当成"已作答"，
        # 于是迟到的答案被静默丢弃（接口 200，答案没了）。
        already_answered = record["status"] == STATUS_ANSWERED or bool(record.get("answered_at"))
        if already_answered:
            return record
        now = _now_iso()
        # 先算好批改结果，再分**两次**落库：answered → graded。
        # W1 E4：路线里的四态要真的能被观察到；旧实现把两次压成一次，
        # «answered» 永远不会出现（按路线实现的消费者等不到它）。
        # 先算后写，保证两次更新之间不会抛异常、不会把记录卡在「已作答未批改」。
        outcome = grade_answers(record["questions"], answers or [])
        payload = json.dumps(answers or [], ensure_ascii=False)
        self._update(
            interaction_id,
            status=STATUS_ANSWERED,
            answers=payload,
            answered_at=now,
        )
        self._update(
            interaction_id,
            status=STATUS_GRADED,
            closure="answered",
            outcome=json.dumps(outcome, ensure_ascii=False),
            graded_at=_now_iso(),
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

    def sweep_timeouts(self, chat_session_id: str | None = None) -> int:
        """W1 E4：把"等太久还没回答"的交互标记为 closure='timeout'；返回条数。

        只标记，**不删**任何东西；用户迟到的回答仍然算数（见 answer()）。
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=self.timeout_hours)).isoformat()
        sql = (
            "UPDATE interactions SET status = ?, closure = 'timeout', graded_at = ?, updated_at = ? "
            "WHERE status IN (?, ?) AND created_at != '' AND created_at < ?"
        )
        params: list[Any] = [STATUS_GRADED, _now_iso(), _now_iso(), _OPEN_STATUSES[0], _OPEN_STATUSES[1], cutoff]
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
        self.sweep_timeouts(chat_session_id)
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM interactions WHERE chat_session_id = ? AND status IN (?, ?) ORDER BY created_at",
                (chat_session_id, _OPEN_STATUSES[0], _OPEN_STATUSES[1]),
            ).fetchall()
        finally:
            conn.close()
        return [_row_to_dict(row) for row in rows]

    def list_pending(self, limit: int = 1) -> list[dict]:
        """跨会话的挂起问题（W1 E6 接线：next_objective 要知道"用户还欠一个回答"）。

        «list_open» 按会话取；这里要的是全局最早的几个，顺便清一次过期数据。
        """
        self.init_db()
        self.expire_stale()
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM interactions
                   WHERE status IN (?, ?)
                   ORDER BY created_at
                   LIMIT ?""",
                (_OPEN_STATUSES[0], _OPEN_STATUSES[1], max(1, int(limit))),
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
