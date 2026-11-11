"""Wiki 高级维护：健康检查、修复计划、页面读写与归档、全库整理计划与运行、任务重试。

2026-11-11 从 ``service/kb_service.py`` 原样移出（行为不变）。Wiki 是高级维护能力
（``docs/ROADMAP.md`` §5「D-WIKI」）：不进一级导航，也不作为回答或出题证据。

以 mixin 形式挂回 ``KBService``：调用方与测试仍然写 ``KBService(...).create_wiki_plan(...)``，
共享的资料库能力（文档列表、检索、同步、路径判断）继续由 ``KBService`` 提供。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from typing import Any

from knowledge.paths import knowledge_path
from service._result import err as _err, ok as _ok

logger = logging.getLogger("service.kb_service")


class WikiMaintenanceMixin:
    """KBService 的 Wiki 维护部分。依赖 KBService 提供的 workspace / 文档 / 检索 / 同步方法。"""

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
