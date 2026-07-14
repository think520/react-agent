"""Corpus-aware Wiki discovery, coverage, and multi-stage planning."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

from .compiler import _parse_llm_json, _safe_filename
from .reliability import PROCESS_RUNNER_ID, atomic_json
from .schema import GENERATED_BY
from .workflow import WikiWorkflow, _canonical_title, _read_frontmatter, _now


BATCH_SIZE = 5
DISCOVERY_WINDOW_CHARS = 24000
EVIDENCE_WINDOW_CHARS = 16000
MAX_KNOWLEDGE_PAGES_PER_BATCH = 12
MAX_PAGE_BODY_CHARS = 4500
MAX_PAGE_SECTIONS = 7
RUN_LOCK = threading.RLock()


DISCOVERY_PROMPT = """You are discovering small, linked Wiki pages from local learning materials.
Return JSON only. Do not write page bodies and do not invent source identifiers.

User topic: {topic}
User instruction: {instruction}

Source excerpts:
{source_excerpts}

Return:
{{"pages":[{{"title":"canonical title","page_type":"wiki_concept, wiki_entity, wiki_analysis, or wiki_question","summary":"one sentence","tags":["tag"],"related":["title"],"source_ids":["S1"]}}]}}

Rules:
- Every candidate must cite supplied source_ids.
- One candidate represents one canonical subject.
- Prefer reusable concept and entity pages over a large topic article.
- Return no more than 12 candidates for this evidence window.
"""


PAGE_PROMPT = """Write one focused Chinese Wiki page from supplied evidence.
Return JSON only and do not invent source identifiers.

Title: {title}
Page type: {page_type}
Candidate summary: {summary}
User instruction: {instruction}
Existing page excerpt: {existing_page}

Evidence:
{evidence}

Return:
{{"pages":[{{"title":"{title}","page_type":"{page_type}","summary":"one paragraph","body":"Markdown without a top-level heading","tags":["tag"],"related":["title"],"claims":[{{"text":"claim","source_ids":["S1"]}}]}}]}}

Rules:
- Keep one canonical subject per page.
- Use at most 6 second-level sections and keep the body concise.
- Important claims require supplied source_ids.
- Preserve useful facts from the existing page when updating it.
- Prefer links to related pages over embedding unrelated subtopics.
{repair_instruction}
"""


def document_fingerprint(document: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(str(document.get("document_id") or "").encode("utf-8"))
    for section in document.get("sections") or []:
        digest.update(str(section.get("chunk_id") or "").encode("utf-8"))
        digest.update(str(section.get("text") or "").strip().encode("utf-8"))
    return digest.hexdigest()[:16]


def wiki_coverage(vault_path: str, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    workflow = WikiWorkflow(vault_path, vault_path)
    wiki_dir = os.path.join(vault_path, workflow.config.wiki_dir)
    document_ids = {str(item.get("document_id") or "") for item in documents}
    aliases: dict[str, set[str]] = defaultdict(set)
    for document in documents:
        document_id = str(document.get("document_id") or "")
        for value in (
            document.get("title"),
            os.path.basename(str(document.get("source") or "")),
            os.path.splitext(os.path.basename(str(document.get("source") or "")))[0],
        ):
            key = _canonical_title(str(value or ""))
            if key:
                aliases[key].add(document_id)

    def resolve_document_id(ref: dict[str, Any]) -> str | None:
        referenced_id = str(ref.get("document_id") or "")
        if referenced_id in document_ids:
            return referenced_id
        for value in (
            ref.get("title"),
            os.path.basename(str(ref.get("source") or "")),
            os.path.splitext(os.path.basename(str(ref.get("source") or "")))[0],
        ):
            matches = aliases.get(_canonical_title(str(value or "")), set())
            if len(matches) == 1:
                return next(iter(matches))
        return None

    pages_by_document: dict[str, set[str]] = defaultdict(set)
    source_pages: dict[str, dict[str, Any]] = {}
    if os.path.isdir(wiki_dir):
        for page_dir in workflow.config.page_dirs():
            root = os.path.join(wiki_dir, page_dir)
            if not os.path.isdir(root):
                continue
            for filename in os.listdir(root):
                if not filename.lower().endswith(".md"):
                    continue
                path = os.path.join(root, filename)
                metadata, _body = _read_frontmatter(path)
                relative = os.path.relpath(path, wiki_dir).replace("\\", "/")
                for ref in metadata.get("source_refs") or []:
                    if not isinstance(ref, dict) or not ref.get("document_id"):
                        continue
                    document_id = resolve_document_id(ref)
                    if not document_id:
                        continue
                    pages_by_document[document_id].add(relative)
                    if metadata.get("type") == "wiki_source":
                        source_pages[document_id] = {
                            "page": relative,
                            "source_hash": str(metadata.get("source_hash") or ""),
                            "updated": metadata.get("updated"),
                        }

    coverage = []
    for document in documents:
        document_id = str(document.get("document_id") or "")
        fingerprint = document_fingerprint(document)
        linked = sorted(pages_by_document.get(document_id, set()))
        source_page = source_pages.get(document_id)
        if source_page and source_page["source_hash"] == fingerprint:
            status = "covered"
        elif source_page and source_page["source_hash"]:
            status = "stale"
        elif source_page or linked:
            status = "partial"
        else:
            status = "uncovered"
        coverage.append({
            "document_id": document_id,
            "status": status,
            "source_page_id": source_page["page"] if source_page else None,
            "linked_page_count": len(linked),
            "source_fingerprint": fingerprint,
            "covered_at": source_page.get("updated") if source_page else None,
        })
    return coverage


class WikiRunStore:
    def __init__(self, workspace: str):
        self.root = os.path.join(os.path.abspath(workspace), ".bobodan", "wiki", "runs")

    def path(self, run_id: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise ValueError("Invalid Wiki run id")
        return os.path.join(self.root, f"{run_id}.json")

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        run = {
            **payload,
            "run_id": payload.get("run_id") or uuid.uuid4().hex,
            "status": "planning",
            "phase": "queued",
            "runner_id": PROCESS_RUNNER_ID,
            "created_at": _now(),
            "updated_at": _now(),
        }
        with RUN_LOCK:
            atomic_json(self.path(run["run_id"]), run)
        return run

    def get(self, run_id: str) -> dict[str, Any]:
        with RUN_LOCK:
            try:
                with open(self.path(run_id), "r", encoding="utf-8") as handle:
                    run = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                raise FileNotFoundError("Wiki run not found") from exc
            if run.get("status") == "planning" and run.get("runner_id") != PROCESS_RUNNER_ID:
                run.update({
                    "status": "failed",
                    "phase": "interrupted",
                    "error": "The previous process stopped before this Wiki run completed.",
                    "retryable": True,
                    "updated_at": _now(),
                })
                atomic_json(self.path(run_id), run)
            return run

    def update(self, run_id: str, **values: Any) -> dict[str, Any]:
        with RUN_LOCK:
            run = self.get(run_id)
            run.update(values)
            run["updated_at"] = _now()
            atomic_json(self.path(run_id), run)
            return run

    def cancel_requested(self, run_id: str) -> bool:
        try:
            return bool(self.get(run_id).get("cancel_requested"))
        except FileNotFoundError:
            return False


class WikiOrchestrator:
    """Plan a corpus Wiki in fair batches while preserving the legacy plan format."""

    def __init__(self, workspace: str, vault_path: str, llm_provider):
        self.workspace = os.path.abspath(workspace)
        self.vault_path = os.path.abspath(vault_path)
        self.llm = llm_provider
        self.workflow = WikiWorkflow(self.workspace, self.vault_path, llm_provider)

    @staticmethod
    def _catalog(documents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        catalog = []
        lookup = {}
        for document in documents:
            for section in document.get("sections") or []:
                text = str(section.get("text") or "").strip()
                if not text:
                    continue
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
                    "text": text,
                }
                catalog.append(ref)
                lookup[source_id] = ref
        if not catalog:
            raise ValueError("The selected materials do not contain readable indexed sections")
        return catalog, lookup

    @staticmethod
    def _prompt_windows(documents: list[dict[str, Any]], lookup: dict[str, dict[str, Any]]) -> list[str]:
        by_document: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for source_id, ref in lookup.items():
            text = ref["text"]
            parts = [text[index:index + 4000] for index in range(0, len(text), 4000)] or [text]
            for part in parts:
                location = ref.get("heading") or (f"page {ref['page']}" if ref.get("page") else "")
                by_document[str(ref["document_id"])].append(
                    (source_id, f"[{source_id}] {ref['title']} {location}\n{part}")
                )
        order = [str(item["document_id"]) for item in documents]
        positions = {document_id: 0 for document_id in order}
        windows = []
        while any(positions[document_id] < len(by_document[document_id]) for document_id in order):
            rendered = []
            used = 0
            progressed = True
            while progressed:
                progressed = False
                for document_id in order:
                    position = positions[document_id]
                    entries = by_document[document_id]
                    if position >= len(entries):
                        continue
                    _source_id, entry = entries[position]
                    if rendered and used + len(entry) > DISCOVERY_WINDOW_CHARS:
                        continue
                    rendered.append(entry)
                    used += len(entry)
                    positions[document_id] += 1
                    progressed = True
            if not rendered:
                break
            windows.append("\n\n".join(rendered))
        return windows

    def _call_pages(self, prompt: str) -> list[dict[str, Any]]:
        response = self.llm.complete([{"role": "user", "content": prompt}])
        parsed = _parse_llm_json(str(getattr(response, "content", "") or ""))
        if not isinstance(parsed, dict) or not isinstance(parsed.get("pages"), list):
            raise ValueError("The model did not return a valid Wiki plan")
        return [item for item in parsed["pages"] if isinstance(item, dict)]

    def _discover_batch(
        self,
        documents: list[dict[str, Any]],
        lookup: dict[str, dict[str, Any]],
        topic: str,
        instruction: str,
    ) -> list[dict[str, Any]]:
        discovered = []
        for excerpts in self._prompt_windows(documents, lookup):
            prompt = DISCOVERY_PROMPT.format(
                topic=topic.strip() or "(whole learning library)",
                instruction=instruction.strip() or "Build a concise, traceable learning Wiki.",
                source_excerpts=excerpts,
            )
            try:
                discovered.extend(self._call_pages(prompt))
            except ValueError:
                discovered.extend(self._call_pages(prompt + "\nThe previous response was invalid. Return the exact JSON shape only."))
        return discovered

    @staticmethod
    def _source_candidates(documents: list[dict[str, Any]], lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        refs_by_document: dict[str, list[str]] = defaultdict(list)
        headings_by_document: dict[str, list[str]] = defaultdict(list)
        for source_id, ref in lookup.items():
            document_id = str(ref["document_id"])
            refs_by_document[document_id].append(source_id)
            heading = str(ref.get("heading") or "").strip()
            if heading and heading not in headings_by_document[document_id]:
                headings_by_document[document_id].append(heading)
        base_titles = [str(document.get("title") or document.get("source") or "资料摘要") for document in documents]
        title_counts = {title: base_titles.count(title) for title in set(base_titles)}
        used_titles: set[str] = set()
        result = []
        for document in documents:
            document_id = str(document["document_id"])
            base_title = str(document.get("title") or document.get("source") or "资料摘要")
            title = base_title
            if title_counts[base_title] > 1:
                qualifier = str(document.get("course") or os.path.basename(str(document.get("source") or "")) or document_id[:8])
                title = f"{base_title}（{qualifier}）"
            if title in used_titles:
                title = f"{title} · {document_id[:8]}"
            used_titles.add(title)
            result.append({
                "candidate_key": f"wiki_source:{document_id}",
                "title": title,
                "page_type": "wiki_source",
                "summary": f"原始资料《{title}》的可追溯摘要。",
                "tags": ["资料摘要"],
                "related": [],
                "source_ids": refs_by_document[document_id],
                "headings": headings_by_document[document_id],
                "document_id": document_id,
            })
        return result

    @staticmethod
    def _merge_candidates(candidates: list[dict[str, Any]], lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            page_type = str(candidate.get("page_type") or "")
            title = str(candidate.get("title") or "").strip()
            if page_type not in {"wiki_source", "wiki_entity", "wiki_concept", "wiki_analysis", "wiki_question"} or not title:
                continue
            key = str(candidate.get("candidate_key") or f"{page_type}:{_canonical_title(title)}")
            source_ids = [
                str(item) for item in candidate.get("source_ids") or []
                if str(item) in lookup
            ]
            if not source_ids:
                continue
            current = merged.get(key)
            if current is None:
                merged[key] = {
                    **candidate,
                    "source_ids": list(dict.fromkeys(source_ids)),
                    "tags": list(dict.fromkeys(str(item) for item in candidate.get("tags") or [] if str(item).strip())),
                    "related": list(dict.fromkeys(str(item) for item in candidate.get("related") or [] if str(item).strip())),
                }
                continue
            current["source_ids"] = list(dict.fromkeys([*current["source_ids"], *source_ids]))
            current["tags"] = list(dict.fromkeys([*current.get("tags", []), *candidate.get("tags", [])]))
            current["related"] = list(dict.fromkeys([*current.get("related", []), *candidate.get("related", [])]))
            if len(str(candidate.get("summary") or "")) > len(str(current.get("summary") or "")):
                current["summary"] = candidate["summary"]
        return list(merged.values())

    @staticmethod
    def _evidence(candidate: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> str:
        rendered = []
        used = 0
        for source_id in candidate.get("source_ids") or []:
            ref = lookup.get(source_id)
            if not ref:
                continue
            excerpt = str(ref["text"])
            remaining = EVIDENCE_WINDOW_CHARS - used
            if remaining <= 0:
                break
            excerpt = excerpt[:min(1800, remaining)]
            location = ref.get("heading") or (f"page {ref['page']}" if ref.get("page") else "")
            rendered.append(f"[{source_id}] {ref['title']} {location}\n{excerpt}")
            used += len(excerpt)
        return "\n\n".join(rendered)

    @staticmethod
    def _fallback_source_page(candidate: dict[str, Any]) -> dict[str, Any]:
        headings = [str(item) for item in candidate.get("headings") or [] if str(item).strip()]
        body = "本页连接原始资料与后续概念页面，重要事实应回到原文核实。"
        if headings:
            body += "\n\n## 主要内容\n\n" + "\n".join(f"- {item}" for item in headings[:16])
        source_ids = list(candidate.get("source_ids") or [])
        return {
            "title": candidate["title"],
            "page_type": "wiki_source",
            "summary": candidate["summary"],
            "body": body,
            "tags": candidate.get("tags") or ["资料摘要"],
            "related": candidate.get("related") or [],
            "claims": [{
                "text": "本页依据对应原始资料整理。",
                "source_ids": source_ids[: min(3, len(source_ids))],
            }],
        }

    def _draft_candidate(
        self,
        candidate: dict[str, Any],
        lookup: dict[str, dict[str, Any]],
        existing: dict[str, list[dict]],
        instruction: str,
    ) -> dict[str, Any] | None:
        key = f"{candidate['page_type']}:{_canonical_title(candidate['title'])}"
        existing_body = (existing.get(key) or [{}])[0].get("body", "")
        repair = ""
        for attempt in range(2):
            prompt = PAGE_PROMPT.format(
                title=candidate["title"],
                page_type=candidate["page_type"],
                summary=candidate.get("summary") or "",
                instruction=instruction.strip() or "Build a concise, traceable learning Wiki.",
                existing_page=str(existing_body)[:6000] or "(none)",
                evidence=self._evidence(candidate, lookup),
                repair_instruction=repair,
            )
            try:
                pages = self._call_pages(prompt)
            except ValueError:
                pages = []
            if pages:
                draft = pages[0]
                body = str(draft.get("body") or "").strip()
                section_count = len(re.findall(r"^##\s+", body, flags=re.MULTILINE))
                if body and len(body) <= MAX_PAGE_BODY_CHARS and section_count <= MAX_PAGE_SECTIONS:
                    draft["title"] = candidate["title"]
                    draft["page_type"] = candidate["page_type"]
                    return draft
                repair = (
                    "The previous draft was too large. Rewrite it as a small overview page under 3000 characters "
                    "with at most 6 second-level sections; move unrelated subtopics into related page links."
                )
        if candidate["page_type"] == "wiki_source":
            return self._fallback_source_page(candidate)
        return None

    def _render_change(
        self,
        candidate: dict[str, Any],
        draft: dict[str, Any] | None,
        lookup: dict[str, dict[str, Any]],
        existing: dict[str, list[dict]],
    ) -> dict[str, Any]:
        title = candidate["title"]
        page_type = candidate["page_type"]
        key = f"{page_type}:{_canonical_title(title)}"
        matches = existing.get(key, [])
        source_refs = [
            {key: value for key, value in lookup[source_id].items() if key != "text"}
            for source_id in candidate.get("source_ids") or []
            if source_id in lookup
        ]
        if draft is None:
            kind = "split"
            content = ""
            summary = str(candidate.get("summary") or "")
            related = list(candidate.get("related") or [])
            tags = list(candidate.get("tags") or [])
        else:
            summary = str(draft.get("summary") or candidate.get("summary") or "").strip()
            body = str(draft.get("body") or "").strip()
            tags = list(dict.fromkeys(str(item) for item in [*candidate.get("tags", []), *draft.get("tags", [])] if str(item).strip()))
            related = list(dict.fromkeys(str(item) for item in [*candidate.get("related", []), *draft.get("related", [])] if str(item).strip()))
            claims = []
            for claim in draft.get("claims") or []:
                if not isinstance(claim, dict):
                    continue
                ids = [str(item) for item in claim.get("source_ids") or [] if str(item) in lookup]
                text = str(claim.get("text") or "").strip()
                if text and ids:
                    citations = " ".join(f"[{source_id}]({self.workflow._source_link(lookup[source_id])})" for source_id in ids)
                    claims.append(f"- {text} {citations}")
            lines = []
            if summary:
                lines.extend(["## 摘要", "", summary, ""])
            if body:
                lines.extend([body, ""])
            if claims:
                lines.extend(["## 关键结论", "", *claims, ""])
            if related:
                from urllib.parse import quote
                lines.extend(["## 相关概念", "", *[f"- [{item}](/library?collection=wiki&title={quote(item)})" for item in related], ""])
            if source_refs:
                first_by_document: dict[str, dict[str, Any]] = {}
                for ref in source_refs:
                    first_by_document.setdefault(str(ref["document_id"]), ref)
                lines.extend(["## 原始资料", ""])
                for ref in first_by_document.values():
                    lines.append(f"- [{ref['title']}]({self.workflow._source_link(ref)})")
            content = "\n".join(lines).strip()
            if matches and any(item.get("generated_by") != GENERATED_BY for item in matches):
                kind = "conflict"
            elif len(matches) > 1:
                kind = "merge"
            elif matches:
                existing_length = max(int(item.get("body_length") or len(str(item.get("body") or ""))) for item in matches)
                kind = "split" if existing_length > MAX_PAGE_BODY_CHARS and len(content) < int(existing_length * 0.7) else "update"
            else:
                kind = "add"

        directory = {
            "wiki_source": self.workflow.config.source_dir,
            "wiki_entity": self.workflow.config.entity_dir,
            "wiki_concept": self.workflow.config.concept_dir,
            "wiki_analysis": self.workflow.config.analysis_dir,
            "wiki_question": self.workflow.config.question_dir,
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
        source_hash = (
            document_fingerprint({
                "document_id": candidate.get("document_id"),
                "sections": [{"chunk_id": ref.get("chunk_id"), "text": lookup[ref["source_id"]]["text"]} for ref in source_refs],
            })
            if page_type == "wiki_source"
            else hashlib.sha256(json.dumps(source_refs, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        )
        return {
            "change_id": uuid.uuid4().hex,
            "kind": kind,
            "title": title,
            "page_type": page_type,
            "summary": summary,
            "tags": tags,
            "related": related,
            "source_refs": source_refs,
            "source_count": len(source_refs),
            "source_hash": source_hash,
            "target": target,
            "content": content,
            "merge_paths": [item["relative_path"] for item in matches[1:]],
            **({"split_reason": "page_requires_smaller_linked_topics"} if kind == "split" else {}),
        }

    def create_plan(
        self,
        documents: list[dict[str, Any]],
        *,
        scope_mode: str,
        action: str = "generate",
        seed_document_ids: list[str] | None = None,
        topic: str = "",
        instruction: str = "",
        coverage_before: list[dict[str, Any]] | None = None,
        run_id: str | None = None,
        progress=None,
        cancel_check=None,
    ) -> dict[str, Any]:
        if not documents:
            raise ValueError("No learning materials matched this Wiki scope")
        if action not in {"generate", "update"}:
            raise ValueError("Wiki action must be generate or update")
        task_id = self.workflow.tasks.start("orchestrate", {
            "action": action,
            "scope_mode": scope_mode,
            "document_ids": [item["document_id"] for item in documents],
            "topic": topic,
            "instruction": instruction,
        })
        try:
            catalog, lookup = self._catalog(documents)
            existing = self.workflow._existing_pages()
            batches = []
            candidates = []
            for index in range(0, len(documents), BATCH_SIZE):
                if cancel_check and cancel_check():
                    raise RuntimeError("Wiki run cancelled")
                batch = documents[index:index + BATCH_SIZE]
                batch_ids = {str(item["document_id"]) for item in batch}
                batch_lookup = {
                    source_id: ref for source_id, ref in lookup.items()
                    if str(ref["document_id"]) in batch_ids
                }
                self.workflow.tasks.update(task_id, phase="discovering", completed_batches=len(batches), total_batches=(len(documents) + BATCH_SIZE - 1) // BATCH_SIZE)
                if progress:
                    progress(phase="discovering", completed_batches=len(batches), total_batches=(len(documents) + BATCH_SIZE - 1) // BATCH_SIZE)
                discovered = self._discover_batch(batch, batch_lookup, topic, instruction)
                knowledge = self._merge_candidates(discovered, batch_lookup)[:MAX_KNOWLEDGE_PAGES_PER_BATCH]
                candidates.extend(knowledge)
                batches.append({
                    "batch_id": uuid.uuid4().hex,
                    "index": len(batches) + 1,
                    "document_ids": [item["document_id"] for item in batch],
                    "documents": [item.get("title") or item.get("source") for item in batch],
                    "status": "planned",
                })
            candidates = self._merge_candidates([
                *self._source_candidates(documents, lookup),
                *candidates,
            ], lookup)
            changes = []
            for index, candidate in enumerate(candidates):
                if cancel_check and cancel_check():
                    raise RuntimeError("Wiki run cancelled")
                self.workflow.tasks.update(task_id, phase="drafting", completed_pages=index, total_pages=len(candidates))
                if progress:
                    progress(phase="drafting", completed_pages=index, total_pages=len(candidates))
                draft = self._draft_candidate(candidate, lookup, existing, instruction)
                changes.append(self._render_change(candidate, draft, lookup, existing))
            plan_id = run_id or uuid.uuid4().hex
            plan = {
                "plan_id": plan_id,
                "run_id": plan_id,
                "status": "planned",
                "action": action,
                "instruction": instruction.strip(),
                "topic": topic.strip(),
                "created_at": _now(),
                "scope": {
                    "mode": scope_mode,
                    "seed_document_ids": list(seed_document_ids or []),
                    "document_ids": [item["document_id"] for item in documents],
                    "discovered_document_ids": [item["document_id"] for item in documents],
                    "documents": [item.get("title") or item.get("source") for item in documents],
                },
                "batches": batches,
                "coverage_before": coverage_before or [],
                "summary": {
                    kind: sum(1 for item in changes if item["kind"] == kind)
                    for kind in ("add", "update", "merge", "conflict", "skip", "split")
                },
                "changes": changes,
                "task_id": task_id,
            }
            atomic_json(self.workflow._plan_path(plan_id), plan)
            self.workflow.tasks.update(task_id, status="completed", phase="planned", plan_id=plan_id, retryable=False)
            if progress:
                progress(status="planned", phase="planned", plan_id=plan_id)
            return plan
        except Exception as exc:
            cancelled = str(exc) == "Wiki run cancelled"
            self.workflow.tasks.update(
                task_id,
                status="cancelled" if cancelled else "failed",
                error=str(exc),
                retryable=not cancelled,
            )
            if progress:
                progress(
                    status="cancelled" if cancelled else "failed",
                    phase="cancelled" if cancelled else "failed",
                    error=str(exc),
                    retryable=not cancelled,
                )
            raise
