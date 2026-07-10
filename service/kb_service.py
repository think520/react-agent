"""KBService — business logic for knowledge base sync, search, graph, status, reset.

Used by both cli/repl.py and tools/rag_search.py, tools/graph_query.py,
tools/knowledge_status.py, tools/obsidian_tool.py.
Returns structured dicts, no ANSI/HTML formatting.
"""

from __future__ import annotations

import os
import json
import shutil
from typing import Any


def _ok(**kwargs: Any) -> dict[str, Any]:
    return {"ok": True, **kwargs}


def _err(error: str) -> dict[str, Any]:
    return {"ok": False, "error": error}


class KBService:
    """Stateless service: each method creates its own stores/managers."""

    def __init__(self, workspace: str = "."):
        self.workspace = os.path.abspath(workspace)

    @property
    def managed_sources_dir(self) -> str:
        return os.path.join(self.workspace, ".bobodan", "sources")

    @property
    def managed_vault_dir(self) -> str:
        return os.path.join(self.workspace, ".bobodan", "managed-vault")

    @property
    def source_roots_path(self) -> str:
        return os.path.join(self.workspace, ".bobodan", "source_roots.json")

    def _load_source_roots(self) -> dict[str, Any]:
        if not os.path.exists(self.source_roots_path):
            return {"vault_path": None, "course_dirs": []}
        try:
            with open(self.source_roots_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {"vault_path": None, "course_dirs": []}
        return {
            "vault_path": data.get("vault_path"),
            "course_dirs": data.get("course_dirs") or [],
        }

    def _save_source_roots(self, roots: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.source_roots_path), exist_ok=True)
        with open(self.source_roots_path, "w", encoding="utf-8") as handle:
            json.dump(roots, handle, ensure_ascii=False, indent=2)

    def _registered_roots(self) -> tuple[str, list[str]]:
        roots = self._load_source_roots()
        vault_path = roots.get("vault_path")
        if not vault_path or not os.path.isdir(vault_path):
            os.makedirs(self.managed_vault_dir, exist_ok=True)
            vault_path = self.managed_vault_dir

        course_dirs = [
            path for path in roots.get("course_dirs", [])
            if os.path.isdir(path)
        ]
        if os.path.isdir(self.managed_sources_dir):
            course_dirs.append(self.managed_sources_dir)
        course_dirs = list(dict.fromkeys(os.path.abspath(path) for path in course_dirs))
        return vault_path, course_dirs

    @staticmethod
    def _is_within_workspace(path: str, workspace: str) -> bool:
        try:
            return os.path.commonpath([os.path.abspath(path), os.path.abspath(workspace)]) == os.path.abspath(workspace)
        except ValueError:
            return False

    # --- Sync ---

    def sync(
        self,
        vault_path: str,
        course_dir: str | None = None,
        mode: str = "incremental",
        config: dict | None = None,
    ) -> dict[str, Any]:
        if mode not in {"incremental", "full"}:
            return _err("mode must be either 'incremental' or 'full'")
        if not self._is_within_workspace(vault_path, self.workspace):
            return _err(f"Access denied: {vault_path} is outside workspace")
        if not os.path.isdir(vault_path):
            return _err(f"Vault directory not found: {vault_path}")
        if course_dir:
            if not self._is_within_workspace(course_dir, self.workspace):
                return _err(f"Access denied: {course_dir} is outside workspace")
            if not os.path.isdir(course_dir):
                return _err(f"Course directory not found: {course_dir}")

        roots = self._load_source_roots()
        roots["vault_path"] = os.path.abspath(vault_path)
        if course_dir:
            course_dirs = [os.path.abspath(path) for path in roots.get("course_dirs", [])]
            abs_course_dir = os.path.abspath(course_dir)
            if abs_course_dir not in course_dirs:
                course_dirs.append(abs_course_dir)
            roots["course_dirs"] = course_dirs
        self._save_source_roots(roots)

        summary = self._sync_registered_sources(mode=mode, config=config or {})
        data = summary.to_dict()
        return _ok(**data)

    def _sync_registered_sources(self, mode: str, config: dict):
        from obsidian.sync import sync_sources

        vault_path, course_dirs = self._registered_roots()
        primary_course = course_dirs[0] if course_dirs else None
        extra_courses = course_dirs[1:] if len(course_dirs) > 1 else []
        return sync_sources(
            workspace=self.workspace,
            vault_path=vault_path,
            course_dir=primary_course,
            extra_course_dirs=extra_courses,
            mode=mode,
            config=config,
        )

    def import_files(
        self,
        files: list[tuple[str, bytes]],
        config: dict | None = None,
    ) -> dict[str, Any]:
        allowed = {".md", ".pdf", ".docx", ".pptx"}
        os.makedirs(self.managed_sources_dir, exist_ok=True)
        imported = []
        rejected = []

        for filename, content in files:
            safe_name = os.path.basename(filename).strip()
            extension = os.path.splitext(safe_name)[1].lower()
            if not safe_name or extension not in allowed:
                rejected.append({"filename": filename, "reason": "unsupported_file_type"})
                continue
            target = os.path.join(self.managed_sources_dir, safe_name)
            with open(target, "wb") as handle:
                handle.write(content)
            imported.append(safe_name)

        if not imported:
            return _err("No supported files were provided")

        summary = self._sync_registered_sources(mode="incremental", config=config or {})
        return _ok(imported=imported, rejected=rejected, sync=summary.to_dict())

    # --- Status ---

    def status(self) -> dict[str, Any]:
        knowledge_dir = os.path.join(self.workspace, ".knowledge")
        if not os.path.exists(knowledge_dir):
            return _err("No knowledge base found. Run obsidian_sync first.")

        from knowledge.library import build_library_summary
        from knowledge.import_report import load_import_report

        summary = build_library_summary(self.workspace)
        report = load_import_report(self.workspace)

        result: dict[str, Any] = {
            "total_files": summary.total_files,
            "total_chunks": summary.total_chunks,
            "total_errors": summary.total_errors,
            "graph_nodes": summary.graph_nodes,
            "graph_relationships": summary.graph_relationships,
            "graph_nodes_by_type": summary.graph_nodes_by_type,
            "graph_relationships_by_type": summary.graph_relationships_by_type,
            "graph_backend": summary.graph_backend,
            "last_sync": summary.last_sync,
            "courses": [
                {
                    "name": cs.name,
                    "file_count": cs.file_count,
                    "chunk_count": cs.chunk_count,
                    "error_count": cs.error_count,
                }
                for cs in summary.courses
            ],
        }

        if report:
            result["last_import"] = {
                "timestamp": report.timestamp,
                "mode": report.mode,
                "error_files": report.error_files,
                "errors": report.errors[:10],
            }

        return _ok(**result)

    def list_documents(self, course: str | None = None) -> dict[str, Any]:
        db_path = os.path.join(self.workspace, ".knowledge", "knowledge.db")
        if not os.path.exists(db_path):
            return _ok(documents=[])
        from rag.sqlite_store import KBSQLiteStore
        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            documents = store.list_documents(course=course)
        finally:
            store.close()
        return _ok(documents=[self._public_document(item) for item in documents])

    def get_document(self, document_id: str) -> dict[str, Any]:
        db_path = os.path.join(self.workspace, ".knowledge", "knowledge.db")
        if not os.path.exists(db_path):
            return _err(f"Document not found: {document_id}")
        from rag.sqlite_store import KBSQLiteStore
        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            document = store.get_document(document_id)
            if document is None:
                return _err(f"Document not found: {document_id}")
            chunks = store.get_chunks_by_document(document_id)
        finally:
            store.close()
        return _ok(
            document=self._public_document(document),
            sections=[
                {
                    "chunk_id": chunk.get("id"),
                    "heading": chunk.get("heading_text", ""),
                    "page_start": chunk.get("page_start"),
                    "slide_start": chunk.get("slide_start"),
                    "text": chunk.get("text", ""),
                }
                for chunk in chunks
            ],
        )

    @staticmethod
    def _public_document(document: dict[str, Any]) -> dict[str, Any]:
        return {
            "document_id": document.get("id"),
            "source": document.get("source", ""),
            "kind": document.get("kind", ""),
            "title": document.get("title", ""),
            "course": document.get("course"),
            "summary": document.get("summary", ""),
            "vector_status": document.get("vector_status", ""),
            "vector_error": document.get("vector_error"),
            "updated_at": document.get("updated_at", ""),
        }

    # --- RAG Search ---

    def search(
        self,
        query: str,
        course: str | None = None,
        top_k: int = 5,
        mode: str = "auto",
        config: dict | None = None,
    ) -> dict[str, Any]:
        if not query or not query.strip():
            return _err("query is required")

        knowledge_dir = os.path.join(self.workspace, ".knowledge")
        db_path = os.path.join(knowledge_dir, "knowledge.db")
        sparse_path = os.path.join(knowledge_dir, "rag_index.json")
        dense_path = os.path.join(knowledge_dir, "rag_index_dense.json")
        if (not os.path.exists(db_path)
                and not os.path.exists(sparse_path)
                and not os.path.exists(dense_path)):
            return _err("RAG index not found. Run obsidian_sync first.")

        from rag.retriever import search_index

        results = search_index(
            self.workspace,
            query=query.strip(),
            course=course,
            top_k=max(1, min(top_k, 20)),
            config=config or {},
            mode=mode,
        )
        return _ok(results=results)

    # --- Graph Query ---

    def graph_query(
        self,
        concept: str,
        intent: str = "related",
        limit: int = 20,
    ) -> dict[str, Any]:
        if not concept or not concept.strip():
            return _err("concept is required")

        from graph.store import get_graph_store

        store = get_graph_store(self.workspace)
        try:
            data = store.query(
                concept=concept.strip(),
                intent=intent,
                limit=max(1, min(int(limit), 50)),
            )
        finally:
            if hasattr(store, "close"):
                store.close()

        return _ok(**data)

    # --- Reset ---

    def reset(self) -> dict[str, Any]:
        knowledge_dir = os.path.join(self.workspace, ".knowledge")
        if os.path.exists(knowledge_dir):
            shutil.rmtree(knowledge_dir)
        return _ok(message="Knowledge base reset")
