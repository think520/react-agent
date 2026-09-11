import json
import os
import sqlite3
from knowledge.paths import knowledge_path
from core.db import create_connection
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
    created_at TEXT NOT NULL,
    bookmarked_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS quiz_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_ids TEXT NOT NULL DEFAULT '[]',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    updated_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    origin TEXT NOT NULL DEFAULT 'practice',
    personalization TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES quiz_sessions(id),
    question_id INTEGER NOT NULL REFERENCES questions(id),
    user_answer TEXT NOT NULL,
    is_correct INTEGER NOT NULL DEFAULT 0,
    verdict TEXT NOT NULL DEFAULT '',
    feedback TEXT NOT NULL DEFAULT '',
    answered_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_session ON quiz_attempts(session_id);
CREATE INDEX IF NOT EXISTS idx_attempts_question ON quiz_attempts(question_id);
CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(type);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# E18/D5: a question counts as "wrong" while its *latest* answer is not a pass.
# "partial" is deliberately not a wrong answer (E15), rows written before the
# verdict column existed fall back to is_correct, and an unrecognised verdict
# lands here too — so the four derived states always partition the bank instead
# of leaving an answered row that no filter and no count can reach. The alias in
# the fragment below is "qa".
_WRONG_VERDICT_SQL = (
    "qa.id IS NOT NULL"
    " AND qa.verdict <> 'partial'"
    " AND NOT (qa.verdict = 'correct' OR (qa.verdict = '' AND qa.is_correct = 1))"
)


def _bank_state(row: sqlite3.Row) -> str:
    """Derive the bank state from the latest attempt; never materialized.

    "incorrect" is the fallback bucket, so it has to stay in step with the
    wrong-answer SQL fragment: an answered question always lands in exactly one
    of the four states, and the counts keep summing to the bank total.
    """
    if row["attempt_id"] is None:
        return "unanswered"
    verdict = str(row["verdict"] or "")
    if verdict == "partial":
        return "partial"
    if verdict == "correct" or (not verdict and bool(row["is_correct"])):
        return "correct"
    return "incorrect"


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
        bookmarked_at=row["bookmarked_at"] if "bookmarked_at" in row.keys() else "",
    )


def _row_to_session(row: sqlite3.Row) -> QuizSession:
    return QuizSession(
        id=row["id"],
        question_ids=json.loads(row["question_ids"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        updated_at=row["updated_at"],
        status=row["status"],
        origin=row["origin"] if "origin" in row.keys() else "practice",
        personalization=json.loads(row["personalization"]) if "personalization" in row.keys() else [],
    )


def _row_to_attempt(row: sqlite3.Row) -> QuizAttempt:
    return QuizAttempt(
        id=row["id"],
        session_id=row["session_id"],
        question_id=row["question_id"],
        user_answer=row["user_answer"],
        is_correct=bool(row["is_correct"]),
        verdict=str(row["verdict"] or "") if "verdict" in row.keys() else "",
        feedback=row["feedback"],
        answered_at=row["answered_at"],
    )


class QuizStore:
    def __init__(self, workspace: str):
        self.db_path = knowledge_path(workspace, DB_FILENAME)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        return create_connection(self.db_path)

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
            if "bookmarked_at" not in question_columns:
                conn.execute(
                    "ALTER TABLE questions ADD COLUMN bookmarked_at TEXT NOT NULL DEFAULT ''"
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
            if "origin" not in session_columns:
                conn.execute(
                    "ALTER TABLE quiz_sessions ADD COLUMN origin TEXT NOT NULL DEFAULT 'practice'"
                )
            if "personalization" not in session_columns:
                conn.execute(
                    "ALTER TABLE quiz_sessions ADD COLUMN personalization TEXT NOT NULL DEFAULT '[]'"
                )
            attempt_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(quiz_attempts)").fetchall()
            }
            if "verdict" not in attempt_columns:
                conn.execute(
                    "ALTER TABLE quiz_attempts ADD COLUMN verdict TEXT NOT NULL DEFAULT ''"
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

    # --- Question bank (E18) ---

    _LATEST_ATTEMPT_JOIN = """
        LEFT JOIN quiz_attempts qa
               ON qa.id = (SELECT MAX(inner_attempt.id)
                             FROM quiz_attempts inner_attempt
                            WHERE inner_attempt.question_id = q.id)
    """

    @staticmethod
    def _bank_filters(
        *,
        state: str | None = None,
        qtype: str | None = None,
        course: str | None = None,
        concept: str | None = None,
        query: str | None = None,
    ) -> tuple[list[str], list]:
        clauses = ["1=1"]
        params: list = []
        if qtype:
            clauses.append("q.type = ?")
            params.append(qtype)
        if course:
            clauses.append("q.source LIKE ?")
            params.append(f"%{course}%")
        if concept:
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(q.concepts) item WHERE item.value = ?)"
            )
            params.append(concept)
        if query:
            clauses.append("(q.question LIKE ? OR q.concepts LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])
        normalized = (state or "").strip().lower()
        if normalized and normalized != "all":
            if normalized == "unanswered":
                clauses.append("qa.id IS NULL")
            elif normalized == "correct":
                clauses.append(
                    "(qa.verdict = 'correct' OR (qa.verdict = '' AND qa.is_correct = 1))"
                )
            elif normalized == "partial":
                clauses.append("qa.verdict = 'partial'")
            elif normalized == "incorrect":
                clauses.append(_WRONG_VERDICT_SQL)
            elif normalized == "bookmarked":
                clauses.append("q.bookmarked_at <> ''")
        return clauses, params

    @staticmethod
    def _bank_item(row: sqlite3.Row) -> dict:
        state = _bank_state(row)
        item = {
            "id": row["id"],
            "type": row["type"],
            "question": row["question"],
            "options": json.loads(row["options"]),
            "concepts": json.loads(row["concepts"]),
            "difficulty": row["difficulty"],
            "source": row["source"],
            "attribution_kind": row["attribution_kind"],
            "sources": json.loads(row["sources"]),
            "created_at": row["created_at"],
            "bookmarked": bool(row["bookmarked_at"]),
            "bookmarked_at": row["bookmarked_at"] or "",
            "state": state,
            "last_attempt": None,
        }
        if row["attempt_id"] is not None:
            item["last_attempt"] = {
                "attempt_id": row["attempt_id"],
                "user_answer": row["user_answer"],
                "verdict": str(
                    row["verdict"] or ("correct" if row["is_correct"] else "incorrect")
                ),
                "is_correct": bool(row["is_correct"]),
                "feedback": row["feedback"],
                "answered_at": row["answered_at"],
            }
            # Only answered questions reveal the reference answer; an unanswered
            # bank must not double as an answer sheet.
            item["answer"] = row["answer"]
            item["explanation"] = row["explanation"]
        return item

    def list_bank_questions(
        self,
        *,
        state: str | None = None,
        qtype: str | None = None,
        course: str | None = None,
        concept: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses, params = self._bank_filters(
            state=state, qtype=qtype, course=course, concept=concept, query=query
        )
        sql = f"""SELECT q.id, q.type, q.question, q.options, q.concepts, q.difficulty,
                         q.source, q.attribution_kind, q.sources, q.created_at,
                         q.bookmarked_at, q.answer, q.explanation,
                         qa.id AS attempt_id, qa.user_answer, qa.verdict, qa.feedback,
                         qa.answered_at, qa.is_correct
                    FROM questions q
                    {self._LATEST_ATTEMPT_JOIN}
                   WHERE {' AND '.join(clauses)}
                   ORDER BY q.id DESC
                   LIMIT ? OFFSET ?"""
        conn = self._connect()
        try:
            rows = conn.execute(
                sql, [*params, max(1, limit), max(0, offset)]
            ).fetchall()
            return [self._bank_item(row) for row in rows]
        finally:
            conn.close()

    def count_bank_questions(
        self,
        *,
        state: str | None = None,
        qtype: str | None = None,
        course: str | None = None,
        concept: str | None = None,
        query: str | None = None,
    ) -> int:
        clauses, params = self._bank_filters(
            state=state, qtype=qtype, course=course, concept=concept, query=query
        )
        sql = f"""SELECT COUNT(*) AS total
                    FROM questions q
                    {self._LATEST_ATTEMPT_JOIN}
                   WHERE {' AND '.join(clauses)}"""
        conn = self._connect()
        try:
            row = conn.execute(sql, params).fetchone()
            return int(row["total"]) if row else 0
        finally:
            conn.close()

    def bank_overview(self) -> dict:
        """Counts for the bank header and the agent's bank_overview tool."""
        conn = self._connect()
        try:
            row = conn.execute(
                f"""SELECT COUNT(*) AS total,
                           SUM(CASE WHEN qa.id IS NULL THEN 1 ELSE 0 END) AS unanswered,
                           SUM(CASE WHEN qa.verdict = 'partial' THEN 1 ELSE 0 END) AS partial,
                           SUM(CASE WHEN qa.verdict = 'correct'
                                      OR (qa.verdict = '' AND qa.is_correct = 1)
                                    THEN 1 ELSE 0 END) AS correct,
                           SUM(CASE WHEN {_WRONG_VERDICT_SQL} THEN 1 ELSE 0 END) AS incorrect,
                           SUM(CASE WHEN q.bookmarked_at <> '' THEN 1 ELSE 0 END) AS bookmarked
                      FROM questions q
                      {self._LATEST_ATTEMPT_JOIN}"""
            ).fetchone()
            by_type = {
                item["type"]: item["cnt"]
                for item in conn.execute(
                    "SELECT type, COUNT(*) AS cnt FROM questions GROUP BY type"
                ).fetchall()
            }
            by_concept = [
                {"concept": item["concept"], "count": item["cnt"]}
                for item in conn.execute(
                    """SELECT item.value AS concept, COUNT(*) AS cnt
                         FROM questions q, json_each(q.concepts) item
                        GROUP BY item.value
                        ORDER BY cnt DESC, concept ASC
                        LIMIT 10"""
                ).fetchall()
            ]
        finally:
            conn.close()
        ints = {
            key: int(row[key] or 0)
            for key in ("total", "unanswered", "partial", "correct", "incorrect", "bookmarked")
        }
        return {**ints, "by_type": by_type, "by_concept": by_concept}

    def set_bookmark(self, question_id: int, bookmarked: bool = True) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute(
                "UPDATE questions SET bookmarked_at = ? WHERE id = ?",
                (_now_iso() if bookmarked else "", question_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # --- Quiz Sessions ---

    def create_session(
        self,
        question_ids: list[int],
        origin: str = "practice",
        personalization: list[dict] | None = None,
    ) -> QuizSession:
        if origin not in {"practice", "review", "chat"}:
            origin = "practice"
        conn = self._connect()
        try:
            now = _now_iso()
            cur = conn.execute(
                """INSERT INTO quiz_sessions
                   (question_ids, started_at, updated_at, status, origin, personalization)
                   VALUES (?, ?, ?, 'active', ?, ?)""",
                (json.dumps(question_ids), now, now, origin, json.dumps(personalization or [], ensure_ascii=False)),
            )
            conn.commit()
            return QuizSession(
                id=cur.lastrowid,
                question_ids=question_ids,
                started_at=now,
                updated_at=now,
                status="active",
                origin=origin,
                personalization=personalization or [],
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
                   (session_id, question_id, user_answer, is_correct, verdict, feedback, answered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    attempt.session_id,
                    attempt.question_id,
                    attempt.user_answer,
                    1 if attempt.is_correct else 0,
                    attempt.verdict or ("correct" if attempt.is_correct else "incorrect"),
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
                f"""SELECT qa.id as attempt_id, qa.user_answer, qa.feedback, qa.answered_at,
                           q.id as question_id, q.type, q.question, q.options, q.answer,
                           q.explanation, q.concepts, q.difficulty, q.source
                    FROM quiz_attempts qa
                    JOIN questions q ON qa.question_id = q.id
                    WHERE qa.id = (SELECT MAX(latest.id) FROM quiz_attempts latest
                                    WHERE latest.question_id = qa.question_id)
                      AND {_WRONG_VERDICT_SQL}
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

    def get_wrong_answer(self, attempt_id: int) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                f"""SELECT qa.id as attempt_id, qa.user_answer, qa.feedback, qa.answered_at,
                           q.id as question_id, q.type, q.question, q.options, q.answer,
                           q.explanation, q.concepts, q.difficulty, q.source
                    FROM quiz_attempts qa
                    JOIN questions q ON qa.question_id = q.id
                    WHERE qa.id = ? AND {_WRONG_VERDICT_SQL}""",
                (attempt_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "attempt_id": row["attempt_id"],
                "user_answer": row["user_answer"],
                "feedback": row["feedback"],
                "answered_at": row["answered_at"],
                "question_id": row["question_id"],
                "type": row["type"],
                "question": row["question"],
                "options": json.loads(row["options"]),
                "answer": row["answer"],
                "explanation": row["explanation"],
                "concepts": json.loads(row["concepts"]),
                "difficulty": row["difficulty"],
                "source": row["source"],
            }
        finally:
            conn.close()

    def get_weakness_analysis(self) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                f"""SELECT je.value AS concept,
                           COUNT(*) AS total_attempts,
                           SUM(CASE WHEN {_WRONG_VERDICT_SQL} THEN 1 ELSE 0 END) AS wrong_count
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
