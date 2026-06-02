"""Background asyncio event loop for running MCP coroutines from sync code.

MCP SDK is async-first. Bobodan's tool execution is synchronous. This
module bridges the two by running a dedicated event loop on a daemon
thread and submitting coroutines to it via `asyncio.run_coroutine_threadsafe`.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Coroutine

logger = logging.getLogger(__name__)


class AsyncEventLoop:
    """Process-wide singleton holding a background asyncio event loop.

    Lifecycle:
        1. First call to `get()` lazily creates the loop and starts the
           daemon thread.
        2. `run_sync(coro, timeout)` submits a coroutine to the loop and
           blocks the calling thread until it completes (or times out).
        3. `close()` stops the loop and joins the thread. Idempotent.

    Thread safety: every public method is safe to call from any thread.
    """

    _instance: "AsyncEventLoop | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run,
            name="mcp-client-event-loop",
            daemon=True,
        )
        self._started = False
        self._closed = False
        self._thread.start()
        self._started = True
        logger.debug("AsyncEventLoop started on thread %s", self._thread.name)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_forever()
        finally:
            self.loop.close()

    def run_sync(self, coro: Coroutine[Any, Any, Any], timeout: float | None = None) -> Any:
        """Run a coroutine on the background loop and block until done.

        Raises:
            TimeoutError: if the coroutine didn't finish within `timeout`.
            Exception: whatever the coroutine raised.
        """
        if self._closed:
            raise RuntimeError("AsyncEventLoop is closed")
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)

    def close(self) -> None:
        """Stop the loop and join the thread. Idempotent."""
        if self._closed:
            return
        self._closed = True
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
        except RuntimeError:
            pass
        self._thread.join(timeout=2.0)
        logger.debug("AsyncEventLoop closed")

    @classmethod
    def get(cls) -> "AsyncEventLoop":
        """Return the process-wide singleton, creating it on first call."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Tear down the singleton (used in tests)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.close()
                cls._instance = None
