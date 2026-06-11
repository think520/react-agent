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


# --- Trace reading ---

def list_traces(workspace: str, limit: int = 10) -> list[dict]:
    """List recent trace files, newest first.

    Returns list of {path, session_id, started_at, file_size} dicts.
    """
    trace_dir = os.path.join(workspace, ".bobodan", "traces")
    if not os.path.isdir(trace_dir):
        return []

    entries = []
    for name in os.listdir(trace_dir):
        if not name.endswith(".jsonl"):
            continue
        full = os.path.join(trace_dir, name)
        try:
            stat = os.stat(full)
        except OSError:
            continue
        # Filename format: {session_id}_{timestamp}.jsonl
        # Timestamp is like 20260611T123456Z
        stem = name[:-6]  # strip .jsonl
        parts = stem.split("_", 1)
        session_id = parts[0] if parts else stem
        ts_str = parts[1] if len(parts) > 1 else ""
        # Parse timestamp from filename for reliable ordering
        started_at = ""
        if ts_str and len(ts_str) >= 15:
            try:
                dt = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ")
                started_at = dt.replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                started_at = ""
        if not started_at:
            started_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        entries.append({
            "path": full,
            "session_id": session_id,
            "started_at": started_at,
            "file_size": stat.st_size,
        })

    entries.sort(key=lambda e: e["started_at"], reverse=True)
    return entries[:limit]


def read_trace(path: str) -> list[dict]:
    """Parse a JSONL trace file into a list of event dicts."""
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def summarize_trace(events: list[dict]) -> dict:
    """Compute summary stats from a list of trace events.

    Returns {tool_count, tools_ok, tools_fail, duration, termination_reason,
             first_ts, last_ts, tool_details}.
    """
    tool_starts: dict[str, dict] = {}  # tool_call_id -> start event
    tool_details: list[dict] = []
    termination_reason = ""
    first_ts = ""
    last_ts = ""

    for ev in events:
        ev_type = ev.get("type", "")
        ts = ev.get("ts", "")
        if ts:
            if not first_ts:
                first_ts = ts
            last_ts = ts

        if ev_type == "tool_start":
            tcid = ev.get("tool_call_id", "")
            tool_starts[tcid] = ev

        elif ev_type == "tool_end":
            tcid = ev.get("tool_call_id", "")
            start = tool_starts.pop(tcid, None)
            tool_details.append({
                "tool_name": ev.get("tool_name", "?"),
                "ok": ev.get("ok", False),
                "elapsed": ev.get("elapsed", 0.0),
                "result_summary": ev.get("result_summary"),
            })

        elif ev_type == "assistant_done":
            termination_reason = ev.get("termination_reason", "")

        elif ev_type == "error":
            tool_details.append({
                "tool_name": "(error)",
                "ok": False,
                "elapsed": 0.0,
                "result_summary": ev.get("error", ""),
            })

    tools_ok = sum(1 for t in tool_details if t["ok"])
    tools_fail = sum(1 for t in tool_details if not t["ok"])

    # Compute wall-clock duration from first to last timestamp
    duration = 0.0
    if first_ts and last_ts:
        try:
            t0 = datetime.fromisoformat(first_ts)
            t1 = datetime.fromisoformat(last_ts)
            duration = (t1 - t0).total_seconds()
        except (ValueError, TypeError):
            pass

    return {
        "tool_count": len(tool_details),
        "tools_ok": tools_ok,
        "tools_fail": tools_fail,
        "duration": round(duration, 1),
        "termination_reason": termination_reason,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "tool_details": tool_details,
    }
