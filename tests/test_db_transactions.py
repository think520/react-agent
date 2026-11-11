"""P1-14: read-modify-write needs the write lock from the start."""

import sqlite3

import pytest

from core.db import begin_immediate, create_connection


def test_begin_immediate_takes_the_write_lock_up_front(tmp_path):
    """A deferred transaction only takes the write lock at the first write.

    Two read-modify-write callers can therefore read the same snapshot and the
    loser dies with SQLITE_BUSY_SNAPSHOT at commit time - after all the work.
    BEGIN IMMEDIATE takes the lock at the start and fails fast instead.
    """
    path = str(tmp_path / "tx.db")
    writer = create_connection(path, busy_timeout_ms=0)
    writer.execute("CREATE TABLE t (v INTEGER)")
    writer.commit()

    begin_immediate(writer)
    writer.execute("INSERT INTO t VALUES (1)")

    blocked = create_connection(path, busy_timeout_ms=0)
    with pytest.raises(sqlite3.OperationalError):
        begin_immediate(blocked)

    # ...whereas a deferred transaction happily starts and only fails later.
    deferred = create_connection(path, busy_timeout_ms=0)
    deferred.execute("BEGIN DEFERRED")
    deferred.execute("SELECT count(*) FROM t").fetchone()
    with pytest.raises(sqlite3.OperationalError):
        deferred.execute("INSERT INTO t VALUES (2)")
    deferred.rollback()

    writer.commit()
    writer.close()
    deferred.close()
    blocked.close()


def test_begin_immediate_is_idempotent_inside_a_transaction(tmp_path):
    path = str(tmp_path / "tx2.db")
    connection = create_connection(path)
    connection.execute("CREATE TABLE t (v INTEGER)")
    connection.commit()
    connection.execute("BEGIN IMMEDIATE")
    begin_immediate(connection)  # must not raise "transaction within a transaction"
    connection.commit()
    connection.close()


def test_stores_migrate_once_per_database_file(tmp_path, monkeypatch):
    """建表 / 补列 / 回填按库文件只跑一次：纯读请求不再执行写事务（2026-11-11 审查）。"""
    import sqlite3

    from learning.store import LearningStore
    from quiz.store import QuizStore

    QuizStore(str(tmp_path))
    LearningStore(str(tmp_path))

    scripts: list[str] = []
    real_connect = sqlite3.connect

    class Spy:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def executescript(self, sql):
            scripts.append(sql)
            return self._conn.executescript(sql)

        def execute(self, sql, *args):
            if sql.lstrip().upper().startswith(("UPDATE", "ALTER", "DROP", "CREATE")):
                scripts.append(sql)
            return self._conn.execute(sql, *args)

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: Spy(real_connect(*a, **k)))
    QuizStore(str(tmp_path))
    LearningStore(str(tmp_path))
    assert scripts == [], scripts


def test_migration_reruns_when_the_database_is_recreated(tmp_path):
    import os

    from quiz.store import QuizStore

    store = QuizStore(str(tmp_path))
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(store.db_path + suffix):
            os.remove(store.db_path + suffix)
    again = QuizStore(str(tmp_path))
    assert again.add_question is not None
    import sqlite3

    conn = sqlite3.connect(again.db_path)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert "questions" in tables and "quiz_sessions" in tables
