"""⑤（E17）：整理建议的「执行 → 一键撤销」（复用 ③b 的身份迁移）。

设计 §3.5 决定 22 的完整形状：提议 → 预览 → 确认 → **执行** → **一键撤销**。
本块实现后两者：把散落资料收进文件夹时，**资料身份必须保留**（文档 id、chunk
身份、概念证据都跟着走），并且**返回一份可撤销的动作清单**。
"""

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
        workspace=str(library), vault_path=str(library), course_dir=str(library), mode="full"
    )


def test_apply_moves_loose_materials_and_keeps_their_identity(library, monkeypatch):
    (library / "散落的一课.md").write_text("# 散落的一课\n\n内容足够长，能切出一段。", encoding="utf-8")
    _sync(library, monkeypatch)
    service = KBService(str(library))
    before = next(
        item for item in service.list_documents(collection="all")["documents"]
        if item["relative_path"] == "散落的一课.md"
    )

    result = service.apply_organization(["散落的一课.md"], "未归类")

    assert result["ok"], result
    assert (library / "未归类" / "散落的一课.md").is_file()
    assert not (library / "散落的一课.md").exists()

    documents = service.list_documents(collection="all")["documents"]
    moved = next(item for item in documents if item["document_id"] == before["document_id"])
    assert moved["relative_path"] == "未归类/散落的一课.md", "身份必须保留（不是当成新资料重建）"

    assert result["moved"] == [{
        "document_id": before["document_id"],
        "from": "散落的一课.md",
        "to": "未归类/散落的一课.md",
    }], result["moved"]


def test_undo_puts_everything_back(library, monkeypatch):
    (library / "散落的一课.md").write_text("# 散落的一课\n\n内容足够长，能切出一段。", encoding="utf-8")
    _sync(library, monkeypatch)
    service = KBService(str(library))
    document_id = next(
        item["document_id"] for item in service.list_documents(collection="all")["documents"]
        if item["relative_path"] == "散落的一课.md"
    )

    applied = service.apply_organization(["散落的一课.md"], "未归类")
    assert applied["ok"], applied

    undone = service.undo_organization(applied["moved"])

    assert undone["ok"], undone
    assert (library / "散落的一课.md").is_file(), "撤销必须放回原位"
    assert not (library / "未归类" / "散落的一课.md").exists()
    documents = service.list_documents(collection="all")["documents"]
    restored = next((item for item in documents if item["document_id"] == document_id), None)
    assert restored is not None and restored["relative_path"] == "散落的一课.md"
