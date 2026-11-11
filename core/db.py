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
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Create a configured connection. Caller owns closing it."""
    connection = sqlite3.connect(path, check_same_thread=check_same_thread)
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


def begin_immediate(connection: sqlite3.Connection) -> None:
    """Take the write lock now instead of at the first write (P1-14).

    Read-modify-write needs it up front: with a deferred begin two callers can
    read the same snapshot, and the loser fails with SQLITE_BUSY_SNAPSHOT at
    commit time - after all the work is done. Safe to call inside a
    transaction that is already open.
    """
    if connection.in_transaction:
        return
    connection.execute("BEGIN IMMEDIATE")


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


# ── 一次性迁移记账 ─────────────────────────────────────────────────────
#
# 各个 store 在构造时跑「建表 + 补列 + 回填」。这些语句本身幂等，但每个请求都会新建 store，
# 于是纯读请求也在执行 executescript、全表扫描甚至 UPDATE 写事务（2026-11-11 审查：
# KBSQLiteStore 每次约 10ms，QuizStore 每次构造都提交一次回填）。
# 这里按「这个库文件」记一次：键里带文件的 inode 与创建时间，库被删掉重建后会重新迁移。

_MIGRATED: set[tuple[str, str, int, int]] = set()


def _file_identity(path: str) -> tuple[str, int, int] | None:
    import os

    try:
        stat = os.stat(path)
    except OSError:
        return None
    born = getattr(stat, "st_birthtime_ns", None) or stat.st_ctime_ns
    return (os.path.realpath(path), int(stat.st_ino), int(born))


def schema_migrated(scope: str, path: str) -> bool:
    """这个库文件在本进程里是否已经由 ``scope`` 迁移过。"""
    identity = _file_identity(path)
    return identity is not None and (scope, *identity) in _MIGRATED


def mark_schema_migrated(scope: str, path: str) -> None:
    identity = _file_identity(path)
    if identity is not None:
        _MIGRATED.add((scope, *identity))
