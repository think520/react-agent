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
    deadline TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed')),
    current_day INTEGER
);

CREATE TABLE IF NOT EXISTS plan_progress (
    plan_id INTEGER NOT NULL,
    day INTEGER NOT NULL,
    task_index INTEGER NOT NULL,
    completed_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'auto' CHECK(source IN ('auto', 'manual')),
    PRIMARY KEY (plan_id, day, task_index)
);

CREATE INDEX IF NOT EXISTS idx_mastery_status ON mastery(status);
CREATE INDEX IF NOT EXISTS idx_mastery_next_review ON mastery(next_review);
CREATE INDEX IF NOT EXISTS idx_plan_progress_plan ON plan_progress(plan_id);
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
            # Migrate: add status and current_day columns to existing learning_plans
            try:
                conn.execute("ALTER TABLE learning_plans ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
            except sqlite3.OperationalError:
                pass  # column already exists
            try:
                conn.execute("ALTER TABLE learning_plans ADD COLUMN current_day INTEGER")
            except sqlite3.OperationalError:
                pass

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
                """INSERT INTO learning_plans (title, goal, steps, course, created_at, deadline, status, current_day)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (plan.title, plan.goal, json.dumps(plan.steps, ensure_ascii=False),
                 plan.course, now, plan.deadline, plan.status, plan.current_day),
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
            status=row["status"] if "status" in row.keys() else "active",
            current_day=row["current_day"] if "current_day" in row.keys() else None,
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
                status=r["status"] if "status" in r.keys() else "active",
                current_day=r["current_day"] if "current_day" in r.keys() else None,
            )
            for r in rows
        ]

    # --- Plan Progress ---

    def mark_task_done(self, plan_id: int, day: int, task_index: int, source: str = "manual") -> None:
        """Mark a specific task as completed."""
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO plan_progress (plan_id, day, task_index, completed_at, source)
                   VALUES (?, ?, ?, ?, ?)""",
                (plan_id, day, task_index, _now_iso(), source),
            )

    def mark_step_done(self, plan_id: int, day: int, task_count: int, source: str = "manual") -> None:
        """Mark all tasks in a step as completed."""
        now = _now_iso()
        with self._conn() as conn:
            for i in range(task_count):
                conn.execute(
                    """INSERT OR REPLACE INTO plan_progress (plan_id, day, task_index, completed_at, source)
                       VALUES (?, ?, ?, ?, ?)""",
                    (plan_id, day, i, now, source),
                )

    def get_progress(self, plan_id: int) -> dict[tuple[int, int], dict]:
        """Get all progress records for a plan. Key: (day, task_index)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT day, task_index, completed_at, source FROM plan_progress WHERE plan_id = ?",
                (plan_id,),
            ).fetchall()
        return {(r["day"], r["task_index"]): {"completed_at": r["completed_at"], "source": r["source"]} for r in rows}

    def is_task_done(self, plan_id: int, day: int, task_index: int) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM plan_progress WHERE plan_id = ? AND day = ? AND task_index = ?",
                (plan_id, day, task_index),
            ).fetchone()
        return row is not None

    def update_plan_status(self, plan_id: int, status: str | None = None, current_day: int | None = None) -> None:
        """Update plan status and/or current_day."""
        clauses = []
        params = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if current_day is not None:
            clauses.append("current_day = ?")
            params.append(current_day)
        if not clauses:
            return
        params.append(plan_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE learning_plans SET {', '.join(clauses)} WHERE id = ?",
                params,
            )

    def get_active_plans(self) -> list[LearningPlan]:
        """Get all plans with status='active'."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM learning_plans WHERE status = 'active' ORDER BY created_at DESC"
            ).fetchall()
        return [
            LearningPlan(
                id=r["id"], title=r["title"], goal=r["goal"],
                steps=json.loads(r["steps"]), course=r["course"],
                created_at=r["created_at"], deadline=r["deadline"],
                status=r["status"], current_day=r["current_day"],
            )
            for r in rows
        ]
