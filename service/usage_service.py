"""Persistent, prompt-free LLM usage accounting."""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _home() -> Path:
    configured = os.getenv("BOBODAN_HOME")
    return Path(configured).expanduser().resolve() if configured else Path.home() / ".bobodan"


class UsageService:
    def __init__(self, home: str | None = None):
        root = Path(home).expanduser().resolve() if home else _home()
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "usage.db"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

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
        entries = self.list(days=days, run_id=run_id, limit=2000)
        cache_reported = [item for item in entries if item["cache_read_tokens"] is not None]
        costs = [float(item["cost_usd"]) for item in entries if item.get("cost_usd") is not None]
        model_distribution: dict[str, int] = {}
        provider_distribution: dict[str, int] = {}
        for item in entries:
            model = str(item.get("model") or "未报告")
            provider = str(item.get("provider") or "未报告")
            model_distribution[model] = model_distribution.get(model, 0) + 1
            provider_distribution[provider] = provider_distribution.get(provider, 0) + 1
        return {
            "days": days,
            "requests": len(entries),
            "errors": sum(item["status"] != "ok" for item in entries),
            "input_tokens": sum(item["input_tokens"] for item in entries),
            "output_tokens": sum(item["output_tokens"] for item in entries),
            "cache_read_tokens": sum(int(item["cache_read_tokens"] or 0) for item in cache_reported),
            "cache_miss_tokens": sum(int(item["cache_miss_tokens"] or 0) for item in entries if item["cache_miss_tokens"] is not None),
            "cache_reported": bool(cache_reported),
            "cost_usd": sum(costs),
            "cost_reported": bool(costs),
            "model_distribution": dict(sorted(model_distribution.items(), key=lambda item: (-item[1], item[0]))),
            "provider_distribution": dict(sorted(provider_distribution.items(), key=lambda item: (-item[1], item[0]))),
            "entries": entries,
        }
