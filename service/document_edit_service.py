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

from core.atomic_io import atomic_write_json, atomic_write_text
from service._result import err as _err, ok as _ok

EDITABLE_KINDS = frozenset({"md", "txt", "markdown", "course_document", "obsidian_note"})

# System areas that must never be edited through the document editor: the
# rebuildable runtime index (.knowledge), version snapshots and archives.
# Legacy workspaces keep real user content under .bobodan/sources and
# .bobodan/managed-vault, so .bobodan itself cannot be blanket-banned.
_SYSTEM_DIR_PARTS = frozenset(
    part + os.sep
    for part in (
        os.sep + ".knowledge",
        os.sep + ".bobodan" + os.sep + "checkpoints",
        os.sep + ".bobodan" + os.sep + "archive",
    )
)
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

    # 原文查看用的媒体类型：PDF 交给浏览器内置阅读器，Office 走下载/系统打开。
    RAW_MEDIA_TYPES = {
        ".md": "text/markdown; charset=utf-8",
        ".markdown": "text/markdown; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }

    def resolve_source_path(self, path: str) -> str | None:
        """Map a stored document path to a real file **inside** this workspace.

        解析会丢图片和表格，所以阅读侧要能看原件；而把工作区文件读给前端是
        本次唯一新增的风险面，所以包含性判断放在这里，只有落在 workspace 里的
        真实文件才会被返回（绝对路径与相对路径都接受）。
        """
        if not path:
            return None
        candidate = path if os.path.isabs(path) else os.path.join(self.workspace, path)
        try:
            resolved = os.path.realpath(candidate)
        except OSError:
            return None
        root = os.path.realpath(self.workspace)
        if resolved != root and not resolved.startswith(root + os.sep):
            return None
        return resolved if os.path.isfile(resolved) else None


    # 附件只允许图片：否则一份 markdown 里的 ![](../../.env) 就能把工作区里的
    # 密钥/数据库读出来（包含性校验只保证"在区内"，不保证"该给你看"）。
    ASSET_MEDIA_TYPES = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }
    DENY_ASSET_SEGMENTS = (".git", ".knowledge", ".bobodan", "node_modules", "__pycache__")

    def raw_asset(self, document_id: str, relative_path: str) -> dict[str, Any]:
        """Resolve an image that sits next to a document, for the reader.

        Markdown is not a trusted path source, so only relative paths are
        accepted and the result must still resolve inside the workspace.
        """
        raw = self._raw_document(document_id)
        if raw is None:
            return _err(f"Document not found: {document_id}", code="document_not_found")
        document_path = self.resolve_source_path(str(raw.get("path") or ""))
        if document_path is None:
            return _err(
                "The original file is not available inside this workspace",
                code="source_not_found",
            )
        if not relative_path or os.path.isabs(relative_path):
            return _err("Only relative asset paths are allowed", code="asset_not_allowed")
        if os.path.splitext(relative_path)[1].lower() not in self.ASSET_MEDIA_TYPES:
            return _err("Only image assets can be served here", code="asset_not_allowed")
        segments = [
            part
            for part in os.path.normcase(relative_path).replace("\\", "/").split("/")
            if part
        ]
        if any(part in self.DENY_ASSET_SEGMENTS for part in segments):
            return _err("Asset is not available", code="asset_not_allowed")
        resolved = self.resolve_source_path(
            os.path.join(os.path.dirname(document_path), relative_path)
        )
        if resolved is None:
            return _err("Asset is not available inside this workspace", code="asset_not_found")
        extension = os.path.splitext(resolved)[1].lower()
        return _ok(
            path=resolved,
            media_type=self.ASSET_MEDIA_TYPES.get(extension, "application/octet-stream"),
            filename=os.path.basename(resolved),
            size=os.path.getsize(resolved),
        )

    def raw_file(self, document_id: str) -> dict[str, Any]:
        """Locate the original file for a document, read-only, or explain why not."""
        raw = self._raw_document(document_id)
        if raw is None:
            return _err(f"Document not found: {document_id}", code="document_not_found")
        resolved = self.resolve_source_path(str(raw.get("path") or ""))
        if resolved is None:
            return _err(
                "The original file is not available inside this workspace",
                code="source_not_found",
            )
        extension = os.path.splitext(resolved)[1].lower()
        return _ok(
            path=resolved,
            media_type=self.RAW_MEDIA_TYPES.get(extension, "application/octet-stream"),
            filename=os.path.basename(resolved),
            size=os.path.getsize(resolved),
        )


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
        # Editable when the file lives inside the library workspace (vault /
        # course folders included) but never inside Bobodan's own system dirs.
        # Managed uploads (raw/inbox, .bobodan/sources) already pass; vault
        # course documents now pass too (user edits them like Obsidian does).
        normalized = os.path.abspath(path) if path else ""
        if (
            not normalized
            or not self.kb._is_within_workspace(normalized, self.workspace)
            or any(part in normalized for part in _SYSTEM_DIR_PARTS)
        ):
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
        atomic_write_json(manifest_path, {"versions": versions})
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
        # P0-13: raw/ is the immutable evidence layer, so a failed write must not
        # truncate the user original - temp file, fsync, replace.
        atomic_write_text(path, content)
