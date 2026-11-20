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


def clear_schema_migrated_cache(path_prefix: str | None = None) -> None:
    """Drop cached schema-migration entries (e.g. after restore or rollback)."""
    if path_prefix is None:
        _MIGRATED.clear()
        return
    import os

    prefix = os.path.realpath(path_prefix)
    to_remove = {
        entry for entry in _MIGRATED
        if entry[1] == prefix or entry[1].startswith(prefix + os.sep)
    }
    _MIGRATED.difference_update(to_remove)


def remove_sqlite_sidecars(db_path: str) -> None:
    """Delete WAL/SHM/journal sidecars next to ``db_path`` before replacing it.

    Replacing a ``.db`` file while a stale ``-wal`` remains on disk can make
    SQLite replay old WAL frames onto the restored database and corrupt it.
    """
    import os

    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = f"{db_path}{suffix}"
        if os.path.exists(sidecar):
            try:
                os.remove(sidecar)
            except OSError:
                pass


def integrity_check_sqlite(path: str, *, busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS) -> tuple[bool, str]:
    """Run ``PRAGMA integrity_check`` on a SQLite file and always close it."""
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(path)
        conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        rows = conn.execute("PRAGMA integrity_check").fetchall()
        messages = [str(row[0]) for row in rows if row]
        if messages == ["ok"]:
            return True, "ok"
        return False, "; ".join(messages) or "integrity_check returned empty result"
    except sqlite3.DatabaseError as exc:
        return False, str(exc)
    finally:
        if conn is not None:
            conn.close()


def backup_sqlite(
    source_path: str,
    dest_path: str,
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> None:
    """Create a WAL-consistent single-file snapshot using SQLite's online backup API.

    The destination file is verified with ``PRAGMA integrity_check`` before returning.
    """
    import os

    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    if os.path.exists(dest_path):
        os.remove(dest_path)
    remove_sqlite_sidecars(dest_path)

    src: sqlite3.Connection | None = None
    dst: sqlite3.Connection | None = None
    try:
        src = sqlite3.connect(source_path)
        src.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        dst = sqlite3.connect(dest_path)
        dst.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        src.backup(dst)
        dst.commit()
    finally:
        if dst is not None:
            dst.close()
        if src is not None:
            src.close()

    ok, detail = integrity_check_sqlite(dest_path, busy_timeout_ms=busy_timeout_ms)
    if not ok:
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except OSError:
                pass
        raise sqlite3.DatabaseError(f"SQLite backup integrity check failed ({os.path.basename(source_path)}): {detail}")
