"""Persistent, prompt-free LLM usage accounting."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.db import open_connection


def _home() -> Path:
    configured = os.getenv("BOBODAN_HOME")
    return Path(configured).expanduser().resolve() if configured else Path.home() / ".bobodan"


class UsageService:
    def __init__(self, home: str | None = None):
        root = Path(home).expanduser().resolve() if home else _home()
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "usage.db"
        self._init_db()

    def _connect(self):
        return open_connection(str(self.path), wal=False)

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS llm_usage (
                    request_id TEXT PRIMARY KEY,
                    occurred_at TEXT NOT NULL,
                    subsystem TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    run_id TEXT,
                    provider TEXT,
                    model TEXT,
                    status TEXT NOT NULL,
                    duration_ms INTEGER,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    cache_read_tokens INTEGER,
                    cache_miss_tokens INTEGER,
                    reasoning_tokens INTEGER,
                    cost_usd REAL,
                    error_kind TEXT
                )
            """)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(llm_usage)")}
            if "cost_usd" not in columns:
                connection.execute("ALTER TABLE llm_usage ADD COLUMN cost_usd REAL")

    def record(
        self,
        response: Any = None,
        *,
        subsystem: str,
        operation: str,
        run_id: str | None = None,
        duration_ms: int | None = None,
        status: str = "ok",
        provider: str = "",
        model: str = "",
        error_kind: str | None = None,
    ) -> dict[str, Any]:
        usage = getattr(response, "usage", None) or {}
        request_id = str(getattr(response, "request_id", "") or uuid.uuid4().hex)
        payload = {
            "request_id": request_id,
            "occurred_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "subsystem": subsystem,
            "operation": operation,
            "run_id": run_id,
            "provider": str(getattr(response, "provider", "") or provider),
            "model": str(getattr(response, "model", "") or model),
            "status": status,
            "duration_ms": duration_ms,
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cache_read_tokens": usage.get("cache_read_tokens"),
            "cache_miss_tokens": usage.get("cache_miss_tokens"),
            "reasoning_tokens": usage.get("reasoning_tokens"),
            "cost_usd": usage.get("cost_usd"),
            "error_kind": error_kind,
        }
        with self._connect() as connection:
            connection.execute("""
                INSERT OR REPLACE INTO llm_usage (
                    request_id, occurred_at, subsystem, operation, run_id, provider, model,
                    status, duration_ms, input_tokens, output_tokens, cache_read_tokens,
                    cache_miss_tokens, reasoning_tokens, cost_usd, error_kind
                ) VALUES (
                    :request_id, :occurred_at, :subsystem, :operation, :run_id, :provider, :model,
                    :status, :duration_ms, :input_tokens, :output_tokens, :cache_read_tokens,
                    :cache_miss_tokens, :reasoning_tokens, :cost_usd, :error_kind
                )
            """, payload)
        return payload

    def list(self, *, days: int = 7, run_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        clauses = ["occurred_at >= datetime('now', ?)"]
        params: list[Any] = [f"-{max(1, min(days, 365))} days"]
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        params.append(max(1, min(limit, 2000)))
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM llm_usage WHERE {' AND '.join(clauses)} ORDER BY occurred_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self, *, days: int = 7, run_id: str | None = None) -> dict[str, Any]:
        clauses = ["occurred_at >= datetime('now', ?)"]
        params: list[Any] = [f"-{max(1, min(days, 365))} days"]
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        where = " AND ".join(clauses)

        with self._connect() as connection:
            agg = connection.execute(f"""
                SELECT
                    COUNT(*)                                          AS requests,
                    SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END) AS errors,
                    COALESCE(SUM(input_tokens), 0)                   AS input_tokens,
                    COALESCE(SUM(output_tokens), 0)                  AS output_tokens,
                    COALESCE(SUM(cache_read_tokens), 0)              AS cache_read_tokens,
                    COALESCE(SUM(cache_miss_tokens), 0)              AS cache_miss_tokens,
                    COUNT(cache_read_tokens)                         AS cache_reported_count,
                    COALESCE(SUM(cost_usd), 0.0)                     AS cost_usd,
                    COUNT(cost_usd)                                  AS cost_reported_count
                FROM llm_usage WHERE {where}
            """, params).fetchone()

            model_rows = connection.execute(f"""
                SELECT COALESCE(NULLIF(model, ''), '未报告') AS model, COUNT(*) AS cnt
                FROM llm_usage WHERE {where}
                GROUP BY model ORDER BY cnt DESC, model
            """, params).fetchall()

            provider_rows = connection.execute(f"""
                SELECT COALESCE(NULLIF(provider, ''), '未报告') AS provider, COUNT(*) AS cnt
                FROM llm_usage WHERE {where}
                GROUP BY provider ORDER BY cnt DESC, provider
            """, params).fetchall()

            entries = connection.execute(f"""
                SELECT * FROM llm_usage WHERE {where} ORDER BY occurred_at DESC LIMIT 500
            """, params).fetchall()

        return {
            "days": days,
            "requests": agg["requests"],
            "errors": agg["errors"] or 0,
            "input_tokens": agg["input_tokens"],
            "output_tokens": agg["output_tokens"],
            "cache_read_tokens": agg["cache_read_tokens"],
            "cache_miss_tokens": agg["cache_miss_tokens"],
            "cache_reported": agg["cache_reported_count"] > 0,
            "cost_usd": agg["cost_usd"],
            "cost_reported": agg["cost_reported_count"] > 0,
            "model_distribution": {r["model"]: r["cnt"] for r in model_rows},
            "provider_distribution": {r["provider"]: r["cnt"] for r in provider_rows},
            "entries": [dict(r) for r in entries],
        }
