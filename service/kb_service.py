"""KBService — business logic for knowledge base sync, search, graph, status, reset.

Used by both cli/repl.py and tools/rag_search.py, tools/graph_query.py,
tools/knowledge_status.py, tools/obsidian_tool.py.
Returns structured dicts, no ANSI/HTML formatting.
"""

from __future__ import annotations

import os
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

        from obsidian.sync import sync_sources

        summary = sync_sources(
            workspace=self.workspace,
            vault_path=vault_path,
            course_dir=course_dir,
            mode=mode,
            config=config or {},
        )
        data = summary.to_dict()
        return _ok(**data)

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
