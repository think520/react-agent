"""JSONL event-source session format + migration (AG-1, conditional).

P5G has not been accepted yet, so this module only provides the read/write and
one-time migration path for the append-only JSONL format. The online default
session format remains the legacy .json (see docs/AGENT_OPTIMIZATION_PLAN.md
AG-1 gating). Nothing here is wired into the live save path yet.

Format: one JSON object per line.
- session entry: id + type="session" + ts + session metadata.
- message entry: id + type="message" + ts + parentId + the message dict
  (role/content/tool_calls/tool_call_id/...).
- model_change entry: id + type="model_change" + ts + provider/model.

parentId is retained but defaults to linear (no fork tree).
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from typing import Any

ENTRY_SESSION = "session"
ENTRY_MESSAGE = "message"
ENTRY_MODEL_CHANGE = "model_change"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def session_to_jsonl(session: Any) -> str:
    """Serialize a Session to append-only JSONL text (does not mutate it)."""
    lines: list[str] = []
    lines.append(json.dumps({
        "id": session.session_id,
        "type": ENTRY_SESSION,
        "ts": session.created_at,
        "cwd": session.cwd,
        "workspace_root": session.workspace_root,
        "created_at": session.created_at,
        "last_active": session.last_active,
        "max_messages": session.max_messages,
        "name": session.name,
        "name_source": session.name_source,
        "library_id": session.library_id,
        "provider_name": session.provider_name,
        "model_name": session.model_name,
    }, ensure_ascii=False))
    for message in session.messages:
        entry: dict[str, Any] = {
            "id": _new_id(),
            "type": ENTRY_MESSAGE,
            "ts": session.last_active,
            "parentId": session.session_id,
        }
        entry.update(message)
        lines.append(json.dumps(entry, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def session_from_jsonl(text: str, session_class=None) -> Any:
    """Parse JSONL text back into a Session object (defaults to core.Session)."""
    if session_class is None:
        from core.session import Session as session_class

    meta: dict[str, Any] = {}
    messages: list[dict[str, Any]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        entry_type = entry.get("type")
        if entry_type == ENTRY_SESSION:
            meta = {
                "session_id": entry.get("id", entry.get("session_id", "")),
                "cwd": entry.get("cwd", ""),
                "workspace_root": entry.get("workspace_root", entry.get("cwd", "")),
                "created_at": entry.get("created_at", entry.get("ts", "")),
                "last_active": entry.get("last_active", entry.get("ts", "")),
                "max_messages": entry.get("max_messages"),
                "name": entry.get("name", ""),
                "name_source": entry.get("name_source", ""),
                "library_id": entry.get("library_id"),
                "provider_name": entry.get("provider_name"),
                "model_name": entry.get("model_name"),
            }
        elif entry_type == ENTRY_MESSAGE:
            message = {key: value for key, value in entry.items()
                       if key not in {"id", "type", "ts", "parentId"}}
            messages.append(message)
        # model_change entries are ignored on read (history projection).
    return session_class(**meta, messages=messages)


def migrate_json_to_jsonl(json_path: str, archive: bool = True) -> dict[str, Any]:
    """Migrate a legacy .json session to .jsonl (AG-1, conditional).

    Validates by loading the .json and round-tripping to JSONL before touching
    the original. On success the original is archived (renamed, never deleted);
    on any failure the original is left untouched.
    """
    from core.session import Session

    if not os.path.isfile(json_path):
        return {"ok": False, "code": "not_found", "error": f"Session file not found: {json_path}"}

    try:
        session = Session.load_from_file(json_path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": "invalid_session", "error": f"Failed to load session: {exc}"}

    text = session_to_jsonl(session)
    # Validate the round-trip before writing anything.
    try:
        restored = session_from_jsonl(text)
        assert restored.session_id == session.session_id
        assert len(restored.messages) == len(session.messages)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": "validation_failed", "error": f"Migration validation failed: {exc}"}

    jsonl_path = json_path[:-5] + ".jsonl" if json_path.endswith(".json") else json_path + ".jsonl"
    try:
        with open(jsonl_path, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as exc:
        return {"ok": False, "code": "write_failed", "error": f"Failed to write JSONL: {exc}"}

    if archive:
        archive_path = json_path + ".archived"
        try:
            shutil.move(json_path, archive_path)
        except OSError:
            # Archiving is best-effort; the JSONL already exists and validated.
            pass

    return {
        "ok": True,
        "jsonl_path": jsonl_path,
        "archived_path": archive_path if archive else None,
        "message_count": len(session.messages),
    }
