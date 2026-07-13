from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from service.kb_service import KBService
from service.library_service import LibraryService


def test_initialize_creates_self_contained_portable_library(tmp_path):
    service = LibraryService(str(tmp_path / "home"))
    root = tmp_path / "libraries" / "Algorithms"

    library = service.initialize(str(root), name="Algorithms")

    descriptor = yaml.safe_load((root / "BOBODAN_LIBRARY.yaml").read_text(encoding="utf-8"))
    assert descriptor["library_id"] == library["library_id"]
    assert descriptor["name"] == "Algorithms"
    assert (root / "WIKI_SCHEMA.md").is_file()
    assert (root / "raw" / "inbox").is_dir()
    assert (root / "wiki" / "templates" / "analysis.md").is_file()
    assert (root / "wiki" / "questions").is_dir()
    assert (root / ".bobodan" / "manifest.json").is_file()
    assert "path" not in library


def test_initialize_is_idempotent_and_registry_can_switch_libraries(tmp_path):
    service = LibraryService(str(tmp_path / "home"))
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = service.initialize(str(first_root), name="First")
    original_schema = (first_root / "WIKI_SCHEMA.md").read_text(encoding="utf-8")
    again = service.initialize(str(first_root), name="Changed")
    second = service.initialize(str(second_root), name="Second")

    assert again["library_id"] == first["library_id"]
    assert (first_root / "WIKI_SCHEMA.md").read_text(encoding="utf-8") == original_schema
    assert service.list_libraries()["active_library_id"] == second["library_id"]
    activated = service.activate(first["library_id"])
    assert activated["active"] is True
    assert service.resolve()["path"] == str(first_root.resolve())


def test_unregister_never_deletes_library_folder(tmp_path):
    service = LibraryService(str(tmp_path / "home"))
    root = tmp_path / "library"
    library = service.initialize(str(root), name="Keep Me")

    assert service.unregister(library["library_id"]) is True
    assert root.is_dir()
    assert (root / "BOBODAN_LIBRARY.yaml").is_file()
    assert service.list_libraries()["libraries"] == []


def test_registry_contains_paths_only_in_user_config(tmp_path):
    service = LibraryService(str(tmp_path / "home"))
    root = tmp_path / "library"
    library = service.initialize(str(root), name="Private Path")

    registry = json.loads(service.registry_path.read_text(encoding="utf-8"))

    assert registry["libraries"][0]["path"] == str(root.resolve())
    assert str(root) not in json.dumps(library)


def test_legacy_folder_preview_and_initialize_registers_course_subfolders(tmp_path):
    from obsidian.vault import scan_vault

    root = tmp_path / "legacy-vault"
    course = root / "course-materials"
    wiki = root / "wiki" / "concepts"
    course.mkdir(parents=True)
    wiki.mkdir(parents=True)
    (root / "note.md").write_text("# Root note", encoding="utf-8")
    (course / "lesson.md").write_text("# Lesson", encoding="utf-8")
    (course / "slides.pdf").write_bytes(b"pdf")
    (wiki / "RAG.md").write_text("# RAG", encoding="utf-8")
    service = LibraryService(str(tmp_path / "home"))

    preview = service.preview_migration(str(root))
    library = service.initialize(str(root), name="Legacy")
    source_roots = json.loads((root / ".bobodan" / "source_roots.json").read_text(encoding="utf-8"))
    scanned = [item.rel_path for item in scan_vault(str(root))]

    assert preview["already_initialized"] is False
    assert preview["material_count"] == 4
    assert preview["wiki_pages"] == 1
    assert preview["legacy_source_count"] == 1
    assert library["name"] == "Legacy"
    assert source_roots["version"] == 2
    assert source_roots["course_dirs"] == ["course-materials"]
    assert "note.md" in scanned
    assert "wiki/concepts/RAG.md" in scanned
    assert "course-materials/lesson.md" not in scanned


def test_moved_library_rewrites_legacy_absolute_source_roots(tmp_path):
    service = LibraryService(str(tmp_path / "home"))
    original = tmp_path / "original" / "library"
    course = original / "course-materials"
    course.mkdir(parents=True)
    (course / "lesson.md").write_text("# Lesson", encoding="utf-8")
    library = service.initialize(str(original), name="Portable")
    source_roots_path = original / ".bobodan" / "source_roots.json"
    source_roots_path.write_text(json.dumps({
        "vault_path": None,
        "course_dirs": [str(course.resolve())],
    }), encoding="utf-8")

    moved = tmp_path / "moved" / "library"
    moved.parent.mkdir()
    shutil.move(str(original), str(moved))
    reopened = service.register(str(moved), activate=True)
    roots = json.loads((moved / ".bobodan" / "source_roots.json").read_text(encoding="utf-8"))
    vault, course_dirs = KBService(str(moved))._registered_roots()

    assert reopened["library_id"] == library["library_id"]
    assert service.resolve()["path"] == str(moved.resolve())
    assert roots["version"] == 2
    assert roots["course_dirs"] == ["course-materials"]
    assert vault == str(moved.resolve())
    assert course_dirs == [str((moved / "raw").resolve()), str((moved / "course-materials").resolve())]


def test_migration_failure_restores_registry_and_active_library(tmp_path, monkeypatch):
    service = LibraryService(str(tmp_path / "home"))
    active = service.initialize(str(tmp_path / "active"), name="Active")
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "lesson.md").write_text("# Lesson", encoding="utf-8")
    registry_before = json.loads(service.registry_path.read_text(encoding="utf-8"))

    def fail_sync(_library_id, config=None):
        del config
        raise ValueError("sync failed")

    monkeypatch.setattr(service, "sync", fail_sync)

    with pytest.raises(ValueError, match="sync failed"):
        service.migrate(str(legacy), name="Legacy")

    registry_after = json.loads(service.registry_path.read_text(encoding="utf-8"))
    assert registry_after == registry_before
    assert service.list_libraries()["active_library_id"] == active["library_id"]
    assert [item["name"] for item in service.list_libraries()["libraries"]] == ["Active"]


def test_migration_activates_library_only_after_sync(tmp_path, monkeypatch):
    service = LibraryService(str(tmp_path / "home"))
    active = service.initialize(str(tmp_path / "active"), name="Active")
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "lesson.md").write_text("# Lesson", encoding="utf-8")
    observed_active_ids = []

    def successful_sync(library_id, config=None):
        del config
        observed_active_ids.append(service.list_libraries()["active_library_id"])
        return {"ok": True, "library_id": library_id}

    monkeypatch.setattr(service, "sync", successful_sync)

    result = service.migrate(str(legacy), name="Legacy")

    assert observed_active_ids == [active["library_id"]]
    assert result["library"]["active"] is True
    assert service.list_libraries()["active_library_id"] == result["library"]["library_id"]
