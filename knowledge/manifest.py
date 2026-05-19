import json
import os
from datetime import datetime, timezone

from .documents import DocumentRecord

MANIFEST_FILENAME = "manifest.json"


def load_manifest(workspace: str) -> dict:
    """Load .knowledge/manifest.json or return empty structure."""
    path = os.path.join(workspace, ".knowledge", MANIFEST_FILENAME)
    if not os.path.exists(path):
        return {"version": 1, "last_sync": None, "sync_summary": {}, "documents": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "last_sync": None, "sync_summary": {}, "documents": []}


def save_manifest(
    workspace: str,
    records: list[DocumentRecord],
    sync_summary: dict | None = None,
) -> None:
    """Write .knowledge/manifest.json with document records and sync metadata."""
    from .documents import document_records_to_dict

    path = os.path.join(workspace, ".knowledge", MANIFEST_FILENAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    manifest = {
        "version": 1,
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "sync_summary": sync_summary or {},
        "documents": document_records_to_dict(records),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
