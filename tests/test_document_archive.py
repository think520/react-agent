"""③（E17）：归档语义扩展到**所有**资料，并给出「已归档」列表与恢复。

设计：`docs/LIBRARY_TREE_DESIGN.md` §3.5（决定 20/21）。
修前行为（`service/kb_service.py:1565`）：只有落在 `raw/`（Bobodan 自己的收件区）
里的文件才能归档，用户自己剪进资料库文件夹的文件会被告知"只读、不能在这里删"。
"""

import os

import pytest

from service.kb_service import KBService
from service.library_service import LibraryService


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    return root


def _sync(library, monkeypatch):
    from unittest.mock import MagicMock

    from obsidian.sync import sync_sources

    monkeypatch.setattr("rag.qdrant_store.QdrantStore", MagicMock())
    monkeypatch.setattr(
        "rag.embedding_service.EmbeddingService",
        lambda *a, **k: type("Embedding", (), {"is_available": lambda self: False})(),
    )
    return sync_sources(
        workspace=str(library),
        vault_path=str(library),
        course_dir=str(library),
        mode="full",
    )


def _documents(library):
    return KBService(str(library)).list_documents(collection="all")["documents"]


def test_archive_moves_any_material_and_records_where_it_went(library, monkeypatch):
    pack = library / "course-pack"
    pack.mkdir()
    (pack / "第一课.md").write_text("# 第一课\n\n内容", encoding="utf-8")
    _sync(library, monkeypatch)
    document = next(item for item in _documents(library) if item["relative_path"] == "course-pack/第一课.md")

    service = KBService(str(library))
    result = service.delete_document(document["document_id"])
    assert result["ok"], result

    # 文件被移到归档区，并且**保留原目录层级**
    assert not (pack / "第一课.md").exists()
    archived = list((library / ".bobodan" / "archive").rglob("course-pack/第一课.md"))
    assert len(archived) == 1, archived

    entries = service.list_archive()["entries"]
    assert len(entries) == 1, entries
    entry = entries[0]
    assert entry["original_path"] == "course-pack/第一课.md"
    assert entry["document_id"] == document["document_id"]
    assert entry["title"]

    # 索引记录走 P0-12 的两次确认通道：这一轮先进「待确认移除」
    assert document["source"] in result["sync"]["pending_removal"]


def test_restore_puts_the_file_back_and_clears_the_entry(library, monkeypatch):
    pack = library / "course-pack"
    pack.mkdir()
    (pack / "第一课.md").write_text("# 第一课\n\n内容", encoding="utf-8")
    _sync(library, monkeypatch)
    document = next(item for item in _documents(library) if item["relative_path"] == "course-pack/第一课.md")

    service = KBService(str(library))
    service.delete_document(document["document_id"])
    entry_id = service.list_archive()["entries"][0]["entry_id"]

    restored = service.restore_archived(entry_id)
    assert restored["ok"], restored
    assert (pack / "第一课.md").read_text(encoding="utf-8") == "# 第一课\n\n内容"
    assert service.list_archive()["entries"] == []
    assert any(item["relative_path"] == "course-pack/第一课.md" for item in _documents(library))


def test_restore_refuses_when_the_original_path_is_occupied(library, monkeypatch):
    pack = library / "course-pack"
    pack.mkdir()
    (pack / "第一课.md").write_text("# 第一课", encoding="utf-8")
    _sync(library, monkeypatch)
    document = next(item for item in _documents(library) if item["relative_path"] == "course-pack/第一课.md")

    service = KBService(str(library))
    service.delete_document(document["document_id"])
    (pack / "第一课.md").write_text("# 我自己又写了一份", encoding="utf-8")

    result = service.restore_archived(service.list_archive()["entries"][0]["entry_id"])
    assert not result["ok"]
    assert result["code"] == "restore_target_exists"
    assert (pack / "第一课.md").read_text(encoding="utf-8") == "# 我自己又写了一份"
    assert len(service.list_archive()["entries"]) == 1, "失败时归档条目必须留着"
    assert list((library / ".bobodan" / "archive").rglob("course-pack/第一课.md")), "归档文件不能被弄丢"


def test_archive_refuses_paths_outside_the_library(library):
    outside = library.parent / "outside.md"
    outside.write_text("# 外部文件", encoding="utf-8")

    service = KBService(str(library))
    result = service.archive_path(str(outside))
    assert not result["ok"]
    assert result["code"] == "document_read_only"
    assert outside.exists()
