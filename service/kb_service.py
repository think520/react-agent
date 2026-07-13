"""KBService — business logic for knowledge base sync, search, graph, status, reset.

Used by both cli/repl.py and tools/rag_search.py, tools/graph_query.py,
tools/knowledge_status.py, tools/obsidian_tool.py.
Returns structured dicts, no ANSI/HTML formatting.
"""

from __future__ import annotations

import os
import json
import shutil
import hashlib
import re
import unicodedata
from functools import lru_cache
from typing import Any

from knowledge.paths import knowledge_dir, knowledge_path


def _ok(**kwargs: Any) -> dict[str, Any]:
    return {"ok": True, **kwargs}


def _err(error: str) -> dict[str, Any]:
    return {"ok": False, "error": error}


def _legacy_document_id(source: str) -> str:
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
    return f"legacy-{digest}"


def _canonical_wiki_key(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title or "").casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)


def _document_classification(source: str, kind: str = "", title: str = "") -> dict[str, Any]:
    normalized_source = source.replace("\\", "/").casefold()
    is_wiki = normalized_source.startswith("obsidian/wiki/") or "/wiki/" in normalized_source
    metadata_names = {"index.md", "log.md"}
    basename = os.path.basename(normalized_source)
    content_role = "metadata" if is_wiki and basename in metadata_names else "content"
    wiki_type = None
    if is_wiki:
        if "/entities/" in normalized_source or kind == "wiki_entity":
            wiki_type = "entity"
        elif "/concepts/" in normalized_source or kind == "wiki_concept":
            wiki_type = "concept"
    canonical_key = _canonical_wiki_key(title or os.path.splitext(os.path.basename(source))[0])
    canonical_id = f"wiki-{hashlib.sha256(canonical_key.encode('utf-8')).hexdigest()[:16]}" if is_wiki else None
    return {
        "collection": "wiki" if is_wiki else "material",
        "wiki_type": wiki_type,
        "canonical_id": canonical_id,
        "content_role": content_role,
    }


@lru_cache(maxsize=4)
def _load_legacy_chunks(index_path: str, modified_at: float) -> tuple[dict[str, Any], ...]:
    del modified_at
    try:
        with open(index_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return ()
    chunks = payload.get("chunks", []) if isinstance(payload, dict) else payload
    return tuple(item for item in chunks if isinstance(item, dict))


class KBService:
    """Stateless service: each method creates its own stores/managers."""

    def __init__(self, workspace: str = "."):
        self.workspace = os.path.abspath(workspace)

    @property
    def is_portable_library(self) -> bool:
        return os.path.isfile(os.path.join(self.workspace, "BOBODAN_LIBRARY.yaml"))

    @property
    def managed_sources_dir(self) -> str:
        if self.is_portable_library:
            return os.path.join(self.workspace, "raw", "inbox")
        return os.path.join(self.workspace, ".bobodan", "sources")

    @property
    def managed_vault_dir(self) -> str:
        return self.workspace if self.is_portable_library else os.path.join(self.workspace, ".bobodan", "managed-vault")

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
        if self.is_portable_library:
            roots = self._load_source_roots()
            course_dirs = [
                path for path in roots.get("course_dirs", [])
                if os.path.isdir(path) and self._is_within_workspace(path, self.workspace)
            ]
            raw_dir = os.path.join(self.workspace, "raw")
            if os.path.isdir(raw_dir):
                course_dirs.insert(0, raw_dir)
            return self.workspace, list(dict.fromkeys(os.path.abspath(path) for path in course_dirs))
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

    def _wiki_vaults(self) -> list[str]:
        if self.is_portable_library:
            return [self.workspace] if os.path.isdir(os.path.join(self.workspace, "wiki")) else []
        roots = self._load_source_roots()
        candidates = [
            roots.get("vault_path"),
            self.managed_vault_dir,
            os.path.join(self.workspace, "note", "vault"),
        ]
        vaults = []
        seen = set()
        for candidate in candidates:
            if not candidate or not os.path.isdir(candidate):
                continue
            vault = os.path.abspath(candidate)
            if vault in seen or not self._is_within_workspace(vault, self.workspace):
                continue
            if not os.path.isdir(os.path.join(vault, "wiki")):
                continue
            seen.add(vault)
            vaults.append(vault)
        return vaults

    def archive_duplicate_wiki_pages(self) -> dict[str, Any]:
        from wiki.index import archive_duplicate_pages

        roots = self._load_source_roots()
        candidates = [self.workspace] if self.is_portable_library else [roots.get("vault_path"), os.path.join(self.workspace, "note", "vault")]
        seen = set()
        results = []
        for candidate in candidates:
            if not candidate or not os.path.isdir(candidate):
                continue
            vault = os.path.abspath(candidate)
            if vault in seen or not self._is_within_workspace(vault, self.workspace):
                continue
            seen.add(vault)
            result = archive_duplicate_pages(
                vault,
                os.path.join(self.workspace, ".bobodan", "archive", "wiki"),
            )
            if result["canonical"] or result["archived"]:
                results.append(result)
        return _ok(results=results)

    def wiki_health(self) -> dict[str, Any]:
        from wiki.lint import WikiLinter

        details = []
        for vault in self._wiki_vaults():
            result = WikiLinter(vault).lint()
            details.append({
                "vault": os.path.relpath(vault, self.workspace).replace("\\", "/"),
                "total_pages": result.total_pages,
                "orphans": result.orphan_pages,
                "broken_links": [
                    {
                        "source": os.path.basename(item.get("source", "")),
                        "target": item.get("target", ""),
                    }
                    for item in result.broken_links
                ],
                "missing": result.missing_pages,
                "stale": result.stale_pages,
                "index_mismatches": result.index_mismatches,
                "contradiction_candidates": result.contradiction_candidates,
                "errors": result.errors,
                "healthy": result.healthy and not result.errors,
            })

        return _ok(
            healthy=bool(details) and all(item["healthy"] for item in details),
            total_pages=sum(item["total_pages"] for item in details),
            orphan_count=sum(len(item["orphans"]) for item in details),
            broken_link_count=sum(len(item["broken_links"]) for item in details),
            missing_count=sum(len(item["missing"]) for item in details),
            stale_count=sum(len(item["stale"]) for item in details),
            index_mismatch_count=sum(len(item["index_mismatches"]) for item in details),
            contradiction_candidate_count=sum(len(item["contradiction_candidates"]) for item in details),
            vaults=details,
        )

    def maintain_wiki(self, action: str) -> dict[str, Any]:
        if action == "check":
            return self.wiki_health()
        if action not in {"organize", "plan"}:
            return _err("action must be check or plan")

        health = self.wiki_health()
        if not health.get("ok"):
            return health
        return _ok(
            status="planned",
            archived_count=0,
            canonical_count=health.get("total_pages", 0),
            repair_plan={
                "action": "repair",
                "requires_confirmation": True,
                "issues": {
                    "orphans": health.get("orphan_count", 0),
                    "broken_links": health.get("broken_link_count", 0),
                    "missing": health.get("missing_count", 0),
                    "stale": health.get("stale_count", 0),
                },
            },
            health={key: value for key, value in health.items() if key != "ok"},
        )

    def _wiki_target_vault(self) -> str:
        if self.is_portable_library:
            return self.workspace
        roots = self._load_source_roots()
        configured = roots.get("vault_path")
        if configured and os.path.isdir(configured):
            return os.path.abspath(configured)
        workspace_vault = os.path.join(self.workspace, "note", "vault")
        if os.path.isdir(workspace_vault):
            return workspace_vault
        os.makedirs(self.managed_vault_dir, exist_ok=True)
        return self.managed_vault_dir

    def _wiki_scope_documents(
        self,
        document_ids: list[str] | None = None,
        course: str | None = None,
        wiki_document_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        from urllib.parse import unquote

        if not document_ids and not course and not wiki_document_ids:
            return []
        requested_ids = set(document_ids or [])
        for wiki_id in wiki_document_ids or []:
            detail = self.get_document(wiki_id)
            if not detail.get("ok") or detail["document"].get("collection") != "wiki":
                continue
            for section in detail.get("sections", []):
                for match in re.findall(r"document=([^&)\s]+)", section.get("text", "")):
                    requested_ids.add(unquote(match))

        materials = self.list_documents(course=course, collection="material")
        if not materials.get("ok"):
            return []
        available = materials["documents"]
        if requested_ids:
            available = [item for item in available if item["document_id"] in requested_ids]
        elif wiki_document_ids:
            return []
        documents = []
        for summary in available:
            detail = self.get_document(summary["document_id"])
            if detail.get("ok"):
                documents.append({**detail["document"], "sections": detail["sections"]})
        return documents

    def create_wiki_plan(
        self,
        llm_provider,
        document_ids: list[str] | None = None,
        course: str | None = None,
        wiki_document_ids: list[str] | None = None,
        action: str = "generate",
        instruction: str = "",
    ) -> dict[str, Any]:
        documents = self._wiki_scope_documents(document_ids, course, wiki_document_ids)
        if not documents:
            return _err("Select at least one indexed learning material before planning a Wiki")
        try:
            from wiki.workflow import WikiWorkflow

            plan = WikiWorkflow(
                self.workspace,
                self._wiki_target_vault(),
                llm_provider=llm_provider,
            ).create_plan(documents, action=action, instruction=instruction)
        except Exception as exc:
            return _err(str(exc))
        return _ok(**plan)

    def get_wiki_plan(self, plan_id: str) -> dict[str, Any]:
        try:
            from wiki.workflow import WikiWorkflow

            plan = WikiWorkflow(self.workspace, self._wiki_target_vault()).get_plan(plan_id)
        except (OSError, ValueError) as exc:
            return _err(str(exc))
        return _ok(**plan)

    def create_wiki_migration_plan(self) -> dict[str, Any]:
        try:
            from wiki.workflow import WikiWorkflow

            plan = WikiWorkflow(self.workspace, self._wiki_target_vault()).create_migration_plan()
        except (OSError, ValueError) as exc:
            return _err(str(exc))
        return _ok(**plan)

    def apply_wiki_plan(self, plan_id: str, config: dict | None = None) -> dict[str, Any]:
        try:
            from wiki.workflow import WikiWorkflow

            plan = WikiWorkflow(self.workspace, self._wiki_target_vault()).apply_plan(plan_id)
        except (OSError, ValueError) as exc:
            return _err(str(exc))
        try:
            sync = self._sync_registered_sources(mode="incremental", config=config or {}).to_dict()
        except Exception as exc:
            sync = {"errors": [{"error": str(exc)}], "deferred": True}
        return _ok(**plan, sync=sync)

    def undo_wiki_checkpoint(self, checkpoint_id: str, config: dict | None = None) -> dict[str, Any]:
        try:
            from wiki.workflow import WikiWorkflow

            restored = WikiWorkflow(
                self.workspace,
                self._wiki_target_vault(),
            ).restore_checkpoint(checkpoint_id)
        except (OSError, ValueError) as exc:
            return _err(str(exc))
        try:
            sync = self._sync_registered_sources(mode="incremental", config=config or {}).to_dict()
        except Exception as exc:
            sync = {"errors": [{"error": str(exc)}], "deferred": True}
        return _ok(**restored, sync=sync)

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
        roots["vault_path"] = None if self.is_portable_library else os.path.abspath(vault_path)
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
            stem, extension = os.path.splitext(safe_name)
            counter = 2
            while os.path.exists(target):
                target = os.path.join(self.managed_sources_dir, f"{stem} ({counter}){extension}")
                counter += 1
            with open(target, "wb") as handle:
                handle.write(content)
            imported.append(os.path.basename(target))

        if not imported:
            return _err("No supported files were provided")

        summary = self._sync_registered_sources(mode="incremental", config=config or {})
        return _ok(imported=imported, rejected=rejected, sync=summary.to_dict())

    # --- Status ---

    def status(self) -> dict[str, Any]:
        storage_dir = knowledge_dir(self.workspace)
        if not os.path.exists(storage_dir):
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

    def list_documents(
        self,
        course: str | None = None,
        collection: str = "all",
    ) -> dict[str, Any]:
        if collection not in {"all", "material", "wiki"}:
            return _err("collection must be all, material, or wiki")
        db_path = knowledge_path(self.workspace, "knowledge.db")
        documents = []
        if os.path.exists(db_path):
            from rag.sqlite_store import KBSQLiteStore
            store = KBSQLiteStore(self.workspace)
            store.init_db()
            try:
                documents = store.list_documents(course=course)
            finally:
                store.close()

        public = [self._public_document(item) for item in documents]
        known_sources = {item.get("source") for item in documents}
        public.extend(self._legacy_documents(course=course, exclude_sources=known_sources))
        public = self._visible_documents(public)
        if collection != "all":
            public = [item for item in public if item["collection"] == collection]
        public.sort(key=lambda item: (item.get("title") or item.get("source") or "").casefold())
        return _ok(documents=public)

    def get_document(self, document_id: str) -> dict[str, Any]:
        db_path = knowledge_path(self.workspace, "knowledge.db")
        if os.path.exists(db_path):
            from rag.sqlite_store import KBSQLiteStore
            store = KBSQLiteStore(self.workspace)
            store.init_db()
            try:
                document = store.get_document(document_id)
                if document is not None:
                    chunks = store.get_chunks_by_document(document_id)
                    return _ok(
                        document=self._public_document(document),
                        sections=[self._public_section(chunk) for chunk in chunks],
                    )
            finally:
                store.close()

        legacy = self._legacy_document(document_id)
        if legacy:
            return _ok(**legacy)
        return _err(f"Document not found: {document_id}")

    def delete_document(self, document_id: str, config: dict | None = None) -> dict[str, Any]:
        if document_id.startswith("legacy-"):
            return _err("This knowledge source is read-only and cannot be deleted here")
        db_path = knowledge_path(self.workspace, "knowledge.db")
        if not os.path.exists(db_path):
            return _err(f"Document not found: {document_id}")

        from rag.sqlite_store import KBSQLiteStore
        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            document = store.get_document(document_id)
        finally:
            store.close()
        if document is None:
            return _err(f"Document not found: {document_id}")

        path = document.get("path")
        if not path or not self._is_within_workspace(path, self.managed_sources_dir):
            return _err("This knowledge source is read-only and cannot be deleted here")
        if os.path.isfile(path):
            if self.is_portable_library:
                from datetime import datetime, timezone
                import shutil

                archive_dir = os.path.join(
                    self.workspace,
                    ".bobodan",
                    "archive",
                    "raw",
                    datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                )
                os.makedirs(archive_dir, exist_ok=True)
                target = os.path.join(archive_dir, os.path.basename(path))
                shutil.move(path, target)
                self._mark_wiki_sources_stale(document.get("source") or path)
            else:
                os.remove(path)

        summary = self._sync_registered_sources(mode="incremental", config=config or {})
        return _ok(document_id=document_id, sync=summary.to_dict())

    def _mark_wiki_sources_stale(self, source: str) -> None:
        """Mark generated pages for review when an original source is archived."""
        import yaml

        wiki_dir = os.path.join(self.workspace, "wiki")
        if not os.path.isdir(wiki_dir):
            return
        normalized = str(source).replace("\\", "/")
        for root, _dirs, files in os.walk(wiki_dir):
            if os.path.basename(root) == "templates":
                continue
            for filename in files:
                if not filename.endswith(".md"):
                    continue
                path = os.path.join(root, filename)
                try:
                    content = open(path, "r", encoding="utf-8").read()
                except OSError:
                    continue
                if not content.startswith("---"):
                    continue
                end = content.find("---", 3)
                if end < 0:
                    continue
                try:
                    metadata = yaml.safe_load(content[3:end]) or {}
                except yaml.YAMLError:
                    continue
                sources = [str(item).replace("\\", "/") for item in metadata.get("sources") or []]
                if normalized not in sources and not any(normalized.endswith(item) or item.endswith(normalized) for item in sources):
                    continue
                metadata["status"] = "needs_update"
                rendered = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(f"---\n{rendered}\n---{content[end + 3:]}")

    @staticmethod
    def _public_section(chunk: dict[str, Any]) -> dict[str, Any]:
        return {
            "chunk_id": chunk.get("id"),
            "heading": chunk.get("heading_text", ""),
            "page_start": chunk.get("page_start"),
            "slide_start": chunk.get("slide_start"),
            "text": chunk.get("text", ""),
        }

    def _public_document(self, document: dict[str, Any]) -> dict[str, Any]:
        path = document.get("path")
        managed = bool(path and self._is_within_workspace(path, self.managed_sources_dir))
        public = {
            "document_id": document.get("id"),
            "source": document.get("source", ""),
            "kind": document.get("kind", ""),
            "title": document.get("title", ""),
            "course": document.get("course"),
            "summary": document.get("summary", ""),
            "vector_status": document.get("vector_status", ""),
            "vector_error": document.get("vector_error"),
            "updated_at": document.get("updated_at", ""),
            "managed": managed,
            "origin": "managed" if managed else "workspace",
        }
        public.update(_document_classification(
            public["source"], public["kind"], public["title"]
        ))
        return public

    @staticmethod
    def _visible_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        visible = [item for item in documents if item.get("content_role") != "metadata"]
        wiki_groups: dict[str, list[dict[str, Any]]] = {}
        output = []
        for item in visible:
            if item.get("collection") != "wiki":
                output.append(item)
                continue
            wiki_groups.setdefault(item.get("canonical_id") or item["document_id"], []).append(item)

        for items in wiki_groups.values():
            items.sort(key=lambda item: (
                item.get("wiki_type") != "concept",
                " " not in (item.get("title") or ""),
                item.get("source") or "",
            ))
            output.append(items[0])
        return output

    def _legacy_chunks(self) -> tuple[dict[str, Any], ...]:
        path = knowledge_path(self.workspace, "rag_index.json")
        if not os.path.exists(path):
            return ()
        return _load_legacy_chunks(path, os.path.getmtime(path))

    def _legacy_documents(
        self,
        course: str | None = None,
        exclude_sources: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        excluded = exclude_sources or set()
        index_path = knowledge_path(self.workspace, "rag_index.json")
        updated_at = ""
        if os.path.exists(index_path):
            from datetime import datetime, timezone
            updated_at = datetime.fromtimestamp(
                os.path.getmtime(index_path), tz=timezone.utc
            ).isoformat()

        for chunk in self._legacy_chunks():
            source = str(chunk.get("source") or "")
            if not source or source in excluded:
                continue
            metadata = chunk.get("metadata") or {}
            chunk_course = metadata.get("course") or chunk.get("course")
            if course and chunk_course != course:
                continue
            classification = _document_classification(
                source,
                metadata.get("kind") or "legacy_document",
                metadata.get("title") or os.path.splitext(os.path.basename(source))[0],
            )
            item = grouped.setdefault(source, {
                "document_id": _legacy_document_id(source),
                "source": source,
                "kind": metadata.get("kind") or "legacy_document",
                "title": metadata.get("title") or os.path.splitext(os.path.basename(source))[0],
                "course": chunk_course,
                "summary": str(chunk.get("text") or "")[:220].strip(),
                "vector_status": "indexed",
                "vector_error": None,
                "updated_at": updated_at,
                "managed": False,
                "origin": "legacy_index",
                "chunk_count": 0,
                **classification,
            })
            item["chunk_count"] += 1
        return list(grouped.values())

    def _legacy_document(self, document_id: str) -> dict[str, Any] | None:
        documents = {
            item["document_id"]: item
            for item in self._legacy_documents()
        }
        document = documents.get(document_id)
        if not document:
            return None
        sections = []
        for chunk in self._legacy_chunks():
            if chunk.get("source") != document["source"]:
                continue
            metadata = chunk.get("metadata") or {}
            sections.append({
                "chunk_id": chunk.get("id"),
                "heading": metadata.get("heading_text") or metadata.get("heading") or "",
                "page_start": metadata.get("page_start") or metadata.get("page"),
                "slide_start": metadata.get("slide_start") or metadata.get("slide"),
                "text": chunk.get("text", ""),
            })
        return {"document": document, "sections": sections}

    # --- RAG Search ---

    def search(
        self,
        query: str,
        course: str | None = None,
        top_k: int = 5,
        mode: str = "auto",
        document_ids: list[str] | None = None,
        config: dict | None = None,
    ) -> dict[str, Any]:
        if not query or not query.strip():
            return _err("query is required")

        storage_dir = knowledge_dir(self.workspace)
        db_path = os.path.join(storage_dir, "knowledge.db")
        sparse_path = os.path.join(storage_dir, "rag_index.json")
        dense_path = os.path.join(storage_dir, "rag_index_dense.json")
        if (not os.path.exists(db_path)
                and not os.path.exists(sparse_path)
                and not os.path.exists(dense_path)):
            return _err("RAG index not found. Run obsidian_sync first.")

        from rag.retriever import search_index

        requested_top_k = max(1, min(top_k, 20))
        candidate_top_k = 20 if document_ids else requested_top_k
        results = search_index(
            self.workspace,
            query=query.strip(),
            course=course,
            top_k=candidate_top_k,
            config=config or {},
            mode=mode,
        )
        legacy_results = []
        if self._legacy_chunks():
            from rag.vector_store import LocalVectorStore
            index_path = knowledge_path(self.workspace, "rag_index.json")
            legacy_results = LocalVectorStore(index_path).search(
                query=query.strip(), course=course, top_k=candidate_top_k
            )
            for item in legacy_results:
                source = str(item.get("source") or "")
                metadata = item.get("metadata") or {}
                item["document_id"] = _legacy_document_id(source)
                item["chunk_id"] = item.get("chunk_id") or item.get("id")
                item["title"] = item.get("title") or metadata.get("title") or os.path.basename(source)

        source_documents = {
            item["source"]: item
            for item in self.list_documents(collection="all").get("documents", [])
        }
        allowed_document_ids = set(document_ids or [])
        merged = []
        seen = set()
        for index in range(max(len(results), len(legacy_results))):
            for collection in (results, legacy_results):
                if index >= len(collection):
                    continue
                item = collection[index]
                visible_document = source_documents.get(str(item.get("source") or ""))
                if not visible_document:
                    continue
                if allowed_document_ids and visible_document["document_id"] not in allowed_document_ids:
                    continue
                item["document_id"] = visible_document["document_id"]
                item["title"] = visible_document["title"]
                item["collection"] = visible_document["collection"]
                item["wiki_type"] = visible_document["wiki_type"]
                key = item.get("chunk_id") or (item.get("source"), item.get("text"))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
        if not allowed_document_ids:
            wiki_results = [item for item in merged if item.get("collection") == "wiki"]
            material_results = [item for item in merged if item.get("collection") == "material"]
            if wiki_results and material_results:
                merged = wiki_results[:2] + material_results + wiki_results[2:]
        return _ok(results=merged[:requested_top_k])

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
        storage_dir = knowledge_dir(self.workspace)
        if os.path.exists(storage_dir):
            if self.is_portable_library:
                for filename in (
                    "knowledge.db", "knowledge.db-shm", "knowledge.db-wal", "bobodan.db",
                    "bobodan.db-shm", "bobodan.db-wal", "rag_index.json", "rag_index_dense.json",
                    "graph_store.json", "sync_state.json", "import_report.json",
                ):
                    path = os.path.join(storage_dir, filename)
                    if os.path.isfile(path):
                        os.remove(path)
                qdrant = os.path.join(storage_dir, "qdrant")
                if os.path.isdir(qdrant):
                    shutil.rmtree(qdrant)
            else:
                shutil.rmtree(storage_dir)
        return _ok(message="Knowledge base reset")
