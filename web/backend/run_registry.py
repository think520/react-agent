"""Grace period between a dropped SSE client and cancelling its run (P0-1).

Decision 3 (2026-09-14): a refresh or an accidental close must not throw the
turn away, and closing the tab must not keep it burning tokens. So a dropped
connection starts a timer; a reconnect to the replay endpoint within the grace
window cancels the timer, and letting it expire cancels the run.

The token itself is the cooperative primitive from core/cancellation.py: this
module only decides *when* to pull it.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from core.cancellation import CancelToken

logger = logging.getLogger(__name__)

DEFAULT_GRACE_SECONDS = 30.0
DISCONNECT_REASON = "client_disconnected"


@dataclass
class RunHandle:
    """One live run: its cancel token and its pending grace timer."""

    stream_id: str
    token: CancelToken = field(default_factory=CancelToken)
    grace_seconds: float = DEFAULT_GRACE_SECONDS
    timer: threading.Timer | None = None
    disconnected: bool = False


class RunRegistry:
    """Tracks live runs by stream id. Thread safe."""

    def __init__(self, grace_seconds: float = DEFAULT_GRACE_SECONDS) -> None:
        self.grace_seconds = grace_seconds
        self._lock = threading.RLock()
        self._runs: dict[str, RunHandle] = {}

    def start(self, stream_id: str, grace_seconds: float | None = None) -> RunHandle:
        window = self.grace_seconds if grace_seconds is None else float(grace_seconds)
        handle = RunHandle(stream_id=stream_id, grace_seconds=window)
        with self._lock:
            self._runs[stream_id] = handle
        return handle

    def get(self, stream_id: str) -> RunHandle | None:
        with self._lock:
            return self._runs.get(stream_id)

    def note_disconnect(self, stream_id: str) -> None:
        """Client dropped: start the grace timer (idempotent)."""
        with self._lock:
            handle = self._runs.get(stream_id)
            if handle is None or handle.timer is not None:
                return
            handle.disconnected = True
            timer = threading.Timer(handle.grace_seconds, self._expire, args=(stream_id,))
            timer.daemon = True
            handle.timer = timer
        timer.start()
        logger.info("Stream %s disconnected; cancelling in %.0fs", stream_id, handle.grace_seconds)

    def note_reconnect(self, stream_id: str) -> None:
        """Client came back inside the grace window: let the run continue."""
        with self._lock:
            handle = self._runs.get(stream_id)
            if handle is None or handle.timer is None:
                return
            timer, handle.timer = handle.timer, None
            handle.disconnected = False
        timer.cancel()
        logger.info("Stream %s reconnected; run continues", stream_id)

    def cancel_now(self, stream_id: str, reason: str = "") -> None:
        """Cancel a run without waiting (explicit user stop)."""
        with self._lock:
            handle = self._runs.get(stream_id)
        if handle is not None:
            handle.token.cancel(reason or "user_stopped")

    def finish(self, stream_id: str) -> None:
        """The run is over: drop the timer and the entry."""
        with self._lock:
            handle = self._runs.pop(stream_id, None)
        if handle is not None and handle.timer is not None:
            handle.timer.cancel()

    def _expire(self, stream_id: str) -> None:
        with self._lock:
            handle = self._runs.get(stream_id)
            if handle is None:
                # The run finished first; nothing to cancel.
                return
            handle.timer = None
        logger.info("Grace period expired for %s; cancelling the run", stream_id)
        handle.token.cancel(DISCONNECT_REASON)


def resolve_grace_seconds(config: dict | None) -> float:
    """Grace window for a dropped client: explicit config, else the default.

    P0-1: this is the budget between "the browser went away" and "stop the
    run". It was a hardcoded 30s; a desktop user on a slow refresh can
    legitimately need longer, and a test needs it shorter.
    """
    web_config = (config or {}).get("web") or {}
    raw = web_config.get("stream_grace_seconds")
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_GRACE_SECONDS
    return seconds if seconds >= 0 else DEFAULT_GRACE_SECONDS


_default_registry = RunRegistry()


def get_run_registry() -> RunRegistry:
    """Process-wide registry: stream ids are uuids, so one map is enough."""
    return _default_registry
