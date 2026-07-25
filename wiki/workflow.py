"""User-confirmed LLM Wiki planning, application, and rollback workflow."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import yaml

from .compiler import _parse_llm_json, _safe_filename
from .index import WikiIndexer
from .reliability import (
    WIKI_WRITE_LOCK, WikiTaskStore, atomic_text, merge_page, stage_change, validate_change,
)
from .schema import CompileResult, GENERATED_BY, WikiConfig, WikiPage


PLAN_PROMPT = """You are editing a local learning Wiki from user-selected source material.
Return JSON only. Do not invent facts or source identifiers.

User instruction: {instruction}
Requested action: {action}

Existing Wiki pages:
{existing_pages}

Source excerpts:
{source_excerpts}

Return this shape:
{{
  "pages": [
    {{
      "title": "short canonical title",
      "page_type": "wiki_source, wiki_concept, wiki_entity, wiki_analysis, or wiki_question",
      "summary": "one paragraph",
      "body": "clear Markdown explanation without a top-level heading",
      "tags": ["tag"],
      "related": ["other page title"],
      "claims": [{{"text": "important claim", "source_ids": ["S1"]}}]
    }}
  ]
}}

Rules:
- Use only the supplied excerpts.
- Return 3-12 useful pages. Include at least one wiki_source summary page.
- Every important claim must cite at least one supplied source id.
- Prefer updating an existing canonical page over creating a near-duplicate.
- Keep concept and entity pages concise, readable, and useful to both people and models.
- Related titles must refer to pages in this plan or existing Wiki pages.
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_title(value: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)


def _atomic_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def _read_frontmatter(path: str) -> tuple[dict, str]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return {}, ""
    if not content.startswith("---"):
        return {}, content
    end = content.find("---", 3)
    if end < 0:
        return {}, content
    try:
        metadata = yaml.safe_load(content[3:end]) or {}
    except yaml.YAMLError:
        metadata = {}
    return metadata, content[end + 3:].strip()


class WikiWorkflow:
    def __init__(self, workspace: str, vault_path: str, llm_provider=None):
        self.workspace = os.path.abspath(workspace)
        self.vault_path = os.path.abspath(vault_path)
        self.llm = llm_provider
        self.config = WikiConfig()
        self.tasks = WikiTaskStore(self.workspace)

    @property
    def plan_dir(self) -> str:
        return os.path.join(self.workspace, ".bobodan", "wiki", "plans")

    @property
    def checkpoint_dir(self) -> str:
        return os.path.join(self.workspace, ".bobodan", "wiki", "checkpoints")

    def _plan_path(self, plan_id: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{32}", plan_id):
            raise ValueError("Invalid Wiki plan id")
        return os.path.join(self.plan_dir, f"{plan_id}.json")

    def _checkpoint_path(self, checkpoint_id: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{32}", checkpoint_id):
            raise ValueError("Invalid Wiki checkpoint id")
        return os.path.join(self.checkpoint_dir, checkpoint_id)

    def _existing_pages(self) -> dict[str, list[dict]]:
        pages: dict[str, list[dict]] = {}
        wiki_dir = os.path.join(self.vault_path, self.config.wiki_dir)
        for page_type in (
            "wiki_source", "wiki_entity", "wiki_concept", "wiki_analysis", "wiki_question", "wiki_note",
        ):
            directory = self.config.page_path(self.vault_path, page_type)
            if not os.path.isdir(directory):
                continue
            for name in os.listdir(directory):
                if not name.lower().endswith(".md"):
                    continue
                path = os.path.join(directory, name)
                metadata, body = _read_frontmatter(path)
                title = str(metadata.get("title") or os.path.splitext(name)[0]).strip()
                key = _canonical_title(title)
                if not key:
                    continue
                pages.setdefault(f"{page_type}:{key}", []).append({
                    "title": title,
                    "page_type": metadata.get("type") or page_type,
                    "generated_by": metadata.get("generated_by"),
                    "path": path,
                    "relative_path": os.path.relpath(path, wiki_dir).replace("\\", "/"),
                    "body": body[:2400],
                    "body_length": len(body),
                    "content_revision": int(metadata.get("content_revision") or 1),
                    "managed_by": metadata.get("managed_by") or ("ai" if metadata.get("generated_by") == GENERATED_BY else "user"),
                })
        return pages

    def _source_catalog(self, documents: list[dict]) -> tuple[list[dict], str]:
        catalog = []
        rendered = []
        total_chars = 0
        for document in documents:
            for section in document.get("sections", []):
                text = str(section.get("text") or "").strip()
                if not text or total_chars >= 30000:
                    continue
                text = text[:1800]
                source_id = f"S{len(catalog) + 1}"
                ref = {
                    "source_id": source_id,
                    "document_id": document["document_id"],
                    "chunk_id": section.get("chunk_id"),
                    "title": document.get("title") or document.get("source") or "Source",
                    "heading": section.get("heading") or None,
                    "page": section.get("page_start"),
                    "slide": section.get("slide_start"),
                    "source": document.get("source") or "",
                    "collection": "material",
                }
                catalog.append(ref)
                location = ref["heading"] or (f"page {ref['page']}" if ref["page"] else f"slide {ref['slide']}" if ref["slide"] else "")
                rendered.append(f"[{source_id}] {ref['title']} {location}\n{text}")
                total_chars += len(text)
        if not catalog:
            raise ValueError("The selected materials do not contain readable indexed sections")
        return catalog, "\n\n".join(rendered)

    @staticmethod
    def _call_llm(llm_provider, prompt: str) -> dict:
        if llm_provider is None:
            raise ValueError("No configured model is available for Wiki planning")
        response = llm_provider.complete([{"role": "user", "content": prompt}])
        parsed = _parse_llm_json(response.content or "")
        if not isinstance(parsed, dict) or not isinstance(parsed.get("pages"), list):
            raise ValueError("The model did not return a valid Wiki plan")
        return parsed

    @staticmethod
    def _source_link(ref: dict) -> str:
        target = f"/library?collection=material&document={quote(str(ref['document_id']))}"
        if ref.get("chunk_id"):
            target += f"&chunk={quote(str(ref['chunk_id']))}"
        return target

    def _render_page(self, draft: dict, source_lookup: dict[str, dict], related: list[str]) -> tuple[str, list[dict]]:
        summary = str(draft.get("summary") or "").strip()
        body = str(draft.get("body") or "").strip()
        claims = []
        used_refs: dict[str, dict] = {}
        for claim in draft.get("claims") or []:
            if not isinstance(claim, dict):
                continue
            refs = [source_lookup[item] for item in claim.get("source_ids") or [] if item in source_lookup]
            text = str(claim.get("text") or "").strip()
            if not text or not refs:
                continue
            for ref in refs:
                used_refs[ref["source_id"]] = ref
            citations = " ".join(f"[{ref['source_id']}]({self._source_link(ref)})" for ref in refs)
            claims.append(f"- {text} {citations}")

        lines = []
        if summary:
            lines.extend(["## 摘要", "", summary, ""])
        if body:
            lines.extend([body, ""])
        if claims:
            lines.extend(["## 关键结论", "", *claims, ""])
        if related:
            lines.extend([
                "## 相关概念",
                "",
                *[f"- [{title}](/library?collection=wiki&title={quote(title)})" for title in related],
                "",
            ])
        if used_refs:
            lines.extend(["## 原始资料", ""])
            for ref in used_refs.values():
                location = ref.get("heading") or (f"第 {ref['page']} 页" if ref.get("page") else f"第 {ref['slide']} 页" if ref.get("slide") else "")
                suffix = f" · {location}" if location else ""
                lines.append(f"- [{ref['title']}{suffix}]({self._source_link(ref)})")
        return "\n".join(lines).strip(), list(used_refs.values())

    def _create_plan(self, documents: list[dict], action: str = "generate", instruction: str = "") -> dict:
        if action not in {"generate", "update"}:
            raise ValueError("Wiki action must be generate or update")
        catalog, source_excerpts = self._source_catalog(documents)
        source_lookup = {item["source_id"]: item for item in catalog}
        existing = self._existing_pages()
        existing_prompt = "\n".join(
            f"- {items[0]['title']} ({items[0]['page_type']}): {items[0]['body']}"
            for items in existing.values()
        ) or "(none)"
        result = self._call_llm(self.llm, PLAN_PROMPT.format(
            action=action,
            instruction=instruction.strip() or "Organize the selected learning materials into a concise Wiki.",
            existing_pages=existing_prompt[:12000],
            source_excerpts=source_excerpts,
        ))
        drafts = [item for item in result["pages"] if isinstance(item, dict)][:12]
        if drafts and not any(item.get("page_type") == "wiki_source" for item in drafts):
            first = documents[0]
            title = first.get("title") or first.get("source") or "资料摘要"
            first_refs = catalog[: min(3, len(catalog))]
            drafts.insert(0, {
                "title": str(title),
                "page_type": "wiki_source",
                "summary": f"所选原始资料《{title}》的可追溯摘要。",
                "body": "本页用于连接原始资料与相关概念页面，事实请回到原文核实。",
                "tags": ["资料摘要"],
                "related": [],
                "claims": [
                    {"text": "本页依据所选原始资料整理。", "source_ids": [item["source_id"] for item in first_refs]}
                ],
            })

        relation_map: dict[str, set[str]] = {}
        title_by_key = {}
        for draft in drafts:
            title = str(draft.get("title") or "").strip()
            key = _canonical_title(title)
            if key:
                title_by_key[key] = title
                relation_map.setdefault(key, set()).update(
                    str(item).strip() for item in draft.get("related") or [] if str(item).strip()
                )
        for source_key, related_titles in list(relation_map.items()):
            source_title = title_by_key[source_key]
            for related_title in list(related_titles):
                target_key = _canonical_title(related_title)
                if target_key in title_by_key:
                    relation_map.setdefault(target_key, set()).add(source_title)

        changes = []
        for draft in drafts:
            title = str(draft.get("title") or "").strip()
            page_type = str(draft.get("page_type") or "wiki_concept")
            key = _canonical_title(title)
            if not key or page_type not in {
                "wiki_source", "wiki_entity", "wiki_concept", "wiki_analysis", "wiki_question",
            }:
                continue
            matches = existing.get(f"{page_type}:{key}", [])
            if matches and any(item.get("generated_by") != GENERATED_BY for item in matches):
                kind = "conflict"
            elif len(matches) > 1:
                kind = "merge"
            elif matches:
                kind = "update"
            else:
                kind = "add"
            related = sorted(relation_map.get(key, set()), key=str.casefold)
            content, source_refs = self._render_page(draft, source_lookup, related)
            if not content or not source_refs:
                kind = "skip"
            directory = {
                "wiki_source": self.config.source_dir,
                "wiki_entity": self.config.entity_dir,
                "wiki_concept": self.config.concept_dir,
                "wiki_analysis": self.config.analysis_dir,
                "wiki_question": self.config.question_dir,
            }[page_type]
            if matches:
                target = matches[0]["relative_path"]
            elif page_type == "wiki_source":
                target = f"{directory}/{datetime.now().strftime('%Y-%m-%d')}_{_safe_filename(title)}.md"
            elif page_type == "wiki_analysis" and not title.startswith("分析_"):
                target = f"{directory}/分析_{_safe_filename(title)}.md"
            elif page_type == "wiki_question" and not title.startswith(("问题_", "发现_")):
                target = f"{directory}/问题_{_safe_filename(title)}.md"
            else:
                target = f"{directory}/{_safe_filename(title)}.md"
            changes.append({
                "change_id": uuid.uuid4().hex,
                "kind": kind,
                "title": title,
                "page_type": page_type,
                "summary": str(draft.get("summary") or "").strip(),
                "tags": [str(item) for item in draft.get("tags") or [] if str(item).strip()],
                "related": related,
                "source_refs": source_refs,
                "source_count": len(source_refs),
                "target": target,
                "content": content,
                "merge_paths": [item["relative_path"] for item in matches[1:]],
                "base_revision": int(matches[0].get("content_revision") or 1) if matches else None,
            })

        plan_id = uuid.uuid4().hex
        plan = {
            "plan_id": plan_id,
            "status": "planned",
            "action": action,
            "instruction": instruction.strip(),
            "created_at": _now(),
            "scope": {
                "document_ids": [item["document_id"] for item in documents],
                "documents": [item.get("title") or item.get("source") for item in documents],
            },
            "summary": {
                kind: sum(1 for item in changes if item["kind"] == kind)
                for kind in ("add", "update", "merge", "conflict", "skip")
            },
            "changes": changes,
        }
        _atomic_json(self._plan_path(plan_id), plan)
        return plan

    def create_plan(self, documents: list[dict], action: str = "generate", instruction: str = "") -> dict:
        task_id = self.tasks.start("plan", {
            "action": action,
            "instruction": instruction.strip(),
            "document_ids": [item.get("document_id") for item in documents],
        })
        try:
            plan = self._create_plan(documents, action=action, instruction=instruction)
        except Exception as exc:
            self.tasks.update(
                task_id,
                status="failed",
                error=str(exc),
                retryable=True,
            )
            raise
        plan["task_id"] = task_id
        _atomic_json(self._plan_path(plan["plan_id"]), plan)
        self.tasks.update(
            task_id,
            status="completed",
            plan_id=plan["plan_id"],
            retryable=False,
        )
        return plan

    def create_migration_plan(self) -> dict:
        """Preview a metadata-only upgrade of legacy Wiki pages."""
        wiki_dir = os.path.join(self.vault_path, self.config.wiki_dir)
        required = {
            "type", "title", "summary", "schema_version", "generated_by", "created",
            "updated", "sources", "source_refs", "status", "indexable",
        }
        candidates: list[tuple[str, str]] = []
        if os.path.isdir(wiki_dir):
            for root, dirs, files in os.walk(wiki_dir):
                dirs[:] = [name for name in dirs if name != self.config.template_dir]
                for filename in files:
                    if not filename.endswith(".md") or filename in {"index.md", "log.md"}:
                        continue
                    path = os.path.join(root, filename)
                    candidates.append((path, os.path.relpath(path, wiki_dir).replace("\\", "/")))

        changes = []
        directory_types = {
            self.config.source_dir: "wiki_source",
            self.config.entity_dir: "wiki_entity",
            self.config.concept_dir: "wiki_concept",
            self.config.analysis_dir: "wiki_analysis",
            self.config.question_dir: "wiki_question",
        }
        for path, relative in candidates:
            metadata, body = _read_frontmatter(path)
            first_dir = relative.split("/", 1)[0]
            page_type = str(metadata.get("type") or directory_types.get(first_dir) or "wiki_concept")
            title = str(metadata.get("title") or os.path.splitext(os.path.basename(path))[0])
            missing = sorted(required - set(metadata))
            if not missing and metadata.get("schema_version") == 1:
                continue
            changes.append({
                "change_id": uuid.uuid4().hex,
                "kind": "update",
                "title": title,
                "page_type": page_type if page_type in {
                    "wiki_source", "wiki_entity", "wiki_concept", "wiki_analysis", "wiki_question",
                } else "wiki_concept",
                "target": relative,
                "content": body,
                "metadata": metadata,
                "missing_fields": missing,
            })

        plan_id = uuid.uuid4().hex
        plan = {
            "plan_id": plan_id,
            "status": "planned",
            "action": "migrate",
            "instruction": "Mechanically upgrade Wiki metadata without moving or rewriting page bodies.",
            "created_at": _now(),
            "scope": {"document_ids": [], "documents": [item["target"] for item in changes]},
            "summary": {
                "add": 0, "update": len(changes), "merge": 0, "conflict": 0, "skip": 0,
            },
            "changes": changes,
        }
        _atomic_json(self._plan_path(plan_id), plan)
        return plan

    def get_plan(self, plan_id: str) -> dict:
        path = self._plan_path(plan_id)
        if not os.path.exists(path):
            raise FileNotFoundError("Wiki plan not found")
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _create_checkpoint(self, plan_id: str) -> str:
        checkpoint_id = uuid.uuid4().hex
        root = self._checkpoint_path(checkpoint_id)
        wiki_dir = os.path.join(self.vault_path, self.config.wiki_dir)
        os.makedirs(root, exist_ok=True)
        existed = os.path.isdir(wiki_dir)
        if existed:
            shutil.copytree(wiki_dir, os.path.join(root, "wiki"))
        _atomic_json(os.path.join(root, "checkpoint.json"), {
            "checkpoint_id": checkpoint_id,
            "plan_id": plan_id,
            "created_at": _now(),
            "wiki_existed": existed,
        })
        return checkpoint_id

    def _preflight_plan(self, plan: dict) -> None:
        plan.pop("staging", None)
        plan.pop("last_error", None)
        allowed_document_ids = set(plan.get("scope", {}).get("document_ids") or [])
        require_sources = plan.get("action") != "migrate"
        staged = []
        for change in plan.get("changes", []):
            if change.get("kind") not in {"add", "update", "merge"}:
                continue
            errors = validate_change(
                change,
                allowed_document_ids,
                require_sources=require_sources,
            )
            if errors:
                staged.append({
                    "change_id": change.get("change_id"),
                    "path": stage_change(self.workspace, plan["plan_id"], change, errors),
                    "errors": errors,
                })
        if not staged:
            return
        plan["staging"] = staged
        plan["last_error"] = "Wiki plan validation failed before writing files"
        _atomic_json(self._plan_path(plan["plan_id"]), plan)
        raise ValueError(plan["last_error"])

    def _write_plan_changes(self, plan: dict) -> list[str]:
        written_pages = []
        written_paths = []
        wiki_dir = os.path.join(self.vault_path, self.config.wiki_dir)
        for change in plan.get("changes", []):
            if change.get("kind") not in {"add", "update", "merge"}:
                continue
            target = os.path.abspath(os.path.join(wiki_dir, change["target"]))
            if os.path.commonpath([target, wiki_dir]) != os.path.abspath(wiki_dir):
                raise ValueError("Wiki plan target escaped the Wiki directory")
            existing_paths = [target]
            for relative in change.get("merge_paths") or []:
                duplicate = os.path.abspath(os.path.join(wiki_dir, relative))
                if duplicate != target and os.path.commonpath([duplicate, wiki_dir]) == os.path.abspath(wiki_dir):
                    existing_paths.append(duplicate)
            prepared = dict(change)
            prepared["source_hash"] = str(change.get("source_hash") or "") or hashlib.sha256(
                json.dumps(change.get("source_refs") or [], sort_keys=True).encode("utf-8")
            ).hexdigest()[:16]
            try:
                page = merge_page(prepared, existing_paths)
            except ValueError as exc:
                errors = [str(exc)]
                staged_item = {
                    "change_id": change.get("change_id"),
                    "path": stage_change(self.workspace, plan["plan_id"], change, errors),
                    "errors": errors,
                }
                plan["staging"] = [staged_item]
                plan["last_error"] = str(exc)
                _atomic_json(self._plan_path(plan["plan_id"]), plan)
                raise
            atomic_text(target, page.to_markdown())
            for duplicate in existing_paths[1:]:
                if os.path.isfile(duplicate):
                    os.remove(duplicate)
            written_pages.append(page)
            written_paths.append(change["target"])

        if written_pages:
            indexer = WikiIndexer(self.vault_path, self.config)
            indexer.rebuild_from_disk()
            result = CompileResult(pages=written_pages)
            result.entities_count = sum(page.page_type == "wiki_entity" for page in written_pages)
            result.concepts_count = sum(page.page_type == "wiki_concept" for page in written_pages)
            result.sources_count = sum(page.page_type == "wiki_source" for page in written_pages)
            indexer.append_log("confirmed-plan", plan["plan_id"], result)
        return written_paths

    def _write_migration_changes(self, plan: dict) -> list[str]:
        wiki_dir = os.path.abspath(os.path.join(self.vault_path, self.config.wiki_dir))
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        written = []
        for change in plan.get("changes") or []:
            target = os.path.abspath(os.path.join(wiki_dir, change["target"]))
            if os.path.commonpath([target, wiki_dir]) != wiki_dir or not os.path.isfile(target):
                raise ValueError("Wiki migration target is invalid")
            metadata = dict(change.get("metadata") or {})
            metadata.update({
                "type": change["page_type"],
                "title": change["title"],
                "summary": str(metadata.get("summary") or ""),
                "schema_version": 1,
                "generated_by": metadata.get("generated_by") or "user",
                "created": metadata.get("created") or today,
                "updated": today,
                "sources": metadata.get("sources") or [],
                "source_refs": metadata.get("source_refs") or [],
                "status": metadata.get("status") or "active",
                "indexable": bool(metadata.get("indexable", True)),
            })
            rendered = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
            atomic_text(target, f"---\n{rendered}\n---\n\n{str(change.get('content') or '').strip()}\n")
            written.append(change["target"])
        if written:
            indexer = WikiIndexer(self.vault_path, self.config)
            indexer.rebuild_from_disk()
            indexer.append_log("迁移", plan["plan_id"])
        return written

    def apply_plan(self, plan_id: str) -> dict:
        with WIKI_WRITE_LOCK:
            return self._apply_plan(plan_id)

    def skip_staged_changes(self, plan_id: str) -> dict:
        with WIKI_WRITE_LOCK:
            plan = self.get_plan(plan_id)
            if plan.get("status") != "planned":
                raise ValueError("This Wiki plan can no longer be changed")
            staged_ids = {
                str(item.get("change_id") or "")
                for item in plan.get("staging") or []
                if item.get("change_id")
            }
            if not staged_ids:
                raise ValueError("This Wiki plan has no pages waiting for correction")
            skipped_titles = []
            for change in plan.get("changes") or []:
                if change.get("change_id") in staged_ids and change.get("kind") in {"add", "update", "merge"}:
                    change["kind"] = "skip"
                    change["skip_reason"] = "kept_existing_page"
                    skipped_titles.append(str(change.get("title") or "Wiki page"))
            if not skipped_titles:
                raise ValueError("The pages waiting for correction are no longer part of this plan")
            plan["summary"] = {
                kind: sum(1 for item in plan.get("changes") or [] if item.get("kind") == kind)
                for kind in ("add", "update", "merge", "conflict", "skip", "split")
            }
            plan.pop("staging", None)
            plan.pop("last_error", None)
            plan["recovery"] = {
                "strategy": "keep_existing",
                "resolved_at": _now(),
                "skipped_titles": skipped_titles,
            }
            _atomic_json(self._plan_path(plan_id), plan)
            staging_dir = os.path.join(self.workspace, ".bobodan", "wiki", "staging", plan_id)
            if os.path.isdir(staging_dir):
                shutil.rmtree(staging_dir)
            return plan

    def mark_replaced(self, plan_id: str, replacement_plan_id: str) -> dict:
        with WIKI_WRITE_LOCK:
            plan = self.get_plan(plan_id)
            if plan.get("status") != "planned":
                raise ValueError("This Wiki plan can no longer be replaced")
            plan["status"] = "replaced"
            plan["replaced_at"] = _now()
            plan["replacement_plan_id"] = replacement_plan_id
            _atomic_json(self._plan_path(plan_id), plan)
            return plan

    def cancel_plan(self, plan_id: str) -> dict:
        with WIKI_WRITE_LOCK:
            plan = self.get_plan(plan_id)
            if plan.get("status") != "planned":
                raise ValueError("This Wiki run can no longer be cancelled")
            plan["status"] = "cancelled"
            plan["cancelled_at"] = _now()
            _atomic_json(self._plan_path(plan_id), plan)
            task_id = plan.get("task_id")
            if task_id:
                self.tasks.update(str(task_id), status="cancelled", retryable=False)
            return plan

    def _apply_plan(self, plan_id: str) -> dict:
        plan = self.get_plan(plan_id)
        if plan.get("status") != "planned":
            raise ValueError("This Wiki plan has already been applied or cancelled")
        if not any(change.get("kind") in {"add", "update", "merge"} for change in plan.get("changes", [])):
            raise ValueError("This Wiki plan has no applicable changes")
        task_id = self.tasks.start("apply", {"plan_id": plan_id})
        checkpoint_id = None
        try:
            self._preflight_plan(plan)
            checkpoint_id = self._create_checkpoint(plan_id)
            written_paths = (
                self._write_migration_changes(plan)
                if plan.get("action") == "migrate"
                else self._write_plan_changes(plan)
            )
        except Exception as exc:
            if checkpoint_id:
                self.restore_checkpoint(checkpoint_id)
            self.tasks.update(
                task_id,
                status="failed",
                error=str(exc),
                plan_id=plan_id,
                retryable=True,
            )
            raise

        plan.update({
            "status": "applied",
            "applied_at": _now(),
            "checkpoint_id": checkpoint_id,
            "written": written_paths,
            "task_id": task_id,
        })
        _atomic_json(self._plan_path(plan_id), plan)
        self.tasks.update(
            task_id,
            status="completed",
            plan_id=plan_id,
            checkpoint_id=checkpoint_id,
            retryable=False,
        )
        return plan

    def list_tasks(self) -> list[dict]:
        return self.tasks.list()

    def get_task(self, task_id: str) -> dict:
        return self.tasks.get(task_id)

    def cancel_task(self, task_id: str) -> dict:
        return self.tasks.cancel(task_id)

    def restore_checkpoint(self, checkpoint_id: str) -> dict:
        with WIKI_WRITE_LOCK:
            return self._restore_checkpoint(checkpoint_id)

    def _restore_checkpoint(self, checkpoint_id: str) -> dict:
        root = self._checkpoint_path(checkpoint_id)
        metadata_path = os.path.join(root, "checkpoint.json")
        if not os.path.exists(metadata_path):
            raise FileNotFoundError("Wiki checkpoint not found")
        with open(metadata_path, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
        wiki_dir = os.path.join(self.vault_path, self.config.wiki_dir)
        if os.path.isdir(wiki_dir):
            archive_root = os.path.join(self.workspace, ".bobodan", "archive", "wiki-undo")
            os.makedirs(archive_root, exist_ok=True)
            archive = os.path.join(
                archive_root,
                f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{checkpoint_id[:8]}-{uuid.uuid4().hex[:6]}",
            )
            shutil.copytree(wiki_dir, archive)
            shutil.rmtree(wiki_dir)
        backup = os.path.join(root, "wiki")
        if metadata.get("wiki_existed") and os.path.isdir(backup):
            shutil.copytree(backup, wiki_dir)
        metadata["restored_at"] = _now()
        _atomic_json(metadata_path, metadata)
        return metadata
