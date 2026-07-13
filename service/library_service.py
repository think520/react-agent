"""Portable local library registration and initialization."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


LIBRARY_SCHEMA_VERSION = 1
LIBRARY_DESCRIPTOR = "BOBODAN_LIBRARY.yaml"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _safe_folder_name(name: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", name.strip()).strip(" .")
    return value or "Bobodan Library"


WIKI_SCHEMA = """# Bobodan LLM Wiki Schema

This file is the shared source of truth for people and AI models maintaining this library.

## Three layers

1. `raw/` contains original material. AI may read it but must never modify, move, rename, or delete it.
2. `wiki/` contains AI-organized pages. Every write requires an explicit user-confirmed plan.
3. This schema defines the rules. AI may propose changes, but may update it only after confirmation.

## Workflow

- Upload and sync create an original-material index only. They never generate Wiki pages.
- Wiki work follows: summarize sources, confirm focus, create a plan, confirm, write, checkpoint.
- Queries may use Wiki pages for navigation, then return to original material to verify facts.
- Maintenance and migration always produce a preview or repair plan before changing files.

## Page requirements

Valid types: `wiki_source`, `wiki_entity`, `wiki_concept`, `wiki_analysis`, `wiki_question`.

Every page has YAML frontmatter containing: `type`, `title`, `summary`, `schema_version`,
`generated_by`, `created`, `updated`, `sources`, `source_refs`, `status`, and `indexable`.

Use Chinese for prose, preserve specialist terms in their original language on first mention,
and use Obsidian `[[double links]]` for relationships.
"""


RAW_README = """# Original Material

Files under `raw/` are the immutable evidence layer of this Bobodan library.

- Uploads are placed in `raw/inbox/`.
- AI may read and index these files but cannot edit, move, rename, or delete them.
- A user deletion archives the file under `.bobodan/archive/raw/`.
- Uploading or syncing does not automatically generate Wiki content.
"""


TEMPLATES = {
    "source.md": "wiki_source",
    "entity.md": "wiki_entity",
    "concept.md": "wiki_concept",
    "analysis.md": "wiki_analysis",
    "question.md": "wiki_question",
}


class LibraryService:
    """Manage the user-level registry without exposing paths in public summaries."""

    def __init__(self, home: str | None = None):
        configured = home or os.getenv("BOBODAN_HOME")
        self.home = Path(configured).expanduser().resolve() if configured else Path.home() / ".bobodan"
        self.registry_path = self.home / "libraries.json"

    def _load(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"version": 1, "active_library_id": None, "libraries": []}
        try:
            value = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "active_library_id": None, "libraries": []}
        return {
            "version": 1,
            "active_library_id": value.get("active_library_id"),
            "libraries": value.get("libraries") or [],
        }

    def _save(self, registry: dict[str, Any]) -> None:
        _atomic_json(self.registry_path, registry)

    @staticmethod
    def _descriptor(root: Path) -> dict[str, Any]:
        path = root / LIBRARY_DESCRIPTOR
        if not path.is_file():
            raise ValueError("This folder is not a Bobodan library")
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ValueError("The library descriptor is invalid") from exc
        library_id = str(value.get("library_id") or "")
        if not re.fullmatch(r"[0-9a-f-]{36}", library_id):
            raise ValueError("The library descriptor has no valid library ID")
        return value

    @staticmethod
    def _public(record: dict[str, Any], active_id: str | None) -> dict[str, Any]:
        return {
            "library_id": record["library_id"],
            "name": record["name"],
            "created_at": record.get("created_at", ""),
            "last_opened_at": record.get("last_opened_at", ""),
            "active": record["library_id"] == active_id,
            "available": Path(record["path"]).is_dir(),
        }

    def list_libraries(self) -> dict[str, Any]:
        registry = self._load()
        return {
            "active_library_id": registry.get("active_library_id"),
            "libraries": [self._public(item, registry.get("active_library_id")) for item in registry["libraries"]],
        }

    def resolve(self, library_id: str | None = None) -> dict[str, Any] | None:
        registry = self._load()
        selected_id = library_id or registry.get("active_library_id")
        if not selected_id:
            return None
        for record in registry["libraries"]:
            if record.get("library_id") != selected_id:
                continue
            root = Path(record["path"]).resolve()
            descriptor = self._descriptor(root)
            if descriptor.get("library_id") != selected_id:
                raise ValueError("The registered library identity no longer matches its folder")
            return {**record, "path": str(root)}
        raise ValueError("Unknown or unregistered Bobodan library")

    def initialize(self, root: str, name: str | None = None) -> dict[str, Any]:
        path = Path(root).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        descriptor_path = path / LIBRARY_DESCRIPTOR
        if descriptor_path.exists():
            descriptor = self._descriptor(path)
        else:
            descriptor = {
                "schema_version": LIBRARY_SCHEMA_VERSION,
                "library_id": str(uuid.uuid4()),
                "name": (name or path.name).strip() or path.name,
                "created_at": _now(),
            }
            descriptor_path.write_text(
                yaml.safe_dump(descriptor, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

        for relative in (
            "raw/inbox", "raw/assets", "raw/articles", "raw/papers", "raw/books", "raw/misc",
            "wiki/templates", "wiki/sources", "wiki/entities", "wiki/concepts", "wiki/analyses", "wiki/questions",
            ".bobodan/checkpoints", ".bobodan/archive/raw", ".bobodan/archive/wiki",
        ):
            (path / relative).mkdir(parents=True, exist_ok=True)

        schema_path = path / "WIKI_SCHEMA.md"
        if not schema_path.exists():
            schema_path.write_text(WIKI_SCHEMA, encoding="utf-8")
        raw_readme = path / "raw" / "README.md"
        if not raw_readme.exists():
            raw_readme.write_text(RAW_README, encoding="utf-8")
        index_path = path / "wiki" / "index.md"
        if not index_path.exists():
            index_path.write_text("# Wiki Index\n\n", encoding="utf-8")
        log_path = path / "wiki" / "log.md"
        if not log_path.exists():
            log_path.write_text(f"# Wiki Log\n\n## [{_now()}] 初始化 | 创建资料库结构\n\n", encoding="utf-8")
        for filename, page_type in TEMPLATES.items():
            template = path / "wiki" / "templates" / filename
            if not template.exists():
                template.write_text(
                    "---\n"
                    f"type: {page_type}\n"
                    "title: \"\"\nsummary: \"\"\nschema_version: 1\ngenerated_by: bobodan\n"
                    "created: \"\"\nupdated: \"\"\nsources: []\nsource_refs: []\n"
                    "status: draft\nindexable: true\n---\n\n# 页面标题\n",
                    encoding="utf-8",
                )
        manifest = path / ".bobodan" / "manifest.json"
        if not manifest.exists():
            _atomic_json(manifest, {"schema_version": 1, "last_sync": None, "sources": []})
        return self.register(str(path), activate=True)

    def create(self, name: str, parent_path: str) -> dict[str, Any]:
        root = Path(parent_path).expanduser().resolve() / _safe_folder_name(name)
        if root.exists() and any(root.iterdir()) and not (root / LIBRARY_DESCRIPTOR).exists():
            raise ValueError("The target folder already exists and is not empty")
        return self.initialize(str(root), name=name)

    def register(self, root: str, activate: bool = True) -> dict[str, Any]:
        path = Path(root).expanduser().resolve()
        descriptor = self._descriptor(path)
        registry = self._load()
        now = _now()
        record = {
            "library_id": descriptor["library_id"],
            "name": str(descriptor.get("name") or path.name),
            "path": str(path),
            "created_at": str(descriptor.get("created_at") or now),
            "last_opened_at": now,
        }
        registry["libraries"] = [
            item for item in registry["libraries"]
            if item.get("library_id") != record["library_id"] and Path(item.get("path", "")) != path
        ] + [record]
        if activate:
            registry["active_library_id"] = record["library_id"]
        self._save(registry)
        return self._public(record, registry.get("active_library_id"))

    def activate(self, library_id: str) -> dict[str, Any]:
        record = self.resolve(library_id)
        if record is None:
            raise ValueError("Library not found")
        registry = self._load()
        registry["active_library_id"] = library_id
        now = _now()
        for item in registry["libraries"]:
            if item.get("library_id") == library_id:
                item["last_opened_at"] = now
                record = item
                break
        self._save(registry)
        return self._public(record, library_id)

    def unregister(self, library_id: str) -> bool:
        registry = self._load()
        before = len(registry["libraries"])
        registry["libraries"] = [item for item in registry["libraries"] if item.get("library_id") != library_id]
        if len(registry["libraries"]) == before:
            return False
        if registry.get("active_library_id") == library_id:
            registry["active_library_id"] = registry["libraries"][0]["library_id"] if registry["libraries"] else None
        self._save(registry)
        return True

    def sync(self, library_id: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
        from service.kb_service import KBService

        record = self.resolve(library_id)
        if record is None:
            raise ValueError("Library not found")
        result = KBService(record["path"]).sync(record["path"], mode="incremental", config=config or {})
        if not result.get("ok"):
            raise ValueError(result.get("error") or "Library sync failed")
        manifest_path = Path(record["path"]) / ".bobodan" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        manifest["last_sync"] = _now()
        _atomic_json(manifest_path, manifest)
        return result
