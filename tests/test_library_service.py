from __future__ import annotations

import json
import os
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
    # 2026-09-24（E17 ①，用户已确认）：wiki 停用 —— 生成页不再是资料，
    # 磁盘文件保留，但不再进入索引与检索。
    assert "wiki/concepts/RAG.md" not in scanned
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
    # 2026-08-12: the library root itself is the scan root; raw/ is covered
    # as its subdirectory, so the registered roots are [root, course-materials].
    assert course_dirs == [str(moved.resolve()), str((moved / "course-materials").resolve())]


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


# ── 2026-08-12: default library folder ─────────────────────────────────

def test_default_library_path_windows_documents(monkeypatch):
    from service.library_service import LibraryService

    monkeypatch.setattr("os.name", "nt")
    monkeypatch.setenv("USERPROFILE", "C:/users/test")
    path = LibraryService().default_library_path()
    assert path.replace("\\", "/") == "C:/users/test/Documents/Bobodan 资料库"


def test_default_library_path_appends_number_when_exists(tmp_path, monkeypatch):
    from service.library_service import LibraryService

    monkeypatch.setattr("os.name", "nt")
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    first = LibraryService().default_library_path()
    os.makedirs(first)
    second = LibraryService().default_library_path()
    assert second.endswith("Bobodan 资料库 2")


def test_defaults_tell_the_frontend_exactly_what_create_will_make(tmp_path, monkeypatch):
    """W1 E2：默认值只能有**一个**来源。

    旧实现前端硬编码 «~/Documents/Bobodan»，后端是 «~/Documents/Bobodan 资料库» ——
    用户看到的预填路径与真正创建的根目录不是同一个地方。
    """
    service = LibraryService(str(tmp_path / "home"))
    monkeypatch.setattr(
        service, "default_library_path",
        lambda: str(tmp_path / "Documents" / "Bobodan 资料库"),
    )

    defaults = service.default_library_defaults()

    assert defaults["name"] == "Bobodan 资料库", defaults
    assert Path(defaults["parent_path"]) == tmp_path / "Documents", defaults
    assert Path(defaults["root_path"]) == tmp_path / "Documents" / "Bobodan 资料库", defaults

    # 预填所见即所得：按这份默认值创建，真正落地的根目录必须就是 root_path。
    created = service.create(defaults["name"], defaults["parent_path"])
    registered = service.resolve(created["library_id"])
    assert Path(registered["path"]) == Path(defaults["root_path"]), (registered, defaults)


def test_root_preview_uses_the_same_rule_as_create(tmp_path):
    """预览与创建必须走**同一个** helper，否则两套规则迟早再分叉。"""
    service = LibraryService(str(tmp_path / "home"))

    preview = service.preview_root("我的 资料库/带斜杠", str(tmp_path / "parent"))
    created = service.create("我的 资料库/带斜杠", str(tmp_path / "parent"))
    registered = service.resolve(created["library_id"])

    assert preview == registered["path"], (preview, registered)


def test_create_on_a_non_empty_folder_explains_itself_in_chinese(tmp_path):
    """W1 E2：这条 409 的文案曾经是英文的，界面上会直接显示英文句子。"""
    service = LibraryService(str(tmp_path / "home"))
    target = tmp_path / "parent" / "占用了"
    target.mkdir(parents=True)
    (target / "已有文件.md").write_text("x", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        service.create("占用了", str(tmp_path / "parent"))

    message = str(excinfo.value)
    assert "已存在" in message and "不是空" in message, message
    assert "already exists" not in message, message
