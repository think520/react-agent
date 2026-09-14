"""Append-only SSE event log (P1-17).

The reconnect path existed end to end - seq stamping, a replay endpoint, seq
de-duplication in the client - but its storage was an in-memory buffer that
the run cleared in its `finally`, including on disconnect. So a reconnect could
never replay anything, and a restart lost the lot. Events now land in SQLite
keyed by (stream_id, seq); growth is bounded by a retention policy instead of
by wiping the log when a turn ends.
"""

from __future__ import annotations

import json
import os
import time

from core.db import begin_immediate, create_connection
from knowledge.paths import knowledge_dir

EVENTS_FILENAME = "events.db"
DEFAULT_RETENTION_DAYS = 7
DEFAULT_MAX_STREAMS = 200
MAX_READ_LIMIT = 5000

_DDL = """
CREATE TABLE IF NOT EXISTS stream_events (
    stream_id  TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    event      TEXT NOT NULL,
    data       TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (stream_id, seq)
);
CREATE INDEX IF NOT EXISTS ix_stream_events_created ON stream_events (created_at);
"""


class EventLog:
    """Persistent per-workspace event log with bounded growth."""

    def __init__(
        self,
        workspace: str,
        *,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        max_streams: int = DEFAULT_MAX_STREAMS,
    ) -> None:
        self.workspace = workspace
        self.retention_days = retention_days
        self.max_streams = max_streams
        self.path = os.path.join(knowledge_dir(workspace), EVENTS_FILENAME)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_DDL)

    def _connect(self):
        return create_connection(self.path, busy_timeout_ms=15000)

    def append(self, stream_id: str, event: str, data) -> int:
        """Append one frame and return its sequence number.

        The read-modify-write of the sequence runs inside BEGIN IMMEDIATE so two
        concurrent runs cannot hand out the same seq.
        """
        payload = json.dumps(data, ensure_ascii=False, default=str)
        with self._connect() as connection:
            begin_immediate(connection)
            row = connection.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM stream_events WHERE stream_id = ?",
                (stream_id,),
            ).fetchone()
            seq = int(row[0]) + 1
            connection.execute(
                "INSERT INTO stream_events (stream_id, seq, event, data, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (stream_id, seq, event, payload, time.time()),
            )
        return seq

    def read_after(self, stream_id: str, after_seq: int = 0, limit: int = MAX_READ_LIMIT) -> list[dict]:
        """Frames with seq > after_seq, in order."""
        capped = max(1, min(int(limit), MAX_READ_LIMIT))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT seq, event, data FROM stream_events"
                " WHERE stream_id = ? AND seq > ? ORDER BY seq ASC LIMIT ?",
                (stream_id, int(after_seq), capped),
            ).fetchall()
        frames: list[dict] = []
        for row in rows:
            try:
                data = json.loads(row["data"])
            except (TypeError, ValueError):
                data = {}
            frames.append({"seq": int(row["seq"]), "event": row["event"], "data": data})
        return frames

    def max_seq(self, stream_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM stream_events WHERE stream_id = ?",
                (stream_id,),
            ).fetchone()
        return int(row[0])

    def clear(self, stream_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM stream_events WHERE stream_id = ?", (stream_id,))

    def prune(self, *, now: float | None = None) -> int:
        """Drop frames older than the retention window and surplus streams."""
        moment = time.time() if now is None else now
        cutoff = moment - self.retention_days * 86400
        removed = 0
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM stream_events WHERE created_at < ?", (cutoff,)
            )
            removed += cursor.rowcount or 0
            stale = connection.execute(
                "SELECT stream_id, MAX(created_at) AS latest FROM stream_events"
                " GROUP BY stream_id ORDER BY latest DESC LIMIT -1 OFFSET ?",
                (self.max_streams,),
            ).fetchall()
            for row in stale:
                cursor = connection.execute(
                    "DELETE FROM stream_events WHERE stream_id = ?", (row["stream_id"],)
                )
                removed += cursor.rowcount or 0
        return removed
