from __future__ import annotations

import json
from pathlib import Path

import yaml

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
