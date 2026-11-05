import json
import os
from knowledge.paths import knowledge_path
from datetime import datetime, timezone

from core.db import ensure_columns, open_connection

from .schema import Mastery, LearningPlan

DB_FILENAME = "bobodan.db"

_LEARNING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS mastery (
    concept TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'unseen' CHECK(status IN ('unseen', 'learning', 'mastered', 'needs_review')),
    score REAL NOT NULL DEFAULT 0.0,
    review_count INTEGER NOT NULL DEFAULT 0,
    consecutive_correct INTEGER NOT NULL DEFAULT 0,
    ease_factor REAL NOT NULL DEFAULT 2.5,
    interval_days INTEGER NOT NULL DEFAULT 0,
    last_reviewed TEXT,
    next_review TEXT,
    source TEXT NOT NULL DEFAULT 'auto' CHECK(source IN ('auto', 'manual')),
    updated_at TEXT NOT NULL,
    -- E6.2：用户显式标记单独存。旧 status / score 列只作为历史快照与
    -- 「没有逐次历史时」的回退值，任何业务判断都不再读它们。
    manual_status TEXT,
    manual_at TEXT
);

-- W1 E6 第一步：逐次作答历史。掌握度引擎要「从历史推导」（近 N 次加权、置信帽），
-- 而聚合表只存计数与分数，推导不出来。每条自动作答在这里留一行（手动标记不写）。
-- E6.2：«evidence_key» 是幂等键（例如 quiz:<session>:<question>），同一证据重复写入
-- 不会新增一行 —— 这是「重复提交不重复累计证据」的结构保证。历史行为 NULL，不强制回填。
CREATE TABLE IF NOT EXISTS mastery_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept TEXT NOT NULL,
    is_correct INTEGER NOT NULL DEFAULT 0,
    verdict TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'quiz',
    created_at TEXT NOT NULL,
    evidence_key TEXT
);

CREATE INDEX IF NOT EXISTS idx_mastery_attempts_concept
    ON mastery_attempts(concept, id DESC);

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
        self.db_path = knowledge_path(workspace, DB_FILENAME)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_schema()

    def _conn(self):
        return open_connection(self.db_path)

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript(_LEARNING_SCHEMA_SQL)
            ensure_columns(conn, "learning_plans", {
                "status": "TEXT NOT NULL DEFAULT 'active'",
                "current_day": "INTEGER",
            })
            ensure_columns(conn, "mastery", {
                "ease_factor": "REAL NOT NULL DEFAULT 2.5",
                "interval_days": "INTEGER NOT NULL DEFAULT 0",
                "manual_status": "TEXT",
                "manual_at": "TEXT",
            })
            ensure_columns(conn, "mastery_attempts", {
                "evidence_key": "TEXT",
            })
        # 旧库建表时没有幂等键；唯一索引必须在补列之后建 —— 放进上面的 executescript
        # 会在旧表上引用不存在的列，整个学习模块直接打不开。
        # 粒度是 (concept, evidence_key)：一道题可能同时考多个概念，同一次作答要为每个
        # 概念各写一条证据，只按 evidence_key 唯一会让它们互相覆盖（后写的顶掉先写的）。
        with self._conn() as conn:
            conn.execute("DROP INDEX IF EXISTS idx_mastery_attempts_evidence_key")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_mastery_attempts_concept_evidence "
                "ON mastery_attempts(concept, evidence_key)"
            )

    # --- Mastery ---

    def get_mastery(self, concept: str) -> Mastery | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM mastery WHERE concept = ?", (concept,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_mastery(row)

    def record_mastery_attempt(
        self,
        concept: str,
        is_correct: bool,
        verdict: str = "",
        source: str = "quiz",
        evidence_key: str | None = None,
    ) -> None:
        """记下**这一次**作答（W1 E6 第一步）。

        聚合表只存计数与分数，引擎要「近 N 次加权」就必须有逐次历史；
        手动标记掌握度不走这里（那不是一次作答）。

        E6.2：«evidence_key» 存在时是幂等键。同一键重复写入会更新那一行（最新结果
        胜出并移到时间线末尾），而不会新增证据 —— 同一练习会话里反复答同一道题
        不该把掌握度推上去。不传则保持旧行为（每次一行）。
        """
        if not concept:
            return
        with self._conn() as conn:
            if evidence_key:
                # REPLACE（而非 ON CONFLICT DO UPDATE）是故意的：同一条证据被重新作答时，
                # 它应该**移到最后** —— 推导看的是「最近发生了什么」。
                conn.execute(
                    """INSERT OR REPLACE INTO mastery_attempts
                       (concept, is_correct, verdict, source, created_at, evidence_key)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (concept, 1 if is_correct else 0, verdict or "", source or "quiz", _now_iso(), evidence_key),
                )
                return
            conn.execute(
                """INSERT INTO mastery_attempts
                   (concept, is_correct, verdict, source, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (concept, 1 if is_correct else 0, verdict or "", source or "quiz", _now_iso()),
            )

    def recent_mastery_attempts(self, concept: str, limit: int = 5) -> list[dict]:
        """这个概念最近的作答（新 → 旧）。没有历史就返回空列表。"""
        if not concept:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT concept, is_correct, verdict, source, created_at
                   FROM mastery_attempts
                   WHERE concept = ?
                   ORDER BY id DESC
                   LIMIT ?""",
                (concept, max(1, int(limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_mastery_attempts(self, concept: str) -> int:
        """这个概念一共有多少条作答证据（不被推导窗口截断）。"""
        if not concept:
            return 0
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM mastery_attempts WHERE concept = ?",
                (concept,),
            ).fetchone()
        return int(row["cnt"] or 0) if row else 0

    def latest_attempt_at(self, concept: str) -> str | None:
        """最近一条作答证据的时间（用于与手动标记比先后）。"""
        if not concept:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT created_at FROM mastery_attempts WHERE concept = ? ORDER BY id DESC LIMIT 1",
                (concept,),
            ).fetchone()
        return str(row["created_at"]) if row else None

    def recent_attempts_by_concept(self, limit_per_concept: int = 5) -> dict[str, list[dict]]:
        """一次查出每个概念最近的 N 条作答（新 → 旧）。

        列表页需要给每个概念都算一次推导；逐个查库是 N 次往返，这里一次拿完。
        """
        cap = max(1, int(limit_per_concept))
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT concept, is_correct, verdict, source, created_at
                   FROM mastery_attempts ORDER BY id DESC"""
            ).fetchall()
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            bucket = grouped.setdefault(row["concept"], [])
            if len(bucket) < cap:
                bucket.append(dict(row))
        return grouped

    def mastery_attempt_stats(self) -> dict[str, dict]:
        """每个概念的证据总数与最新时间（一次 GROUP BY）。"""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT concept, COUNT(*) AS total, MAX(created_at) AS latest_at
                   FROM mastery_attempts GROUP BY concept"""
            ).fetchall()
        return {
            row["concept"]: {"total": row["total"], "latest_at": row["latest_at"]}
            for row in rows
        }

    def upsert_mastery(self, m: Mastery) -> None:
        m.updated_at = _now_iso()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO mastery (concept, status, score, review_count,
                   consecutive_correct, ease_factor, interval_days,
                   last_reviewed, next_review, source, updated_at,
                   manual_status, manual_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(concept) DO UPDATE SET
                   status=excluded.status, score=excluded.score,
                   review_count=excluded.review_count,
                   consecutive_correct=excluded.consecutive_correct,
                   ease_factor=excluded.ease_factor,
                   interval_days=excluded.interval_days,
                   last_reviewed=excluded.last_reviewed,
                   next_review=excluded.next_review,
                   source=excluded.source, updated_at=excluded.updated_at,
                   manual_status=excluded.manual_status,
                   manual_at=excluded.manual_at""",
                (m.concept, m.status, m.score, m.review_count,
                 m.consecutive_correct, m.ease_factor, m.interval_days,
                 m.last_reviewed, m.next_review,
                 m.source, m.updated_at,
                 m.manual_status, m.manual_at),
            )

    @staticmethod
    def _row_to_mastery(row) -> Mastery:
        keys = row.keys()
        return Mastery(
            concept=row["concept"], status=row["status"], score=row["score"],
            review_count=row["review_count"],
            consecutive_correct=row["consecutive_correct"],
            ease_factor=row["ease_factor"], interval_days=row["interval_days"],
            last_reviewed=row["last_reviewed"], next_review=row["next_review"],
            source=row["source"], updated_at=row["updated_at"],
            manual_status=row["manual_status"] if "manual_status" in keys else None,
            manual_at=row["manual_at"] if "manual_at" in keys else None,
        )

    def list_mastery(self, status: str | None = None, limit: int = 100) -> list[Mastery]:
        """原始掌握度行。

        E6.2：«status» 过滤器与内部排序读的都是旧口径列，只适合迁移前的旧代码；
        业务侧请用 «learning.contract.mastery_states»（按推导结果过滤与排序）。
        """
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
        return [self._row_to_mastery(r) for r in rows]

    def get_due_reviews(self, limit: int = 20) -> list[Mastery]:
        """Get concepts that are due for review (next_review <= now).

        E6.2：只按**调度结果**筛选（next_review），不再看旧 status 列 ——
        「该不该复习」是调度问题，「是不是掌握了」是推导问题，两者分开。
        """
        now = _now_iso()
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT * FROM mastery
                   WHERE next_review IS NOT NULL AND next_review <= ?
                   ORDER BY next_review ASC LIMIT ?""",
                (now, limit),
            ).fetchall()
        return [self._row_to_mastery(r) for r in rows]

    def get_next_scheduled_review(self) -> Mastery | None:
        """Get the next future review so an empty queue can explain what is next."""
        now = _now_iso()
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM mastery
                   WHERE next_review IS NOT NULL AND next_review > ?
                   ORDER BY next_review ASC LIMIT 1""",
                (now,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_mastery(row)

    def count_by_status(self) -> dict[str, int]:
        """旧口径的状态计数（库里存的历史快照）。

        E6.2：不要再拿它做业务判断或展示；唯一来源是 «learning.contract»。
        """
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
