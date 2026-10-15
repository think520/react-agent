"""Import runs (E8): an import is observable and cancellable, not a black box.

Mirrors the chat run plumbing (web/backend/run_registry.py): a registry keyed by
id plus the cooperative primitive from core/cancellation.py. The difference is
what cancellation can promise: an import is CPU/disk work in a worker thread, so
the token is checked at **file boundaries** - files already accepted stay
accepted and the rest are reported as cancelled (docs/CANCELLATION_DESIGN.md,
"Python cannot kill a thread").

Plain threading.Thread rather than a threadpool: this is fire-and-forget work
whose whole point is that the client can poll it and cancel it.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field

from core.cancellation import CancelToken

logger = logging.getLogger(__name__)

RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"


@dataclass
class ImportRun:
    """One live import: its token, its coarse progress, and its final result."""

    import_id: str
    files_total: int = 0
    token: CancelToken = field(default_factory=CancelToken)
    status: str = RUNNING
    phase: str = "receiving"
    files_done: int = 0
    current: str = ""
    sources_total: int = 0
    sources_done: int = 0
    result: dict | None = None
    error: str = ""

    def snapshot(self) -> dict:
        return {
            "import_id": self.import_id,
            "status": self.status,
            "phase": self.phase,
            "files_total": self.files_total,
            "files_done": self.files_done,
            "current": self.current,
            "sources_total": self.sources_total,
            "sources_done": self.sources_done,
            "error": self.error,
            "result": self.result,
        }


class ImportRegistry:
    """Tracks live imports by id. Thread safe."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runs: dict[str, ImportRun] = {}

    def start(self, files_total: int) -> ImportRun:
        run = ImportRun(import_id=uuid.uuid4().hex[:16], files_total=files_total)
        with self._lock:
            self._runs[run.import_id] = run
        return run

    def get(self, import_id: str) -> ImportRun | None:
        with self._lock:
            return self._runs.get(import_id)

    def cancel(self, import_id: str) -> bool:
        run = self.get(import_id)
        if run is None:
            return False
        run.token.cancel("user_cancelled")
        logger.info("Import %s cancelled; it stops at the next file boundary", import_id)
        return True

    def record_progress(self, import_id: str, event: dict) -> None:
        run = self.get(import_id)
        if run is None:
            return
        phase = str(event.get("phase") or run.phase)
        run.phase = phase
        run.current = str(event.get("filename") or event.get("source") or "")
        if phase == "receiving":
            run.files_done = max(run.files_done, int(event.get("done") or 0))
        elif phase == "indexing":
            run.sources_done = max(run.sources_done, int(event.get("done") or 0))
            run.sources_total = max(run.sources_total, int(event.get("total") or 0))

    def finish(self, import_id: str, result: dict | None = None, error: str = "") -> None:
        run = self.get(import_id)
        if run is None:
            return
        run.result = result
        run.error = error
        if error:
            run.status = FAILED
        elif result is not None and result.get("cancelled"):
            run.status = CANCELLED
        else:
            run.status = COMPLETED

    def clear(self) -> None:
        """Test hook: forget every run."""
        with self._lock:
            self._runs.clear()
