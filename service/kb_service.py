"""KBService — business logic for knowledge base sync, search, graph, status, reset.

Used by CLI, local RAG tools, and the Web backend.
Returns structured dicts, no ANSI/HTML formatting.
"""

from __future__ import annotations

import os
import json
import logging
import shutil
import hashlib
import re
import unicodedata
from typing import Any

from knowledge.paths import knowledge_dir, knowledge_path
from service._result import err as _err, ok as _ok

logger = logging.getLogger(__name__)


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
        if "/sources/" in normalized_source or kind == "wiki_source":
            wiki_type = "source"
        elif "/entities/" in normalized_source or kind == "wiki_entity":
            wiki_type = "entity"
        elif "/concepts/" in normalized_source or kind == "wiki_concept":
            wiki_type = "concept"
        elif "/analyses/" in normalized_source or kind == "wiki_analysis":
            wiki_type = "analysis"
        elif "/questions/" in normalized_source or kind == "wiki_question":
            wiki_type = "question"
        elif "/notes/" in normalized_source or kind == "wiki_note":
            wiki_type = "note"
    canonical_title = _canonical_wiki_key(title or os.path.splitext(os.path.basename(source))[0])
    canonical_family = "source" if wiki_type == "source" else "knowledge"
    canonical_key = f"{canonical_family}:{canonical_title}"
    canonical_id = f"wiki-{hashlib.sha256(canonical_key.encode('utf-8')).hexdigest()[:16]}" if is_wiki else None
    return {
        "collection": "wiki" if is_wiki else "material",
        "wiki_type": wiki_type,
        "canonical_id": canonical_id,
        "content_role": content_role,
    }


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
            course_dirs = []
            for stored_path in roots.get("course_dirs", []):
                path = str(stored_path)
                candidate = path if os.path.isabs(path) else os.path.join(self.workspace, path)
                candidate = os.path.abspath(candidate)
                if not os.path.isdir(candidate) and os.path.isabs(path):
                    candidate = os.path.join(self.workspace, os.path.basename(os.path.normpath(path)))
                if os.path.isdir(candidate) and self._is_within_workspace(candidate, self.workspace):
                    course_dirs.append(candidate)
            # 2026-08-12 design: the library root itself is the user-facing
            # "throw files in here" folder. Registering it (instead of raw/)
            # lets root-level PDF/DOCX be indexed; raw/ is covered as its
            # subdirectory, internal structure is excluded by the scanner.
            if not any(os.path.abspath(d) == os.path.abspath(self.workspace) for d in course_dirs):
                course_dirs.insert(0, self.workspace)
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
                "duplicate_candidates": result.duplicate_candidates,
                "contradiction_candidates": result.contradiction_candidates,
                "semantic_candidates": result.semantic_candidates,
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
            duplicate_candidate_count=sum(len(item["duplicate_candidates"]) for item in details),
            contradiction_candidate_count=sum(len(item["contradiction_candidates"]) for item in details),
            semantic_candidate_count=sum(len(item["semantic_candidates"]) for item in details),
            vaults=details,
        )

    def review_wiki_semantics(self, llm_provider) -> dict[str, Any]:
        from wiki.lint import WikiLinter

        reviews = []
        try:
            for vault in self._wiki_vaults():
                result = WikiLinter(vault).semantic_review(llm_provider)
                reviews.append({
                    "vault": os.path.relpath(vault, self.workspace).replace("\\", "/"),
                    **result,
                })
        except (OSError, ValueError) as exc:
            return _err(str(exc))
        health = self.wiki_health()
        return _ok(reviews=reviews, health={key: value for key, value in health.items() if key != "ok"})

    def maintain_wiki(self, action: str) -> dict[str, Any]:
        if action == "check":
            return self.wiki_health()
        if action not in {"organize", "plan"}:
            return _err("action must be check or plan")

        health = self.wiki_health()
        if not health.get("ok"):
            return health
        from wiki.repair import WikiRepairStore

        store = WikiRepairStore(self.workspace, self._wiki_target_vault())
        plan = store.create(health)
        wiki_documents = self.list_documents(collection="wiki").get("documents") or []
        by_title: dict[str, list[str]] = {}
        for document in wiki_documents:
            title = str(document.get("title") or "").strip()
            if title:
                by_title.setdefault(title, []).append(str(document["document_id"]))
        changed = False
        for item in plan.get("items") or []:
            matches = by_title.get(str(item.get("title") or ""), [])
            if len(matches) == 1:
                item["page_id"] = matches[0]
                changed = True
        if changed:
            plan = store.save(plan)
        return _ok(
            status="planned",
            archived_count=0,
            canonical_count=health.get("total_pages", 0),
            repair_plan=plan,
            plan_id=plan["plan_id"],
            health={key: value for key, value in health.items() if key != "ok"},
        )

    def get_wiki_repair_plan(self, plan_id: str) -> dict[str, Any]:
        try:
            from wiki.repair import WikiRepairStore

            plan = WikiRepairStore(self.workspace, self._wiki_target_vault()).get(plan_id)
        except (OSError, ValueError) as exc:
            return _err(str(exc))
        return _ok(**plan)

    def apply_wiki_repair_plan(self, plan_id: str, config: dict | None = None) -> dict[str, Any]:
        try:
            from wiki.repair import WikiRepairStore

            plan = WikiRepairStore(self.workspace, self._wiki_target_vault()).apply(plan_id)
            summary = self._sync_registered_sources(mode="incremental", config=config or {})
        except (OSError, ValueError) as exc:
            return _err(str(exc))
        return _ok(**plan, sync=summary.to_dict())

    def draft_wiki_repair_plan(self, plan_id: str, llm_provider) -> dict[str, Any]:
        try:
            from wiki.repair import WikiRepairStore

            store = WikiRepairStore(self.workspace, self._wiki_target_vault())
            plan = store.get(plan_id)
            review = self.review_wiki_semantics(llm_provider)
            if not review.get("ok"):
                return review
            for item in plan.get("items") or []:
                if item.get("execution") == "ai" and item.get("status") == "pending":
                    item["status"] = "ready"
            plan["ai_review"] = review.get("reviews") or []
            plan = store.save(plan)
        except (OSError, ValueError) as exc:
            return _err(str(exc))
        return _ok(**plan)

    def _wiki_page_record(self, document_id: str) -> dict[str, Any] | None:
        db_path = knowledge_path(self.workspace, "knowledge.db")
        if not os.path.exists(db_path):
            return None
        from rag.sqlite_store import KBSQLiteStore

        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            document = store.get_document(document_id)
        finally:
            store.close()
        if not document:
            return None
        public = self._public_document(document)
        path = str(document.get("path") or "")
        wiki_root = os.path.abspath(os.path.join(self._wiki_target_vault(), "wiki"))
        if public.get("collection") != "wiki" or not path or not os.path.isfile(path):
            return None
        if os.path.commonpath([os.path.abspath(path), wiki_root]) != wiki_root:
            return None
        return {**document, **public, "path": path}

    def get_wiki_page(self, document_id: str) -> dict[str, Any]:
        record = self._wiki_page_record(document_id)
        if not record:
            return _err(f"Wiki page not found: {document_id}")
        from wiki.reliability import read_page

        metadata, body = read_page(record["path"])
        body = re.sub(r"^#\s+[^\n]+\n+", "", body.strip(), count=1)
        return _ok(page={
            "document_id": document_id,
            "title": str(metadata.get("title") or record.get("title") or ""),
            "body": body,
            "tags": list(metadata.get("tags") or []),
            "related": list(metadata.get("related") or []),
            "page_type": str(metadata.get("type") or record.get("kind") or "wiki_note"),
            "generated_by": str(metadata.get("generated_by") or "user"),
            "managed_by": str(metadata.get("managed_by") or ("ai" if metadata.get("generated_by") == "bobodan" else "user")),
            "content_revision": int(metadata.get("content_revision") or 1),
            "source_refs": list(metadata.get("source_refs") or []),
        })

    def create_wiki_page(
        self,
        *,
        title: str,
        body: str,
        tags: list[str] | None = None,
        related: list[str] | None = None,
        config: dict | None = None,
    ) -> dict[str, Any]:
        from wiki.utils import safe_filename
        from wiki.index import WikiIndexer
        from wiki.reliability import atomic_text
        from wiki.schema import WikiConfig, WikiPage

        title = title.strip()
        body = body.strip()
        if not title or not body:
            return _err("Wiki page title and body are required")
        vault = self._wiki_target_vault()
        wiki_config = WikiConfig()
        directory = wiki_config.notes_path(vault)
        os.makedirs(directory, exist_ok=True)
        target = os.path.join(directory, f"{safe_filename(title)}.md")
        if os.path.exists(target):
            return _err("A Wiki page with this title already exists")
        page = WikiPage(
            title=title,
            page_type="wiki_note",
            content=body,
            tags=list(dict.fromkeys(tags or [])),
            links=list(dict.fromkeys(related or [])),
            generated_by="user",
            managed_by="user",
            content_revision=1,
        )
        atomic_text(target, page.to_markdown())
        WikiIndexer(vault, wiki_config).rebuild_from_disk()
        summary = self._sync_registered_sources(mode="incremental", config=config or {})
        documents = self.list_documents(collection="wiki").get("documents", [])
        created = next((item for item in documents if item.get("title") == title and item.get("wiki_type") == "note"), None)
        return _ok(page=created or {"title": title, "wiki_type": "note"}, sync=summary.to_dict())

    def update_wiki_page(
        self,
        document_id: str,
        *,
        expected_revision: int,
        title: str,
        body: str,
        tags: list[str] | None = None,
        related: list[str] | None = None,
        config: dict | None = None,
    ) -> dict[str, Any]:
        record = self._wiki_page_record(document_id)
        if not record:
            return _err(f"Wiki page not found: {document_id}")
        from wiki.index import WikiIndexer
        from wiki.reliability import atomic_text, read_page
        from wiki.schema import WikiConfig, WikiPage

        metadata, _old_body = read_page(record["path"])
        current_revision = int(metadata.get("content_revision") or 1)
        if expected_revision != current_revision:
            return _err("Wiki page changed in another view; reload before saving")
        title = title.strip()
        body = body.strip()
        if not title or not body:
            return _err("Wiki page title and body are required")
        generated_by = str(metadata.get("generated_by") or "user")
        page = WikiPage(
            title=title,
            page_type=str(metadata.get("type") or record.get("kind") or "wiki_note"),
            content=body,
            tags=list(dict.fromkeys(tags or [])),
            sources=list(metadata.get("sources") or []),
            links=list(dict.fromkeys(related or [])),
            source_refs=list(metadata.get("source_refs") or []),
            source_hash=str(metadata.get("source_hash") or ""),
            indexable=bool(metadata.get("indexable", True)),
            created=str(metadata.get("created") or ""),
            summary=str(metadata.get("summary") or ""),
            status=str(metadata.get("status") or "active"),
            generated_by=generated_by,
            managed_by="mixed" if generated_by == "bobodan" else "user",
            content_revision=current_revision + 1,
        )
        atomic_text(record["path"], page.to_markdown())
        WikiIndexer(self._wiki_target_vault(), WikiConfig()).rebuild_from_disk()
        summary = self._sync_registered_sources(mode="incremental", config=config or {})
        return _ok(page={
            "document_id": document_id,
            "title": title,
            "body": body,
            "tags": page.tags,
            "related": page.links,
            "page_type": page.page_type,
            "generated_by": generated_by,
            "managed_by": page.managed_by,
            "content_revision": page.content_revision,
            "source_refs": page.source_refs,
        }, sync=summary.to_dict())

    @property
    def _wiki_page_archives_path(self) -> str:
        return os.path.join(self.workspace, ".bobodan", "wiki", "page-archives.json")

    def archive_wiki_page(self, document_id: str, config: dict | None = None) -> dict[str, Any]:
        record = self._wiki_page_record(document_id)
        if not record:
            return _err(f"Wiki page not found: {document_id}")
        from datetime import datetime, timezone
        import uuid
        from wiki.index import WikiIndexer
        from wiki.reliability import atomic_json
        from wiki.schema import WikiConfig

        archive_root = os.path.join(self.workspace, ".bobodan", "archive", "wiki-pages")
        os.makedirs(archive_root, exist_ok=True)
        target = os.path.join(archive_root, f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}-{os.path.basename(record['path'])}")
        shutil.move(record["path"], target)
        try:
            with open(self._wiki_page_archives_path, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except (OSError, json.JSONDecodeError):
            manifest = {}
        manifest[document_id] = {"original": record["path"], "archived": target}
        atomic_json(self._wiki_page_archives_path, manifest)
        WikiIndexer(self._wiki_target_vault(), WikiConfig()).rebuild_from_disk()
        summary = self._sync_registered_sources(mode="incremental", config=config or {})
        return _ok(document_id=document_id, archived=True, sync=summary.to_dict())

    def restore_wiki_page(self, document_id: str, config: dict | None = None) -> dict[str, Any]:
        from wiki.index import WikiIndexer
        from wiki.reliability import atomic_json
        from wiki.schema import WikiConfig

        try:
            with open(self._wiki_page_archives_path, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return _err("Archived Wiki page not found")
        item = manifest.get(document_id)
        if not item or not os.path.isfile(item.get("archived", "")):
            return _err("Archived Wiki page not found")
        os.makedirs(os.path.dirname(item["original"]), exist_ok=True)
        if os.path.exists(item["original"]):
            return _err("The original Wiki page path is already in use")
        shutil.move(item["archived"], item["original"])
        manifest.pop(document_id, None)
        atomic_json(self._wiki_page_archives_path, manifest)
        WikiIndexer(self._wiki_target_vault(), WikiConfig()).rebuild_from_disk()
        summary = self._sync_registered_sources(mode="incremental", config=config or {})
        return _ok(document_id=document_id, restored=True, sync=summary.to_dict())

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
        return self._hydrate_documents(available)

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

    def _all_wiki_materials(self, course: str | None = None) -> list[dict[str, Any]]:
        materials = self.list_documents(course=course, collection="material")
        if not materials.get("ok"):
            return []
        return self._hydrate_documents(materials.get("documents") or [])

    def _hydrate_documents(self, summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Read document sections in one SQLite connection for Wiki planning."""
        if not summaries:
            return []
        from rag.sqlite_store import KBSQLiteStore

        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            document_ids = [str(item["document_id"]) for item in summaries]
            sections_by_document = store.get_chunks_for_documents(document_ids)
        finally:
            store.close()
        return [
            {
                **summary,
                "sections": [
                    self._public_section(section)
                    for section in sections_by_document.get(str(summary["document_id"]), [])
                ],
            }
            for summary in summaries
        ]

    def wiki_coverage(self) -> dict[str, Any]:
        try:
            from wiki.orchestration import wiki_coverage

            documents = self._all_wiki_materials()
            coverage = wiki_coverage(self._wiki_target_vault(), documents)
        except (OSError, ValueError) as exc:
            return _err(str(exc))
        counts = {
            status: sum(1 for item in coverage if item["status"] == status)
            for status in ("uncovered", "partial", "covered", "stale")
        }
        return _ok(documents=coverage, counts=counts)

    def _wiki_run_documents(
        self,
        scope_mode: str,
        document_ids: list[str] | None = None,
        course: str | None = None,
        topic: str = "",
        instruction: str = "",
        config: dict | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        from wiki.orchestration import wiki_coverage

        all_documents = self._all_wiki_materials()
        coverage = wiki_coverage(self._wiki_target_vault(), all_documents)
        by_id = {str(item["document_id"]): item for item in all_documents}
        coverage_by_id = {str(item["document_id"]): item for item in coverage}
        seed_ids = [item for item in document_ids or [] if item in by_id]
        selected_ids: list[str] = []
        if scope_mode == "uncovered":
            selected_ids = [
                item["document_id"] for item in coverage
                if item["status"] in {"uncovered", "partial", "stale"}
            ]
        elif scope_mode == "selected_only":
            selected_ids = seed_ids
        elif scope_mode == "course":
            selected_ids = [
                item["document_id"] for item in all_documents
                if course and item.get("course") == course
            ]
        elif scope_mode == "smart_library":
            selected_ids = list(seed_ids)
            query = (topic or instruction).strip()
            if not query and seed_ids:
                query = " ".join(str(by_id[item].get("title") or "") for item in seed_ids)
            if query:
                search = self.search(
                    query=query,
                    top_k=20,
                    mode="auto",
                    preferred_document_ids=seed_ids,
                    config=config or {},
                )
                for result in search.get("results") or []:
                    document_id = str(result.get("document_id") or "")
                    if result.get("collection") == "material" and document_id in by_id and document_id not in selected_ids:
                        selected_ids.append(document_id)
            if not selected_ids:
                if query:
                    import unicodedata
                    normalized_query = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", unicodedata.normalize("NFKC", query).casefold())
                    selected_ids = [
                        item["document_id"] for item in all_documents
                        if normalized_query and normalized_query in re.sub(
                            r"[^0-9a-z\u4e00-\u9fff]+", "",
                            unicodedata.normalize("NFKC", str(item.get("title") or "")).casefold(),
                        )
                    ]
                else:
                    selected_ids = [
                        item["document_id"] for item in coverage
                        if item["status"] in {"uncovered", "partial", "stale"}
                    ]
        else:
            raise ValueError("Unsupported Wiki scope mode")
        seed_set = set(seed_ids)
        selected = [by_id[item] for item in selected_ids if item in by_id]
        selected.sort(key=lambda item: (
            0 if item["document_id"] in seed_set else 1,
            str(item.get("course") or "").casefold(),
            str(item.get("source") or item.get("title") or "").casefold(),
        ))
        return selected, [coverage_by_id[item["document_id"]] for item in selected]

    def create_wiki_run(
        self,
        llm_provider,
        *,
        action: str = "generate",
        scope_mode: str = "smart_library",
        document_ids: list[str] | None = None,
        course: str | None = None,
        topic: str = "",
        instruction: str = "",
        config: dict | None = None,
    ) -> dict[str, Any]:
        try:
            from wiki.orchestration import WikiOrchestrator

            documents, coverage = self._wiki_run_documents(
                scope_mode,
                document_ids=document_ids,
                course=course,
                topic=topic,
                instruction=instruction,
                config=config,
            )
            if not documents:
                return _err("No uncovered or matching learning materials were found")
            plan = WikiOrchestrator(
                self.workspace,
                self._wiki_target_vault(),
                llm_provider,
            ).create_plan(
                documents,
                action=action,
                scope_mode=scope_mode,
                seed_document_ids=document_ids or [],
                topic=topic,
                instruction=instruction,
                coverage_before=coverage,
            )
        except Exception as exc:
            return _err(str(exc))
        return _ok(**plan)

    def start_wiki_run(
        self,
        llm_provider,
        *,
        action: str = "generate",
        scope_mode: str = "smart_library",
        document_ids: list[str] | None = None,
        course: str | None = None,
        topic: str = "",
        instruction: str = "",
        config: dict | None = None,
        generation_mode: str = "standard",
        budget: dict[str, int] | None = None,
        force_regenerate: bool = False,
        discovery_provider=None,
    ) -> dict[str, Any]:
        try:
            from wiki.orchestration import BATCH_SIZE, WikiOrchestrator, WikiRunStore

            documents, coverage = self._wiki_run_documents(
                scope_mode,
                document_ids=document_ids,
                course=course,
                topic=topic,
                instruction=instruction,
                config=config,
            )
            if not documents:
                return _err("No uncovered or matching learning materials were found")
            if generation_mode not in {"catalog", "standard", "deep"}:
                return _err("Unsupported Wiki generation mode")
            all_document_ids = [item["document_id"] for item in documents]
            if generation_mode == "standard":
                documents = documents[:BATCH_SIZE]
                coverage = coverage[:BATCH_SIZE]
            store = WikiRunStore(self.workspace)
            run = store.create({
                "scope": {
                    "mode": scope_mode,
                    "seed_document_ids": list(document_ids or []),
                    "document_ids": [item["document_id"] for item in documents],
                    "discovered_document_ids": all_document_ids,
                    "documents": [item.get("title") or item.get("source") for item in documents],
                },
                "topic": topic.strip(),
                "instruction": instruction.strip(),
                "action": action,
                "coverage_before": coverage,
                "total_batches": (len(documents) + BATCH_SIZE - 1) // BATCH_SIZE,
                "completed_batches": 0,
                "completed_pages": 0,
                "total_pages": 0,
                "generation_mode": generation_mode,
                "budget": {"max_requests": 24, "max_input_tokens": 300000, "max_output_tokens": 40000, **(budget or {})},
                "remaining_document_ids": all_document_ids[len(documents):],
                "request": {
                    "action": action,
                    "scope_mode": scope_mode,
                    "document_ids": list(document_ids or []),
                    "course": course,
                    "topic": topic,
                    "instruction": instruction,
                    "generation_mode": generation_mode,
                    "force_regenerate": force_regenerate,
                },
            })

            def worker():
                try:
                    plan = WikiOrchestrator(
                        self.workspace,
                        self._wiki_target_vault(),
                        llm_provider,
                        run_id=run["run_id"],
                        budget=run["budget"],
                        force_regenerate=force_regenerate,
                        discovery_provider=discovery_provider,
                    ).create_plan(
                        documents,
                        action=action,
                        scope_mode=scope_mode,
                        seed_document_ids=document_ids or [],
                        topic=topic,
                        instruction=instruction,
                        coverage_before=coverage,
                        run_id=run["run_id"],
                        progress=lambda **values: store.update(run["run_id"], **values),
                        cancel_check=lambda: store.cancel_requested(run["run_id"]),
                        generation_mode=generation_mode,
                    )
                    plan["remaining_document_ids"] = run.get("remaining_document_ids") or []
                    from wiki.reliability import atomic_json
                    atomic_json(
                        os.path.join(self.workspace, ".bobodan", "wiki", "plans", f"{plan['plan_id']}.json"),
                        plan,
                    )
                except Exception as exc:
                    logger.exception("Wiki run %s failed during planning", run["run_id"])
                    try:
                        store.update(
                            run["run_id"],
                            status="failed",
                            phase="error",
                            error=f"整理运行失败：{exc}",
                            retryable=True,
                        )
                    except Exception:
                        logger.exception("Could not mark wiki run %s as failed", run["run_id"])

            import threading
            threading.Thread(target=worker, name=f"wiki-run-{run['run_id'][:8]}", daemon=True).start()
        except Exception as exc:
            return _err(str(exc))
        return _ok(**run)

    def estimate_wiki_run(
        self,
        *,
        scope_mode: str = "uncovered",
        document_ids: list[str] | None = None,
        course: str | None = None,
        topic: str = "",
        instruction: str = "",
        generation_mode: str = "standard",
        provider_name: str = "",
        model: str = "",
        config: dict | None = None,
    ) -> dict[str, Any]:
        try:
            from service.usage_service import UsageService
            from wiki.orchestration import BATCH_SIZE, WikiOrchestrator

            documents, _coverage = self._wiki_run_documents(
                scope_mode,
                document_ids=document_ids,
                course=course,
                topic=topic,
                instruction=instruction,
                config=config,
            )
            if generation_mode == "standard":
                documents = documents[:BATCH_SIZE]
            if not documents:
                return _err("No uncovered or matching learning materials were found")
            _catalog, lookup = WikiOrchestrator._catalog(documents)
            windows = WikiOrchestrator._prompt_windows(documents, lookup)
            concept_max = 0 if generation_mode == "catalog" else 6 if generation_mode == "standard" else 12 * ((len(documents) + 4) // 5)
            page_min = len(documents)
            page_max = page_min + concept_max
            discovery_min = 0 if generation_mode == "catalog" else len(windows)
            discovery_max = discovery_min + ((discovery_min + 3) // 4)
            drafting_min = 0 if generation_mode == "catalog" else page_min
            drafting_max = 0 if generation_mode == "catalog" else page_max + ((page_max + 3) // 4)
            request_min = discovery_min + drafting_min
            request_max = discovery_max + drafting_max
            source_chars = sum(len(str(item.get("text") or "")) for item in lookup.values())
            input_min = 0 if generation_mode == "catalog" else max(1000, source_chars // 2)
            input_max = 0 if generation_mode == "catalog" else input_min + page_max * 10000
            output_min = 0
            output_max = 0 if generation_mode == "catalog" else page_max * 3000
            history = [
                item for item in UsageService().summary(days=30)["entries"]
                if item.get("subsystem") == "wiki"
                and item.get("status") == "ok"
                and item.get("run_id")
                and int(item.get("duration_ms") or 0) > 0
                and (not provider_name or str(item.get("provider") or "").casefold() == provider_name.casefold())
                and (not model or str(item.get("model") or "").casefold() == model.casefold())
            ]
            discovery_history = [item for item in history if str(item.get("operation") or "").startswith("wiki_discovery")]
            drafting_history = [item for item in history if item.get("operation") == "wiki_drafting"]

            def profile(items: list[dict[str, Any]], field: str, fallback_low: int, fallback_high: int) -> tuple[int, int]:
                values = sorted(int(item.get(field) or 0) for item in items if int(item.get(field) or 0) > 0)
                if not values:
                    return fallback_low, fallback_high
                median = values[len(values) // 2]
                p90 = values[min(len(values) - 1, int((len(values) - 1) * .9))]
                return median, max(median, p90)

            discovery_duration = profile(discovery_history, "duration_ms", 8000, 45000)
            drafting_duration = profile(drafting_history, "duration_ms", 8000, 45000)
            duration_range = [
                round((discovery_min * discovery_duration[0] + drafting_min * drafting_duration[0]) / 1000),
                round((discovery_max * discovery_duration[1] + drafting_max * drafting_duration[1]) / 1000),
            ]
            if generation_mode != "catalog" and discovery_history and drafting_history:
                discovery_input = profile(discovery_history, "input_tokens", max(1000, source_chars // 2), max(1000, source_chars))
                drafting_input = profile(drafting_history, "input_tokens", 1000, 10000)
                drafting_output = profile(drafting_history, "output_tokens", 500, 3000)
                discovery_output = profile(discovery_history, "output_tokens", 500, 3000)
                input_min = discovery_min * discovery_input[0] + drafting_min * drafting_input[0]
                input_max = discovery_max * discovery_input[1] + drafting_max * drafting_input[1]
                output_min = discovery_min * discovery_output[0] + drafting_min * drafting_output[0]
                output_max = discovery_max * discovery_output[1] + drafting_max * drafting_output[1]
            sample_size = len(history)
            confidence = (
                "high" if sample_size >= 12 and len(discovery_history) >= 4 and len(drafting_history) >= 4
                else "medium" if sample_size >= 6 and discovery_history and drafting_history
                else "low"
            )
            return _ok(
                generation_mode=generation_mode,
                document_count=len(documents),
                batch_count=(len(documents) + BATCH_SIZE - 1) // BATCH_SIZE,
                estimated_pages=[page_min, page_max],
                request_range=[request_min, request_max],
                input_token_range=[input_min, input_max],
                output_token_range=[output_min, output_max],
                duration_range_seconds=duration_range,
                rough=confidence == "low",
                confidence=confidence,
                historical_sample_size=sample_size,
                local_cache_reuse_included=False,
                assumptions=[
                    "估算按 Wiki 发现与页面写作分别计算",
                    "上界预留约 25% 的格式修复请求",
                    "本地精确草稿缓存会让实际请求和耗时低于区间",
                ],
                provider=provider_name,
                model=model,
            )
        except (OSError, ValueError) as exc:
            return _err(str(exc))

    def resume_wiki_run(self, run_id: str, llm_provider, additional_budget: dict[str, int] | None = None, discovery_provider=None) -> dict[str, Any]:
        try:
            from wiki.orchestration import WikiRunStore

            store = WikiRunStore(self.workspace)
            run = store.get(run_id)
            if run.get("status") not in {"paused_budget", "cancelled", "failed"}:
                return _err("This Wiki run is not paused")
            budget = dict(run.get("budget") or {})
            previous_usage = run.get("usage") or {}
            additions = additional_budget or {}
            for key in ("max_requests", "max_input_tokens", "max_output_tokens"):
                value = additions.get(key, 0)
                used_key = {
                    "max_requests": "requests",
                    "max_input_tokens": "input_tokens",
                    "max_output_tokens": "output_tokens",
                }.get(key)
                remaining = max(0, int(budget.get(key) or 0) - int(previous_usage.get(used_key) or 0))
                budget[key] = remaining + int(value)
            request = run.get("request") or {}
            result = self.start_wiki_run(
                llm_provider,
                action=request.get("action", "generate"),
                scope_mode=request.get("scope_mode", "uncovered"),
                document_ids=request.get("document_ids") or [],
                course=request.get("course"),
                topic=request.get("topic", ""),
                instruction=request.get("instruction", ""),
                generation_mode=request.get("generation_mode", "standard"),
                budget=budget,
                force_regenerate=bool(request.get("force_regenerate")),
                discovery_provider=discovery_provider,
            )
            if not result.get("ok"):
                return result
            store.update(run_id, status="replaced", replacement_run_id=result["run_id"])
            return _ok(previous_run_id=run_id, **{key: value for key, value in result.items() if key != "ok"})
        except (OSError, ValueError) as exc:
            return _err(str(exc))

    def wiki_run_usage(self, run_id: str) -> dict[str, Any]:
        from service.usage_service import UsageService

        return _ok(**UsageService().summary(days=365, run_id=run_id))

    def get_wiki_run(self, run_id: str) -> dict[str, Any]:
        planned = self.get_wiki_plan(run_id)
        if planned.get("ok"):
            return planned
        try:
            from wiki.orchestration import WikiRunStore

            return _ok(**WikiRunStore(self.workspace).get(run_id))
        except (OSError, ValueError) as exc:
            return _err(str(exc))

    def cancel_wiki_run(self, run_id: str) -> dict[str, Any]:
        try:
            from wiki.orchestration import WikiRunStore

            store = WikiRunStore(self.workspace)
            run = store.get(run_id)
            if run.get("status") == "planning":
                return _ok(**store.update(run_id, cancel_requested=True, phase="cancelling"))
        except (OSError, ValueError):
            pass
        try:
            from wiki.workflow import WikiWorkflow

            plan = WikiWorkflow(self.workspace, self._wiki_target_vault()).cancel_plan(run_id)
        except (OSError, ValueError) as exc:
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

    def recover_wiki_plan(
        self,
        plan_id: str,
        strategy: str,
        llm_provider=None,
        config: dict | None = None,
    ) -> dict[str, Any]:
        try:
            from wiki.workflow import WikiWorkflow

            workflow = WikiWorkflow(self.workspace, self._wiki_target_vault())
            current = workflow.get_plan(plan_id)
            if not current.get("staging"):
                return _err("This Wiki plan has no pages waiting for correction")
            if strategy == "keep_existing":
                workflow.skip_staged_changes(plan_id)
                result = self.apply_wiki_plan(plan_id, config=config)
                if result.get("ok"):
                    workflow.tasks.resolve_plan_failures(plan_id)
                return result
            if strategy != "regenerate":
                return _err("Unsupported Wiki recovery strategy")
            if llm_provider is None:
                return _err("No configured model is available for Wiki replanning")
            instruction = "\n".join(item for item in (
                str(current.get("instruction") or "").strip(),
                (
                    "修正上一版计划：已有 Wiki 页面包含更多信息。更新时必须保留已有要点并补充新资料，"
                    "不要用更短的草稿覆盖现有页面；若无法安全补全，请跳过该页面。"
                ),
            ) if item)
            scope = current.get("scope") or {}
            if current.get("run_id") or scope.get("mode"):
                result = self.start_wiki_run(
                    llm_provider,
                    action=str(current.get("action") or "generate"),
                    scope_mode=str(scope.get("mode") or "smart_library"),
                    document_ids=list(scope.get("seed_document_ids") or scope.get("document_ids") or []),
                    topic=str(current.get("topic") or ""),
                    instruction=instruction,
                    config=config,
                )
            else:
                result = self.create_wiki_plan(
                    llm_provider,
                    document_ids=list(scope.get("document_ids") or []),
                    action=str(current.get("action") or "generate"),
                    instruction=instruction,
                )
            if not result.get("ok"):
                return result
            workflow.mark_replaced(plan_id, str(result.get("plan_id") or result.get("run_id")))
            workflow.tasks.resolve_plan_failures(plan_id)
            return result
        except (OSError, ValueError) as exc:
            return _err(str(exc))

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

    def wiki_tasks(self) -> dict[str, Any]:
        from wiki.workflow import WikiWorkflow

        tasks = WikiWorkflow(self.workspace, self._wiki_target_vault()).list_tasks()
        return _ok(tasks=tasks)

    def cancel_wiki_task(self, task_id: str) -> dict[str, Any]:
        try:
            from wiki.workflow import WikiWorkflow

            task = WikiWorkflow(self.workspace, self._wiki_target_vault()).cancel_task(task_id)
        except (FileNotFoundError, ValueError) as exc:
            return _err(str(exc))
        return _ok(task=task)

    def retry_wiki_task(
        self,
        task_id: str,
        llm_provider=None,
        config: dict | None = None,
    ) -> dict[str, Any]:
        try:
            from wiki.workflow import WikiWorkflow

            workflow = WikiWorkflow(self.workspace, self._wiki_target_vault())
            task = workflow.get_task(task_id)
        except (FileNotFoundError, ValueError) as exc:
            return _err(str(exc))
        if not task.get("retryable") or task.get("status") != "failed":
            return _err("This Wiki task is not retryable")
        payload = task.get("payload") or {}
        if task.get("operation") in {"plan", "orchestrate"}:
            if llm_provider is None:
                return _err("No configured model is available for Wiki planning")
            if task.get("operation") == "orchestrate":
                result = self.start_wiki_run(
                    llm_provider,
                    action=str(payload.get("action") or "generate"),
                    scope_mode=str(payload.get("scope_mode") or "smart_library"),
                    document_ids=list(payload.get("document_ids") or []),
                    topic=str(payload.get("topic") or ""),
                    instruction=str(payload.get("instruction") or ""),
                    config=config,
                )
            else:
                result = self.create_wiki_plan(
                    llm_provider,
                    document_ids=list(payload.get("document_ids") or []),
                    action=str(payload.get("action") or "generate"),
                    instruction=str(payload.get("instruction") or ""),
                )
        elif task.get("operation") == "apply":
            plan_id = str(payload.get("plan_id") or task.get("plan_id") or "")
            result = self.apply_wiki_plan(plan_id, config=config)
        else:
            return _err("This Wiki task type cannot be retried")
        if not result.get("ok"):
            return result
        workflow.tasks.update(
            task_id,
            status="completed",
            retryable=False,
            retried_by=result.get("task_id") or result.get("plan_id") or result.get("run_id"),
        )
        return _ok(retry_of=task_id, result={key: value for key, value in result.items() if key != "ok"})

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
                "extraction_counts": report.extraction_counts or {},
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

        return _err(f"Document not found: {document_id}")

    def get_document_extraction(self, document_id: str) -> dict[str, Any]:
        """Return the stored extraction report for one document (P5G.0)."""
        db_path = knowledge_path(self.workspace, "knowledge.db")
        if os.path.exists(db_path):
            from rag.sqlite_store import KBSQLiteStore
            store = KBSQLiteStore(self.workspace)
            store.init_db()
            try:
                report = store.get_extraction_report(document_id)
            finally:
                store.close()
            if report is not None:
                return _ok(report=report)
        return _err(f"Document not found: {document_id}", code="document_not_found")

    def delete_document(self, document_id: str, config: dict | None = None) -> dict[str, Any]:
        db_path = knowledge_path(self.workspace, "knowledge.db")
        if not os.path.exists(db_path):
            return _err(f"Document not found: {document_id}", code="document_not_found")

        from rag.sqlite_store import KBSQLiteStore
        store = KBSQLiteStore(self.workspace)
        store.init_db()
        try:
            document = store.get_document(document_id)
        finally:
            store.close()
        if document is None:
            return _err(f"Document not found: {document_id}", code="document_not_found")

        impact = self.document_impact(document_id, document=document)
        if not impact.get("ok"):
            return impact

        path = document.get("path")
        if not path or not self._is_within_workspace(path, self.managed_sources_dir):
            return _err(
                "This knowledge source is read-only and cannot be deleted here",
                code="document_read_only",
            )
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
                self._mark_wiki_sources_stale(document_id, document.get("source") or path)
            else:
                os.remove(path)

        summary = self._sync_registered_sources(mode="incremental", config=config or {})
        return _ok(document_id=document_id, impact=impact.get("affected_pages", []), sync=summary.to_dict())

    def document_impact(self, document_id: str, document: dict[str, Any] | None = None) -> dict[str, Any]:
        if document is None:
            detail = self.get_document(document_id)
            if not detail.get("ok") or detail.get("document", {}).get("collection") != "material":
                return _err(f"Document not found: {document_id}")
            document = detail["document"]
        source = str(document.get("source") or "").replace("\\", "/")
        affected = []
        wiki_dir = os.path.join(self._wiki_target_vault(), "wiki")
        if os.path.isdir(wiki_dir):
            import yaml

            for root, dirs, files in os.walk(wiki_dir):
                dirs[:] = [name for name in dirs if name != "templates"]
                for filename in files:
                    if not filename.endswith(".md") or filename in {"index.md", "log.md"}:
                        continue
                    path = os.path.join(root, filename)
                    try:
                        with open(path, "r", encoding="utf-8") as handle:
                            content = handle.read()
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
                    refs = [item for item in metadata.get("source_refs") or [] if isinstance(item, dict)]
                    sources = [str(item).replace("\\", "/") for item in metadata.get("sources") or []]
                    matches = any(str(item.get("document_id") or "") == document_id for item in refs)
                    matches = matches or source in sources or any(
                        source.endswith(item) or item.endswith(source) for item in sources if item and source
                    )
                    if not matches:
                        continue
                    identities = {
                        str(item.get("document_id") or item.get("source") or "").strip()
                        for item in refs
                        if item.get("document_id") or item.get("source")
                    } or set(sources)
                    affected.append({
                        "title": str(metadata.get("title") or os.path.splitext(filename)[0]),
                        "page_type": str(metadata.get("type") or ""),
                        "target": os.path.relpath(path, wiki_dir).replace("\\", "/"),
                        "source_count": len(identities),
                        "action": "archive_candidate" if len(identities) <= 1 else "mark_needs_update",
                    })
        return _ok(
            document_id=document_id,
            title=document.get("title") or document.get("source") or "",
            affected_pages=affected,
            affected_count=len(affected),
        )

    def _mark_wiki_sources_stale(self, document_id: str, source: str) -> None:
        """Mark generated pages for review when an original source is archived."""
        import yaml

        wiki_dir = os.path.join(self._wiki_target_vault(), "wiki")
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
                    with open(path, "r", encoding="utf-8") as handle:
                        content = handle.read()
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
                refs = [item for item in metadata.get("source_refs") or [] if isinstance(item, dict)]
                sources = [str(item).replace("\\", "/") for item in metadata.get("sources") or []]
                referenced = any(str(item.get("document_id") or "") == document_id for item in refs)
                if not referenced and normalized not in sources and not any(normalized.endswith(item) or item.endswith(normalized) for item in sources):
                    continue
                metadata["status"] = "needs_update"
                rendered = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
                from wiki.reliability import atomic_text

                atomic_text(path, f"---\n{rendered}\n---{content[end + 3:]}")

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
            "extraction_status": document.get("extraction_status", "complete"),
            "extraction_total_units": document.get("extraction_total_units", 0),
            "extraction_extracted_units": document.get("extraction_extracted_units", 0),
            "extraction_empty_units": document.get("extraction_empty_units", 0),
            "updated_at": document.get("updated_at", ""),
            "content_hash": document.get("content_hash", ""),
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

    # --- RAG Search ---

    def search(
        self,
        query: str,
        course: str | None = None,
        top_k: int = 5,
        mode: str = "auto",
        document_ids: list[str] | None = None,
        preferred_document_ids: list[str] | None = None,
        collection: str = "all",
        config: dict | None = None,
    ) -> dict[str, Any]:
        if not query or not query.strip():
            return _err("query is required")

        storage_dir = knowledge_dir(self.workspace)
        db_path = os.path.join(storage_dir, "knowledge.db")
        if not os.path.exists(db_path):
            return _err("RAG index not found. Run obsidian_sync first.")

        from rag.retriever import search_index_with_status

        requested_top_k = max(1, min(top_k, 20))
        candidate_top_k = 20 if document_ids or preferred_document_ids else requested_top_k
        results, retrieval_status = search_index_with_status(
            self.workspace,
            query=query.strip(),
            course=course,
            top_k=candidate_top_k,
            config=config or {},
            mode=mode,
        )
        source_documents = {
            item["source"]: item
            for item in self.list_documents(collection="all").get("documents", [])
        }
        allowed_document_ids = set(document_ids or [])
        preferred_ids = set(preferred_document_ids or [])
        merged = []
        seen = set()
        for item in results:
            visible_document = source_documents.get(str(item.get("source") or ""))
            if not visible_document:
                continue
            if collection != "all" and visible_document.get("collection") != collection:
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
        if preferred_ids and not allowed_document_ids:
            merged.sort(key=lambda item: (
                0 if item.get("document_id") in preferred_ids else 1,
                -float(item.get("score") or item.get("similarity") or 0),
            ))
        if not allowed_document_ids:
            wiki_results = [item for item in merged if item.get("collection") == "wiki"]
            material_results = [item for item in merged if item.get("collection") == "material"]
            if wiki_results and material_results:
                merged = wiki_results[:2] + material_results + wiki_results[2:]
        return _ok(results=merged[:requested_top_k], **retrieval_status)

    # --- Reset ---

    def reset(self) -> dict[str, Any]:
        from rag.retriever import clear_retrieval_cache

        clear_retrieval_cache(self.workspace)
        storage_dir = knowledge_dir(self.workspace)
        if os.path.exists(storage_dir):
            # Preserve retired JSON indexes and graph_store.json. They are
            # read-only migration sources and may contain the user's only copy.
            for filename in (
                "knowledge.db", "knowledge.db-shm", "knowledge.db-wal", "bobodan.db",
                "bobodan.db-shm", "bobodan.db-wal", "sync_state.json", "import_report.json",
            ):
                path = os.path.join(storage_dir, filename)
                if os.path.isfile(path):
                    os.remove(path)
            qdrant = os.path.join(storage_dir, "qdrant")
            if os.path.isdir(qdrant):
                shutil.rmtree(qdrant)
        return _ok(message="Knowledge base reset")
