import json
import os
from datetime import datetime, timezone

from .documents import DocumentRecord
from .paths import knowledge_path

MANIFEST_FILENAME = "manifest.json"


def load_manifest(workspace: str) -> dict:
    """Load .knowledge/manifest.json or return empty structure."""
    path = knowledge_path(workspace, MANIFEST_FILENAME)
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
    vault_path: str | None = None,
) -> None:
    """Write .knowledge/manifest.json with document records and sync metadata."""
    from .documents import document_records_to_dict

    path = knowledge_path(workspace, MANIFEST_FILENAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Load existing manifest to preserve vault_path if not provided
    existing = load_manifest(workspace)
    if vault_path is None:
        vault_path = existing.get("vault_path")

    manifest = {
        "version": 1,
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "vault_path": vault_path,
        "sync_summary": sync_summary or {},
        "documents": document_records_to_dict(records),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
