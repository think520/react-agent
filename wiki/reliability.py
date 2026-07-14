"""Validation, staging, safe merging, and task persistence for Wiki writes."""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .schema import PAGE_TYPES, WikiPage


PAGE_TYPE_DIRECTORIES = {
    "wiki_source": "sources",
    "wiki_entity": "entities",
    "wiki_concept": "concepts",
    "wiki_analysis": "analyses",
    "wiki_question": "questions",
}
STRUCTURAL_FILES = {"index.md", "log.md", "source_registry.json", ".wiki_state.json"}
BODY_SHRINK_THRESHOLD = 0.7
PROCESS_RUNNER_ID = uuid.uuid4().hex
TASK_LOCK = threading.RLock()
WIKI_WRITE_LOCK = threading.RLock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def atomic_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(content)
    os.replace(temporary, path)


def read_page(path: str) -> tuple[dict[str, Any], str]:
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()
    if not content.startswith("---"):
        return {}, content.strip()
    end = content.find("---", 3)
    if end < 0:
        return {}, content.strip()
    try:
        metadata = yaml.safe_load(content[3:end]) or {}
    except yaml.YAMLError:
        metadata = {}
    return metadata, content[end + 3:].strip()


def validate_change(
    change: dict[str, Any],
    allowed_document_ids: set[str],
    require_sources: bool = True,
) -> list[str]:
    errors: list[str] = []
    page_type = str(change.get("page_type") or "")
    target = str(change.get("target") or "").replace("\\", "/")
    content = str(change.get("content") or "").strip()
    if page_type not in PAGE_TYPES:
        errors.append("unsupported page type")
    path = PurePosixPath(target)
    if not target or path.is_absolute() or ".." in path.parts or path.suffix.lower() != ".md":
        errors.append("invalid Wiki target path")
    elif page_type in PAGE_TYPE_DIRECTORIES and (
        not path.parts or path.parts[0] != PAGE_TYPE_DIRECTORIES[page_type]
    ):
        errors.append("page type does not match target directory")
    if path.name.lower() in STRUCTURAL_FILES:
        errors.append("application-managed structural files cannot be written by a plan")
    if not str(change.get("title") or "").strip():
        errors.append("page title is required")
    if not content:
        errors.append("page body is required")
    refs = change.get("source_refs") or []
    if require_sources and (not isinstance(refs, list) or not refs):
        errors.append("at least one source reference is required")
    elif refs:
        for ref in refs:
            if not isinstance(ref, dict) or not ref.get("document_id") or not ref.get("source"):
                errors.append("source references must contain document_id and source")
                break
            if allowed_document_ids and str(ref["document_id"]) not in allowed_document_ids:
                errors.append("source reference is outside the confirmed plan scope")
                break
    return errors


def stage_change(workspace: str, plan_id: str, change: dict[str, Any], errors: list[str]) -> str:
    change_id = str(change.get("change_id") or uuid.uuid4().hex)
    relative = f"{plan_id}/{change_id}.json"
    path = os.path.join(workspace, ".bobodan", "wiki", "staging", *relative.split("/"))
    atomic_json(path, {
        "plan_id": plan_id,
        "change_id": change_id,
        "created_at": now(),
        "errors": errors,
        "change": change,
    })
    return relative


def _unique_strings(*values: list[Any]) -> list[str]:
    result: list[str] = []
    for collection in values:
        for value in collection or []:
            text = str(value).strip()
            if text and text not in result:
                result.append(text)
    return result


def _unique_dicts(*values: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for collection in values:
        for value in collection or []:
            if not isinstance(value, dict):
                continue
            key = json.dumps(value, ensure_ascii=False, sort_keys=True)
            if key not in seen:
                seen.add(key)
                result.append(value)
    return result


def _body_without_title(body: str) -> str:
    return re.sub(r"^#\s+[^\n]+\n+", "", body.strip(), count=1).strip()


def merge_page(change: dict[str, Any], existing_paths: list[str]) -> WikiPage:
    metadata_items: list[dict[str, Any]] = []
    existing_bodies: list[str] = []
    for path in existing_paths:
        if not os.path.isfile(path):
            continue
        metadata, body = read_page(path)
        metadata_items.append(metadata)
        existing_bodies.append(_body_without_title(body))

    incoming_body = str(change.get("content") or "").strip()
    incoming_sources = sorted({
        str(item.get("source") or "").strip()
        for item in change.get("source_refs") or []
        if isinstance(item, dict) and item.get("source")
    })
    existing_sources = _unique_strings(*[list(item.get("sources") or []) for item in metadata_items])
    largest_body = max((len(item) for item in existing_bodies), default=0)
    replaces_single_source = bool(
        existing_sources
        and len(existing_sources) == 1
        and set(existing_sources).issubset(set(incoming_sources))
    )
    if (
        largest_body
        and not replaces_single_source
        and len(incoming_body) < int(largest_body * BODY_SHRINK_THRESHOLD)
    ):
        raise ValueError("incoming body is unexpectedly shorter than the existing page")

    primary = metadata_items[0] if metadata_items else {}
    title = str(primary.get("title") or change["title"])
    page_type = str(primary.get("type") or change["page_type"])
    if page_type != change["page_type"]:
        raise ValueError("existing page type does not match the confirmed plan")
    created = str(primary.get("created") or "")
    tags = _unique_strings(
        *[list(item.get("tags") or []) for item in metadata_items],
        list(change.get("tags") or []),
    )
    sources = _unique_strings(existing_sources, incoming_sources)
    source_refs = _unique_dicts(
        *[list(item.get("source_refs") or []) for item in metadata_items],
        list(change.get("source_refs") or []),
    )
    related = _unique_strings(
        *[list(item.get("related") or []) for item in metadata_items],
        list(change.get("related") or []),
    )
    return WikiPage(
        title=title,
        page_type=page_type,
        content=incoming_body,
        tags=tags,
        sources=sources,
        links=related,
        source_refs=source_refs,
        source_hash=str(change.get("source_hash") or ""),
        created=created,
        summary=str(change.get("summary") or primary.get("summary") or ""),
    )


class WikiTaskStore:
    """Persist user-visible Wiki operation state without running a second worker stack."""

    def __init__(self, workspace: str):
        self.path = os.path.join(workspace, ".bobodan", "wiki", "tasks.json")

    def _load(self) -> list[dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                tasks = json.load(handle)
        except (OSError, json.JSONDecodeError):
            tasks = []
        changed = False
        for task in tasks:
            if task.get("status") == "running" and task.get("runner_id") != PROCESS_RUNNER_ID:
                task.update({
                    "status": "failed",
                    "error": "The previous process stopped before this Wiki task completed.",
                    "retryable": True,
                    "updated_at": now(),
                })
                changed = True
        if changed:
            atomic_json(self.path, tasks)
        return tasks

    def list(self) -> list[dict[str, Any]]:
        with TASK_LOCK:
            return self._load()

    def get(self, task_id: str) -> dict[str, Any]:
        with TASK_LOCK:
            for task in self._load():
                if task.get("task_id") == task_id:
                    return task
        raise FileNotFoundError("Wiki task not found")

    def start(self, operation: str, payload: dict[str, Any]) -> str:
        with TASK_LOCK:
            tasks = self._load()
            task_id = uuid.uuid4().hex
            timestamp = now()
            tasks.insert(0, {
                "task_id": task_id,
                "operation": operation,
                "status": "running",
                "payload": payload,
                "attempts": 1,
                "retryable": False,
                "runner_id": PROCESS_RUNNER_ID,
                "created_at": timestamp,
                "updated_at": timestamp,
            })
            atomic_json(self.path, tasks[:100])
        return task_id

    def update(self, task_id: str, **values: Any) -> None:
        with TASK_LOCK:
            tasks = self._load()
            for task in tasks:
                if task.get("task_id") == task_id:
                    task.update(values)
                    task["updated_at"] = now()
                    break
            atomic_json(self.path, tasks)

    def cancel(self, task_id: str) -> dict[str, Any]:
        with TASK_LOCK:
            tasks = self._load()
            for task in tasks:
                if task.get("task_id") != task_id:
                    continue
                if task.get("status") == "running" and task.get("runner_id") == PROCESS_RUNNER_ID:
                    raise ValueError("A running in-process Wiki task cannot be cancelled safely")
                task.update({"status": "cancelled", "retryable": False, "updated_at": now()})
                atomic_json(self.path, tasks)
                return task
        raise FileNotFoundError("Wiki task not found")

    def resolve_plan_failures(self, plan_id: str) -> int:
        with TASK_LOCK:
            tasks = self._load()
            resolved = 0
            for task in tasks:
                if task.get("plan_id") != plan_id or task.get("status") != "failed":
                    continue
                task.update({
                    "status": "cancelled",
                    "retryable": False,
                    "error": "Resolved by a newer Wiki plan action.",
                    "updated_at": now(),
                })
                resolved += 1
            if resolved:
                atomic_json(self.path, tasks)
            return resolved
