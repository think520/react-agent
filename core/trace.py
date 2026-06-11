import json
import logging
import os
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Event types written to trace (assistant_delta is excluded — too noisy).
_TRACE_EVENT_TYPES = {"tool_start", "tool_end", "assistant_done", "error"}

# Fields that may contain secrets — values are replaced with "***".
_SECRET_FIELDS = frozenset({
    "api_key", "api_secret", "token", "password", "secret",
    "authorization", "access_token", "refresh_token",
})

# Truncate large content blobs to keep trace files manageable.
_MAX_CONTENT_LEN = 500


def _redact_value(key: str, value: object) -> object:
    if isinstance(key, str) and key.lower() in _SECRET_FIELDS:
        return "***"
    return value


def _redact_obj(obj: object, depth: int = 0) -> object:
    """Recursively redact secret fields in dicts/lists."""
    if depth > 10:
        return obj
    if isinstance(obj, dict):
        return {k: _redact_obj(_redact_value(k, v), depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_obj(item, depth + 1) for item in obj]
    return obj


def _truncate(text: str, limit: int = _MAX_CONTENT_LEN) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


class TraceWriter:
    """Append-only JSONL trace writer for agent runs.

    Writes tool_start / tool_end / assistant_done / error events to
    ``.bobodan/traces/{session_id}_{timestamp}.jsonl``.

    Thread-safe: a lock protects file writes so events from background
    agent threads don't interleave mid-line.
    """

    def __init__(self, session_id: str, workspace: str) -> None:
        trace_dir = os.path.join(workspace, ".bobodan", "traces")
        os.makedirs(trace_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_id = session_id[:12] if len(session_id) > 12 else session_id
        self._path = os.path.join(trace_dir, f"{safe_id}_{ts}.jsonl")
        self._lock = threading.Lock()
        logger.debug("[TraceWriter] trace file: %s", self._path)

    @property
    def path(self) -> str:
        return self._path

    def write(self, event: dict) -> None:
        """Write a single event if its type is in the traced set."""
        event_type = event.get("type", "")
        if event_type not in _TRACE_EVENT_TYPES:
            return

        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
        }

        if event_type == "tool_start":
            record["tool_call_id"] = event.get("tool_call_id", "")
            record["tool_name"] = event.get("tool_name", "")
            record["args"] = _redact_obj(event.get("args", {}))

        elif event_type == "tool_end":
            record["tool_call_id"] = event.get("tool_call_id", "")
            record["tool_name"] = event.get("tool_name", "")
            record["ok"] = event.get("ok", False)
            record["elapsed"] = round(event.get("elapsed", 0.0), 3)
            summary = event.get("result_summary")
            if summary:
                record["result_summary"] = summary
            content = event.get("content", "")
            if content:
                record["content"] = _truncate(content)

        elif event_type == "assistant_done":
            record["termination_reason"] = event.get("termination_reason", "")
            content = event.get("content", "")
            if content:
                record["content"] = _truncate(content)

        elif event_type == "error":
            record["error"] = _truncate(str(event.get("error", "")))

        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            try:
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                logger.warning("[TraceWriter] failed to write trace event")
