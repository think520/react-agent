import json
import os
import sqlite3
from datetime import datetime, timezone

from .schema import Question, QuizSession, QuizAttempt

DB_FILENAME = "bobodan.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('single_choice', 'true_false', 'short_answer')),
    question TEXT NOT NULL,
    options TEXT NOT NULL DEFAULT '[]',
    answer TEXT NOT NULL,
    explanation TEXT NOT NULL DEFAULT '',
    concepts TEXT NOT NULL DEFAULT '[]',
    difficulty TEXT NOT NULL DEFAULT 'medium' CHECK(difficulty IN ('easy', 'medium', 'hard')),
    source TEXT NOT NULL DEFAULT '',
    attribution_kind TEXT NOT NULL DEFAULT 'unverified',
    sources TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_ids TEXT NOT NULL DEFAULT '[]',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    updated_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES quiz_sessions(id),
    question_id INTEGER NOT NULL REFERENCES questions(id),
    user_answer TEXT NOT NULL,
    is_correct INTEGER NOT NULL DEFAULT 0,
    feedback TEXT NOT NULL DEFAULT '',
    answered_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_session ON quiz_attempts(session_id);
CREATE INDEX IF NOT EXISTS idx_attempts_question ON quiz_attempts(question_id);
CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(type);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_question(row: sqlite3.Row) -> Question:
    return Question(
        id=row["id"],
        type=row["type"],
        question=row["question"],
        options=json.loads(row["options"]),
        answer=row["answer"],
        explanation=row["explanation"],
        concepts=json.loads(row["concepts"]),
        difficulty=row["difficulty"],
        source=row["source"],
        attribution_kind=row["attribution_kind"],
        sources=json.loads(row["sources"]),
        created_at=row["created_at"],
    )


def _row_to_session(row: sqlite3.Row) -> QuizSession:
    return QuizSession(
        id=row["id"],
        question_ids=json.loads(row["question_ids"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        updated_at=row["updated_at"],
        status=row["status"],
    )


def _row_to_attempt(row: sqlite3.Row) -> QuizAttempt:
    return QuizAttempt(
        id=row["id"],
        session_id=row["session_id"],
        question_id=row["question_id"],
        user_answer=row["user_answer"],
        is_correct=bool(row["is_correct"]),
        feedback=row["feedback"],
        answered_at=row["answered_at"],
    )


class QuizStore:
    def __init__(self, workspace: str):
        self.db_path = os.path.join(workspace, ".knowledge", DB_FILENAME)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA_SQL)
            question_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(questions)").fetchall()
            }
            if "attribution_kind" not in question_columns:
                conn.execute(
                    "ALTER TABLE questions ADD COLUMN attribution_kind TEXT NOT NULL DEFAULT 'unverified'"
                )
            if "sources" not in question_columns:
                conn.execute(
                    "ALTER TABLE questions ADD COLUMN sources TEXT NOT NULL DEFAULT '[]'"
                )

            session_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(quiz_sessions)").fetchall()
            }
            if "updated_at" not in session_columns:
                conn.execute(
                    "ALTER TABLE quiz_sessions ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"
                )
            if "status" not in session_columns:
                conn.execute(
                    "ALTER TABLE quiz_sessions ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
                )
            conn.execute(
                """UPDATE quiz_sessions
                   SET updated_at = COALESCE(NULLIF(updated_at, ''), completed_at, started_at)"""
            )
            conn.execute(
                """UPDATE quiz_sessions
                   SET status = 'completed'
                   WHERE completed_at IS NOT NULL AND status = 'active'"""
            )
            conn.commit()
        finally:
            conn.close()

    # --- Questions ---

    def add_question(self, q: Question) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                """INSERT INTO questions (type, question, options, answer, explanation,
                   concepts, difficulty, source, attribution_kind, sources, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    q.type,
                    q.question,
                    json.dumps(q.options, ensure_ascii=False),
                    q.answer,
                    q.explanation,
                    json.dumps(q.concepts, ensure_ascii=False),
                    q.difficulty,
                    q.source,
                    q.attribution_kind,
                    json.dumps(q.sources, ensure_ascii=False),
                    q.created_at or _now_iso(),
                ),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_question(self, question_id: int) -> Question | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
            return _row_to_question(row) if row else None
        finally:
            conn.close()

    def list_questions(
        self, course: str | None = None, qtype: str | None = None, limit: int = 50
    ) -> list[Question]:
        conn = self._connect()
        try:
            sql = "SELECT * FROM questions WHERE 1=1"
            params: list = []
            if qtype:
                sql += " AND type = ?"
                params.append(qtype)
            if course:
                sql += " AND source LIKE ?"
                params.append(f"%{course}%")
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [_row_to_question(r) for r in rows]
        finally:
            conn.close()

    def get_questions_by_ids(self, ids: list[int]) -> list[Question]:
        if not ids:
            return []
        conn = self._connect()
        try:
            placeholders = ",".join("?" * len(ids))
            rows = conn.execute(
                f"SELECT * FROM questions WHERE id IN ({placeholders})", ids
            ).fetchall()
            by_id = {r["id"]: _row_to_question(r) for r in rows}
            return [by_id[i] for i in ids if i in by_id]
        finally:
            conn.close()

    def find_question_ids_by_concept(self, concept: str, limit: int = 5) -> list[int]:
        if not concept:
            return []
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT DISTINCT q.id
                   FROM questions q, json_each(q.concepts) concept_item
                   WHERE concept_item.value = ?
                   ORDER BY q.id DESC
                   LIMIT ?""",
                (concept, max(1, limit)),
            ).fetchall()
            return [int(row["id"]) for row in rows]
        finally:
            conn.close()

    def count_questions(self) -> dict:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT type, COUNT(*) as cnt FROM questions GROUP BY type"
            ).fetchall()
            return {r["type"]: r["cnt"] for r in rows}
        finally:
            conn.close()

    # --- Quiz Sessions ---

    def create_session(self, question_ids: list[int]) -> QuizSession:
        conn = self._connect()
        try:
            now = _now_iso()
            cur = conn.execute(
                """INSERT INTO quiz_sessions
                   (question_ids, started_at, updated_at, status) VALUES (?, ?, ?, 'active')""",
                (json.dumps(question_ids), now, now),
            )
            conn.commit()
            return QuizSession(
                id=cur.lastrowid,
                question_ids=question_ids,
                started_at=now,
                updated_at=now,
                status="active",
            )
        finally:
            conn.close()

    def get_session(self, session_id: int) -> QuizSession | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM quiz_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return _row_to_session(row) if row else None
        finally:
            conn.close()

    def complete_session(self, session_id: int) -> None:
        conn = self._connect()
        try:
            now = _now_iso()
            conn.execute(
                """UPDATE quiz_sessions
                   SET completed_at = ?, updated_at = ?, status = 'completed'
                   WHERE id = ?""",
                (now, now, session_id),
            )
            conn.commit()
        finally:
            conn.close()

    def abandon_session(self, session_id: int) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute(
                "UPDATE quiz_sessions SET status = 'abandoned', updated_at = ? WHERE id = ?",
                (_now_iso(), session_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def list_active_sessions(self, limit: int = 10) -> list[QuizSession]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM quiz_sessions
                   WHERE status = 'active' ORDER BY updated_at DESC, id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [_row_to_session(row) for row in rows]
        finally:
            conn.close()

    # --- Quiz Attempts ---

    def record_attempt(self, attempt: QuizAttempt) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                """INSERT INTO quiz_attempts
                   (session_id, question_id, user_answer, is_correct, feedback, answered_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    attempt.session_id,
                    attempt.question_id,
                    attempt.user_answer,
                    1 if attempt.is_correct else 0,
                    attempt.feedback,
                    attempt.answered_at or _now_iso(),
                ),
            )
            conn.execute(
                "UPDATE quiz_sessions SET updated_at = ? WHERE id = ?",
                (_now_iso(), attempt.session_id),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_attempts_for_session(self, session_id: int) -> list[QuizAttempt]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM quiz_attempts WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            return [_row_to_attempt(r) for r in rows]
        finally:
            conn.close()

    def get_wrong_answers(self, limit: int = 20) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT qa.id as attempt_id, qa.user_answer, qa.feedback, qa.answered_at,
                          q.id as question_id, q.type, q.question, q.options, q.answer,
                          q.explanation, q.concepts, q.difficulty, q.source
                   FROM quiz_attempts qa
                   JOIN questions q ON qa.question_id = q.id
                   WHERE qa.is_correct = 0
                   ORDER BY qa.answered_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            results = []
            for r in rows:
                results.append({
                    "attempt_id": r["attempt_id"],
                    "user_answer": r["user_answer"],
                    "feedback": r["feedback"],
                    "answered_at": r["answered_at"],
                    "question_id": r["question_id"],
                    "type": r["type"],
                    "question": r["question"],
                    "options": json.loads(r["options"]),
                    "answer": r["answer"],
                    "explanation": r["explanation"],
                    "concepts": json.loads(r["concepts"]),
                    "difficulty": r["difficulty"],
                    "source": r["source"],
                })
            return results
        finally:
            conn.close()

    def get_weakness_analysis(self) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT je.value AS concept,
                          COUNT(*) AS total_attempts,
                          SUM(CASE WHEN qa.is_correct = 0 THEN 1 ELSE 0 END) AS wrong_count
                   FROM quiz_attempts qa
                   JOIN questions q ON qa.question_id = q.id,
                        json_each(q.concepts) je
                   GROUP BY je.value
                   ORDER BY wrong_count DESC"""
            ).fetchall()
            return [
                {
                    "concept": r["concept"],
                    "total_attempts": r["total_attempts"],
                    "wrong_count": r["wrong_count"],
                    "error_rate": round(r["wrong_count"] / r["total_attempts"], 2)
                    if r["total_attempts"] > 0
                    else 0,
                }
                for r in rows
            ]
        finally:
            conn.close()
