"""LB-1.1: user editing of Markdown/text materials with checkpoints.

The original material is still the truth source — writes go through a
checkpoint and version store. Binary documents (PDF/DOCX/PPTX) stay read-only.

Versioning:
- Keep the last 10 full-file snapshots per document under
  .bobodan/checkpoints/<document_id>/.
- Rollback restores a snapshot and re-indexes.

Obsidian double-open conflict:
- The client sends the content hash it saw before editing. Before applying,
  we recompute the on-disk hash; on mismatch the caller chooses one of three
  actions: overwrite external changes / abandon the edit / save as a new file
  under raw/inbox/. No automatic merge, no bidirectional sync.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

from service._result import err as _err, ok as _ok

EDITABLE_KINDS = frozenset({"md", "txt", "markdown"})
MAX_VERSIONS = 10
CONFLICT_ACTIONS = frozenset({"overwrite", "abandon", "save_as_new"})


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class DocumentEditService:
    """Stateless-ish editor for managed Markdown/text materials."""

    def __init__(self, workspace: str) -> None:
        from service.kb_service import KBService

        self.workspace = os.path.abspath(workspace)
        self.kb = KBService(self.workspace)

    @property
    def checkpoints_dir(self) -> str:
        return os.path.join(self.workspace, ".bobodan", "checkpoints")

    def _doc_dir(self, document_id: str) -> str:
        return os.path.join(self.checkpoints_dir, document_id)

    @staticmethod
    def _editable(document: dict[str, Any]) -> bool:
        kind = str(document.get("kind") or "").lower()
        return kind in EDITABLE_KINDS

    def _read_file(self, path: str) -> str:
        if not path or not os.path.isfile(path):
            return ""
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def _raw_document(self, document_id: str) -> dict[str, Any] | None:
        from knowledge.paths import knowledge_path
        from rag.sqlite_store import KBSQLiteStore

        db_path = knowledge_path(self.workspace, "knowledge.db")
        if not os.path.exists(db_path):
            return None
        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            return store.get_document(document_id)
        finally:
            store.close()

    def read(self, document_id: str) -> dict[str, Any]:
        raw = self._raw_document(document_id)
        if raw is None:
            return _err(f"Document not found: {document_id}", code="document_not_found")
        editable = self._editable(raw)
        content = self._read_file(raw.get("path") or "") if editable else ""
        public = self.kb._public_document(raw)
        return _ok(
            document=public,
            content=content,
            editable=editable,
            content_hash=content_hash(content) if content else "",
        )

    def list_versions(self, document_id: str) -> dict[str, Any]:
        manifest_path = os.path.join(self._doc_dir(document_id), "manifest.json")
        if not os.path.isfile(manifest_path):
            return _ok(versions=[])
        with open(manifest_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return _ok(versions=data.get("versions", []))

    def edit(
        self,
        document_id: str,
        content: str,
        expected_hash: str | None = None,
        conflict_action: str = "overwrite",
        config: dict | None = None,
    ) -> dict[str, Any]:
        if conflict_action not in CONFLICT_ACTIONS:
            return _err("conflict_action must be overwrite, abandon, or save_as_new")

        document = self._raw_document(document_id)
        if document is None:
            return _err(f"Document not found: {document_id}", code="document_not_found")
        if not self._editable(document):
            return _err(
                "This document is read-only in this version",
                code="document_read_only",
            )

        path = document.get("path") or ""
        if not path or not self.kb._is_within_workspace(path, self.kb.managed_sources_dir):
            return _err(
                "This knowledge source cannot be edited here",
                code="document_read_only",
            )

        current = self._read_file(path)
        current_hash = content_hash(current)

        if expected_hash and expected_hash != current_hash:
            if conflict_action == "abandon":
                return _err(
                    "The document changed on disk since you started editing",
                    code="document_conflict",
                    details={"expected_hash": expected_hash, "actual_hash": current_hash},
                )
            if conflict_action == "save_as_new":
                return self._save_as_new(document, content)

        # Record a checkpoint of the pre-edit state, then overwrite.
        self._record_version(document_id, current)
        self._write_file(path, content)

        summary = self.kb._sync_registered_sources(mode="incremental", config=config or {})
        self.kb._mark_wiki_sources_stale(document_id, document.get("source") or path)

        return _ok(
            document_id=document_id,
            content_hash=content_hash(content),
            conflict="overwritten" if (expected_hash and expected_hash != current_hash) else None,
            sync=summary.to_dict(),
        )

    def rollback(self, document_id: str, version_id: str, config: dict | None = None) -> dict[str, Any]:
        versions = self.list_versions(document_id)
        if not versions.get("ok"):
            return versions
        match = next((v for v in versions["versions"] if v.get("id") == version_id), None)
        if match is None:
            return _err("Version not found", code="version_not_found")

        document = self._raw_document(document_id)
        if document is None:
            return _err(f"Document not found: {document_id}", code="document_not_found")
        path = document.get("path") or ""

        snapshot_path = os.path.join(self._doc_dir(document_id), f"{version_id}.md")
        if not os.path.isfile(snapshot_path):
            return _err("Version snapshot missing", code="version_not_found")

        with open(snapshot_path, "r", encoding="utf-8") as handle:
            restored = handle.read()

        self._record_version(document_id, self._read_file(path))
        self._write_file(path, restored)

        summary = self.kb._sync_registered_sources(mode="incremental", config=config or {})
        self.kb._mark_wiki_sources_stale(document_id, document.get("source") or path)
        return _ok(document_id=document_id, version_id=version_id, sync=summary.to_dict())

    def _save_as_new(self, document: dict[str, Any], content: str) -> dict[str, Any]:
        source = document.get("source") or "document"
        stem, extension = os.path.splitext(os.path.basename(source))
        if not extension:
            extension = ".md"
        inbox = os.path.join(self.workspace, "raw", "inbox")
        os.makedirs(inbox, exist_ok=True)
        target = os.path.join(inbox, f"{stem}-edited{extension}")
        counter = 2
        while os.path.exists(target):
            target = os.path.join(inbox, f"{stem}-edited ({counter}){extension}")
            counter += 1
        self._write_file(target, content)
        return _ok(saved_as_new=True, path=os.path.basename(target))

    def _record_version(self, document_id: str, content: str) -> None:
        if not content.strip():
            return
        doc_dir = self._doc_dir(document_id)
        os.makedirs(doc_dir, exist_ok=True)
        version_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        snapshot_path = os.path.join(doc_dir, f"{version_id}.md")
        self._write_file(snapshot_path, content)

        manifest_path = os.path.join(doc_dir, "manifest.json")
        versions: list[dict[str, Any]] = []
        if os.path.isfile(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as handle:
                versions = json.load(handle).get("versions", [])
        versions.append({
            "id": version_id,
            "created_at": version_id,
            "content_hash": content_hash(content),
        })
        # Keep only the last MAX_VERSIONS snapshots + manifest entries.
        versions = versions[-MAX_VERSIONS:]
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump({"versions": versions}, handle, ensure_ascii=False, indent=2)
        self._prune_old_snapshots(doc_dir, {v["id"] for v in versions})

    @staticmethod
    def _prune_old_snapshots(doc_dir: str, keep: set[str]) -> None:
        for name in os.listdir(doc_dir):
            if name.endswith(".md") and name[:-3] not in keep:
                try:
                    os.remove(os.path.join(doc_dir, name))
                except OSError:
                    pass

    @staticmethod
    def _write_file(path: str, content: str) -> None:
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
