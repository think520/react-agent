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
