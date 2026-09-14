"""Server-Sent Events helpers (AG-0.3: stream identity + replay)."""

from __future__ import annotations

import json
import os
import threading
from collections import deque
from collections.abc import AsyncIterator, Iterator
from typing import Any

import anyio

MAX_STREAM_ENTRIES = 5000
MAX_STREAM_BYTES = 8 * 1024 * 1024

# Long-lived SSE producers (a chat run blocks for seconds between events) are
# pumped on this dedicated lane instead of Starlette's shared request pool
# (anyio default: 40 threads), so active streams can never starve regular
# endpoint handlers of worker threads. Bounded so streams cannot spawn
# unbounded threads either.
STREAM_LANE_TOKENS = 16
_stream_lane_limiter = anyio.CapacityLimiter(total_tokens=STREAM_LANE_TOKENS)


class _StreamLaneDone(Exception):
    pass


def _lane_next(iterator: Iterator[Any]) -> Any:
    try:
        return next(iterator)
    except StopIteration:
        # Raw StopIteration must not cross a task boundary (asyncio may read
        # it as a clean return); same trick as starlette's own threadpool
        # iteration.
        raise _StreamLaneDone


async def iterate_on_stream_lane(generator: Iterator[Any]) -> AsyncIterator[Any]:
    """Drive a blocking SSE generator on the dedicated stream lane.

    Drop-in replacement for passing a sync iterator straight into
    StreamingResponse: consumers see the same items in the same order, but
    every blocked next() occupies the bounded SSE lane rather than the shared
    request threadpool.
    """
    iterator = iter(generator)
    while True:
        try:
            item = await anyio.to_thread.run_sync(
                _lane_next, iterator, limiter=_stream_lane_limiter
            )
        except _StreamLaneDone:
            return
        yield item


def encode_sse(event: str, data: Any) -> str:
    """Encode one SSE frame.

    Data is JSON-serialized so clients receive one stable object per event.
    """
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _frame_bytes(event: str, data: Any) -> int:
    try:
        return len(event.encode("utf-8", "ignore")) + len(
            json.dumps(data, ensure_ascii=False, default=str).encode("utf-8", "ignore")
        )
    except (TypeError, ValueError):
        return 0


class StreamBuffer:
    """Bounded per-stream buffer of emitted frames.

    Frames are evicted oldest-first once the entry or byte ceiling is crossed,
    so a very chatty turn cannot grow unbounded.
    """

    def __init__(self) -> None:
        self._frames: deque[dict] = deque()
        self._bytes = 0
        self._next_seq = 1

    def append(self, event: str, data: Any) -> int:
        seq = self._next_seq
        self._next_seq += 1
        frame = {"seq": seq, "event": event, "data": data}
        self._frames.append(frame)
        self._bytes += _frame_bytes(event, data)
        while self._frames and (
            len(self._frames) > MAX_STREAM_ENTRIES or self._bytes > MAX_STREAM_BYTES
        ):
            evicted = self._frames.popleft()
            self._bytes -= _frame_bytes(evicted["event"], evicted["data"])
            if self._bytes < 0:
                self._bytes = 0
        return seq

    def replay(self, after_seq: int) -> list[dict]:
        """Return frames whose seq is strictly greater than after_seq."""
        return [frame for frame in self._frames if frame["seq"] > after_seq]

    def clear(self) -> None:
        self._frames.clear()
        self._bytes = 0
        self._next_seq = 1

    def __len__(self) -> int:
        return len(self._frames)


class StreamStore:
    """Thread-safe map of stream_id -> StreamBuffer (AG-0.3).

    P1-17: when an EventLog is attached the events are persisted and the store
    reads them back from there. The in-memory buffer then plays no part - which
    is deliberate, because a buffer that keeps its own counter would hand out
    seq numbers that disagree with the log after a restart.
    """

    def __init__(self, log: Any = None) -> None:
        self._lock = threading.RLock()
        self._buffers: dict[str, StreamBuffer] = {}
        self._log = log

    def append(self, stream_id: str, event: str, data: Any) -> int:
        with self._lock:
            if self._log is not None:
                return self._log.append(stream_id, event, data)
            buffer = self._buffers.setdefault(stream_id, StreamBuffer())
            return buffer.append(event, data)

    def replay(self, stream_id: str, after_seq: int = 0) -> list[dict]:
        with self._lock:
            if self._log is not None:
                return self._log.read_after(stream_id, after_seq)
            buffer = self._buffers.get(stream_id)
            if buffer is None:
                return []
            return buffer.replay(after_seq)

    def clear(self, stream_id: str) -> None:
        with self._lock:
            self._buffers.pop(stream_id, None)
        if self._log is not None:
            self._log.clear(stream_id)

    def prune(self) -> int:
        """Apply the retention policy (P1-17 replaced clear-on-finish with it)."""
        if self._log is None:
            return 0
        return self._log.prune()

    def has(self, stream_id: str) -> bool:
        with self._lock:
            if stream_id in self._buffers:
                return True
        if self._log is not None:
            return self._log.max_seq(stream_id) > 0
        return False


class StreamEmitter:
    """Stamps seq + stream identity onto every SSE frame it emits."""

    def __init__(self, store: StreamStore, stream_id: str) -> None:
        self.store = store
        self.stream_id = stream_id

    def emit(self, event: str, data: dict[str, Any]) -> str:
        seq = self.store.append(self.stream_id, event, data)
        return encode_sse(event, {**data, "seq": seq, "stream_id": self.stream_id})

    def clear(self) -> None:
        self.store.clear(self.stream_id)


_default_store = StreamStore()
_stores: dict[str, StreamStore] = {}
_stores_lock = threading.Lock()


def get_default_stream_store() -> StreamStore:
    """Return the process-wide stream store used for reconnect replay."""
    return _default_store


def get_stream_store(workspace: str | None = None) -> StreamStore:
    """Store for one workspace; with a workspace its events are persisted.

    P1-17: the reconnect path is only real if the frames outlive the run and
    the process, so production callers pass the workspace.
    """
    if not workspace:
        return _default_store
    key = os.path.normcase(os.path.abspath(workspace))
    with _stores_lock:
        store = _stores.get(key)
        if store is None:
            from core.event_log import EventLog

            store = StreamStore(log=EventLog(workspace))
            _stores[key] = store
        return store
