"""Run production decoupled from the SSE response (A4 batch 3, P0-1).

Before this module a run only advanced while a client was reading the SSE
response: closing the tab parked the producer generator at its last yield, so
the grace period in web/backend/run_registry.py had nothing left to cancel -
the run was already dead, just not reaped.

Now create_run hands the producer to a background pump that drains it on its
own thread. The HTTP response is only a reader: it tails the persisted event
log (core/event_log.py) from a cursor, so a reconnect - or a different client -
can pick the same run up mid-flight.

Honest limits: Python cannot kill a thread. A run still only stops at the
cooperative checkpoints wired through core/cancellation.py; the pump changes
*who drives the producer*, not how cancellation works.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from typing import Any

from web.backend.sse import encode_sse

logger = logging.getLogger(__name__)

# How often an idle tail wakes up to look for new frames. Small enough to feel
# live on a LAN, large enough not to spin a core.
TAIL_POLL_SECONDS = 0.05


class RunPump:
    """Drains a blocking SSE producer on its own thread.

    The producer persists every frame as it emits it (StreamEmitter +
    StreamStore), so the pump buffers nothing itself: it only keeps the
    generator moving after - or without - a reader.
    """

    def __init__(
        self,
        stream_id: str,
        producer: Iterator[str],
        *,
        store: Any,
        registry: Any,
    ) -> None:
        self.stream_id = stream_id
        self.producer = producer
        self.store = store
        self.registry = registry
        self._done = threading.Event()
        self._error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._drain, name=f"sse-run-{stream_id}", daemon=True
        )

    @property
    def finished(self) -> bool:
        return self._done.is_set()

    @property
    def error(self) -> BaseException | None:
        return self._error

    def start(self) -> "RunPump":
        self._thread.start()
        return self

    def join(self, timeout: float | None = None) -> bool:
        """Wait for the producer to finish (tests and shutdown helpers)."""
        return self._done.wait(timeout)

    def _drain(self) -> None:
        try:
            for _frame in self.producer:
                pass
        except BaseException as exc:  # noqa: BLE001 - reported through .error
            self._error = exc
            logger.exception("Run pump for stream %s died", self.stream_id)
        finally:
            self._done.set()
            try:
                self.registry.finish(self.stream_id)
            except Exception:
                logger.exception("Could not retire run handle for %s", self.stream_id)
            unregister_pump(self)

    def tail(self, after_seq: int = 0) -> Iterator[str]:
        """Yield persisted frames until the producer stops emitting.

        The response is a reader, not the driver: closing this generator never
        touches the producer. It returns only once the pump has finished and
        the log has been drained up to its last frame.
        """
        cursor = after_seq
        while True:
            for frame in self.store.replay(self.stream_id, cursor):
                cursor = frame.get("seq", cursor)
                yield encode_sse(
                    frame["event"],
                    {**frame["data"], "seq": cursor, "stream_id": self.stream_id},
                )
            if self._done.is_set():
                # One more look so a frame emitted just before the flag is not
                # dropped; then this reader is genuinely at the end.
                if not self.store.replay(self.stream_id, cursor):
                    return
                continue
            time.sleep(TAIL_POLL_SECONDS)


_LIVE_PUMPS: dict[str, RunPump] = {}
_LIVE_LOCK = threading.Lock()


def register_pump(pump: RunPump) -> RunPump:
    with _LIVE_LOCK:
        _LIVE_PUMPS[pump.stream_id] = pump
    return pump


def get_live_pump(stream_id: str) -> RunPump | None:
    """The pump for a stream that is still producing, if any."""
    with _LIVE_LOCK:
        pump = _LIVE_PUMPS.get(stream_id)
    if pump is None or pump.finished:
        return None
    return pump


def live_stream_ids() -> list[str]:
    """Streams whose pump is still producing.

    The event log is the transport for a live run, so the retention sweep
    must be told about these or it could delete the run out from under its
    own reader.
    """
    with _LIVE_LOCK:
        return [sid for sid, pump in _LIVE_PUMPS.items() if not pump.finished]


def unregister_pump(pump: RunPump) -> None:
    with _LIVE_LOCK:
        if _LIVE_PUMPS.get(pump.stream_id) is pump:
            _LIVE_PUMPS.pop(pump.stream_id, None)
