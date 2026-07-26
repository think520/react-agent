"""Shared SQLite helpers.

Every store in the project opens its own SQLite database; this module owns the
one correct way to do it so PRAGMA settings, busy timeout, row factory, and —
critically — connection close semantics are consistent.

Note: ``with sqlite3.connect(...)`` does NOT close the connection; it only
wraps a transaction. Use :func:`open_connection` instead.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

DEFAULT_BUSY_TIMEOUT_MS = 5000


def create_connection(
    path: str,
    *,
    wal: bool = True,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> sqlite3.Connection:
    """Create a configured connection. Caller owns closing it."""
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    if wal:
        connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


@contextmanager
def open_connection(
    path: str,
    *,
    wal: bool = True,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> Iterator[sqlite3.Connection]:
    """Context manager: commit on success, rollback on error, always close."""
    connection = create_connection(path, wal=wal, busy_timeout_ms=busy_timeout_ms)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def ensure_columns(
    connection: sqlite3.Connection,
    table: str,
    columns: dict[str, str],
) -> None:
    """Idempotent column migration: adds any column missing from ``table``.

    ``columns`` maps column name to its DDL fragment, e.g.
    ``{"difficulty": "TEXT DEFAULT 'medium'"}``.
    """
    existing = {
        row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, ddl in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
