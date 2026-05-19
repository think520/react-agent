import json
import os
import sqlite3
from datetime import datetime, timezone

from .schema import Mastery, LearningPlan

DB_FILENAME = "bobodan.db"

_LEARNING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mastery (
    concept TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'unseen' CHECK(status IN ('unseen', 'learning', 'mastered', 'needs_review')),
    score REAL NOT NULL DEFAULT 0.0,
    review_count INTEGER NOT NULL DEFAULT 0,
    consecutive_correct INTEGER NOT NULL DEFAULT 0,
    last_reviewed TEXT,
    next_review TEXT,
    source TEXT NOT NULL DEFAULT 'auto' CHECK(source IN ('auto', 'manual')),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    goal TEXT NOT NULL DEFAULT '',
    steps TEXT NOT NULL DEFAULT '[]',
    course TEXT,
    created_at TEXT NOT NULL,
    deadline TEXT
);

CREATE INDEX IF NOT EXISTS idx_mastery_status ON mastery(status);
CREATE INDEX IF NOT EXISTS idx_mastery_next_review ON mastery(next_review);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LearningStore:
    """SQLite-backed storage for mastery tracking and learning plans."""

    def __init__(self, workspace: str):
        self.db_path = os.path.join(workspace, ".knowledge", DB_FILENAME)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_schema()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript(_LEARNING_SCHEMA_SQL)

    # --- Mastery ---

    def get_mastery(self, concept: str) -> Mastery | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM mastery WHERE concept = ?", (concept,)
            ).fetchone()
        if not row:
            return None
        return Mastery(
            concept=row["concept"],
            status=row["status"],
            score=row["score"],
            review_count=row["review_count"],
            consecutive_correct=row["consecutive_correct"],
            last_reviewed=row["last_reviewed"],
            next_review=row["next_review"],
            source=row["source"],
            updated_at=row["updated_at"],
        )

    def upsert_mastery(self, m: Mastery) -> None:
        m.updated_at = _now_iso()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO mastery (concept, status, score, review_count,
                   consecutive_correct, last_reviewed, next_review, source, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(concept) DO UPDATE SET
                   status=excluded.status, score=excluded.score,
                   review_count=excluded.review_count,
                   consecutive_correct=excluded.consecutive_correct,
                   last_reviewed=excluded.last_reviewed,
                   next_review=excluded.next_review,
                   source=excluded.source, updated_at=excluded.updated_at""",
                (m.concept, m.status, m.score, m.review_count,
                 m.consecutive_correct, m.last_reviewed, m.next_review,
                 m.source, m.updated_at),
            )

    def list_mastery(self, status: str | None = None, limit: int = 100) -> list[Mastery]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM mastery WHERE status = ? ORDER BY score ASC, updated_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM mastery ORDER BY score ASC, updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            Mastery(
                concept=r["concept"], status=r["status"], score=r["score"],
                review_count=r["review_count"],
                consecutive_correct=r["consecutive_correct"],
                last_reviewed=r["last_reviewed"], next_review=r["next_review"],
                source=r["source"], updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def get_due_reviews(self, limit: int = 20) -> list[Mastery]:
        """Get concepts that are due for review (next_review <= now)."""
        now = _now_iso()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM mastery
                   WHERE status IN ('learning', 'needs_review')
                   AND next_review IS NOT NULL AND next_review <= ?
                   ORDER BY next_review ASC LIMIT ?""",
                (now, limit),
            ).fetchall()
        return [
            Mastery(
                concept=r["concept"], status=r["status"], score=r["score"],
                review_count=r["review_count"],
                consecutive_correct=r["consecutive_correct"],
                last_reviewed=r["last_reviewed"], next_review=r["next_review"],
                source=r["source"], updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def count_by_status(self) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM mastery GROUP BY status"
            ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}

    # --- Learning Plans ---

    def save_plan(self, plan: LearningPlan) -> int:
        now = _now_iso()
        with self._conn() as conn:
            cursor = conn.execute(
                """INSERT INTO learning_plans (title, goal, steps, course, created_at, deadline)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (plan.title, plan.goal, json.dumps(plan.steps, ensure_ascii=False),
                 plan.course, now, plan.deadline),
            )
            return cursor.lastrowid

    def get_plan(self, plan_id: int) -> LearningPlan | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM learning_plans WHERE id = ?", (plan_id,)
            ).fetchone()
        if not row:
            return None
        return LearningPlan(
            id=row["id"], title=row["title"], goal=row["goal"],
            steps=json.loads(row["steps"]), course=row["course"],
            created_at=row["created_at"], deadline=row["deadline"],
        )

    def list_plans(self, limit: int = 10) -> list[LearningPlan]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM learning_plans ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            LearningPlan(
                id=r["id"], title=r["title"], goal=r["goal"],
                steps=json.loads(r["steps"]), course=r["course"],
                created_at=r["created_at"], deadline=r["deadline"],
            )
            for r in rows
        ]
