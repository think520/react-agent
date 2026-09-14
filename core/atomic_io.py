"""Atomic, durable writes and cross-process write exclusion (P0-13, P1-8).

`raw/` is the immutable evidence layer and the session file is the only record
of a conversation, yet both were written with a bare `open(path, "w")`: a
crash, a full disk or a concurrent reader could see a truncated file, and two
writers silently overwrote each other. Preference and library files already
used temp+replace (`wiki.reliability.atomic_text`); this module is that same
pattern with durability (fsync) and cross-process exclusion added.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

REPLACE_RETRIES = 10
REPLACE_BACKOFF = 0.05
LOCK_POLL = 0.05

_path_locks: dict[str, threading.RLock] = {}
_path_locks_guard = threading.Lock()


class LockTimeout(RuntimeError):
    """Another process held the workspace write lock for too long."""


def path_lock(path: str) -> threading.RLock:
    """Process-local lock for one path (two tabs share the web server)."""
    key = os.path.normcase(os.path.abspath(path))
    with _path_locks_guard:
        lock = _path_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _path_locks[key] = lock
        return lock


def _fsync_directory(directory: str) -> None:
    """Best effort directory fsync so the rename itself is durable."""
    if os.name == "nt":  # not supported on Windows
        return
    try:
        descriptor = os.open(directory or ".", os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _replace_with_retry(source: str, target: str) -> None:
    """os.replace, retried on Windows permission errors.

    On Windows a reader, an indexer or a virus scanner can hold the target for
    a few milliseconds, which turns a legitimate replace into PermissionError.
    """
    last: OSError | None = None
    for attempt in range(REPLACE_RETRIES):
        try:
            os.replace(source, target)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(REPLACE_BACKOFF * (attempt + 1))
    if last is not None:
        raise last


def atomic_write_text(path: str, content: str) -> None:
    """Write `content` to `path` or leave the previous file untouched."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with path_lock(path):
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=directory,
            prefix=".tmp-",
            suffix=".part",
            delete=False,
        )
        temporary = handle.name
        try:
            with handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            _replace_with_retry(temporary, path)
            _fsync_directory(directory)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


def atomic_write_json(path: str, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _try_lock(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


@contextmanager
def workspace_write_lock(workspace: str, timeout: float = 30.0) -> Iterator[None]:
    """Hold the exclusive right to write one workspace, across processes.

    The CLI and the web server can both have the same workspace open; on
    Windows `fcntl` does not exist, so the lock is built on `msvcrt` there
    instead of silently doing nothing (a mistake the reference project made).
    """
    lock_path = os.path.join(os.path.abspath(workspace), ".bobodan", "workspace.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, "a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                _try_lock(handle)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise LockTimeout(f"another process is writing to {workspace}")
                time.sleep(LOCK_POLL)
        try:
            yield
        finally:
            _unlock(handle)
