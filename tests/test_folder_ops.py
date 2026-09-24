"""③（E17）：树上写操作的后端语义 —— 新建文件夹、删文件夹=只删容器、移动。

设计 §3.5 决定 21：删文件夹**默认只删容器**，里面的资料移回库根并明说后果
（参考项目原话：a container's ⋯ must not be able to destroy work）。
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


def _service(library):
    return KBService(str(library))


def test_create_folder_makes_a_real_directory(library):
    result = _service(library).create_folder("课程包/第一章")
    assert result["ok"], result
    assert (library / "课程包" / "第一章").is_dir()
    assert result["folder"]["path"] == "课程包/第一章"


def test_create_folder_rejects_bad_targets(library):
    service = _service(library)
    (library / "已有").mkdir()
    assert service.create_folder("../外面")["code"] == "invalid_target"
    assert service.create_folder("已有")["code"] == "target_exists"
    assert service.create_folder("wiki/我的")["code"] == "invalid_target"
    assert service.create_folder("")["code"] == "invalid_target"


def test_delete_folder_moves_materials_back_to_the_root(library):
    (library / "课程包" / "第一章").mkdir(parents=True)
    (library / "课程包" / "第一章" / "第一课.md").write_text("# 第一课", encoding="utf-8")
    (library / "课程包" / "封面.png").write_bytes(b"png")

    result = _service(library).delete_folder("课程包")

    assert result["ok"], result
    assert result["moved"] == ["课程包/第一章/第一课.md"]
    assert (library / "第一课.md").is_file(), "资料必须被移回库根，而不是被删掉"
    assert not (library / "课程包" / "第一章").exists()
    # 非资料文件留在原地 → 目录因此保留（不静默丢东西）
    assert (library / "课程包" / "封面.png").is_file()
    assert result["kept_directory"] is True


def test_delete_folder_removes_the_directory_when_it_becomes_empty(library):
    (library / "空壳").mkdir()
    (library / "空壳" / "第一课.md").write_text("# 第一课", encoding="utf-8")

    result = _service(library).delete_folder("空壳")

    assert result["ok"], result
    assert not (library / "空壳").exists()
    assert (library / "第一课.md").is_file()
    assert result["kept_directory"] is False


def test_delete_folder_refuses_the_root_and_internal_dirs(library):
    service = _service(library)
    assert service.delete_folder("")["code"] == "invalid_target"
    assert service.delete_folder(".bobodan")["code"] == "invalid_target"
    assert service.delete_folder("wiki")["code"] == "invalid_target"

def test_delete_folder_ungroup_keeps_identity_and_migrates_references(library, monkeypatch):
    """删除容器时把资料移回库根，必须和 move_document 一样迁移身份。

    审查发现的缺口：delete_folder 原先只是把文件从磁盘搬走，于是资料以新 source
    重新索引 → document_id 变化 → 挂在它上面的概念证据与笔记引用断掉。
    同一个「移动」，两条路径的行为必须一致。
    """
    from unittest.mock import MagicMock

    import sqlite3

    from graph.concept_store import ConceptStore
    from knowledge.paths import knowledge_dir
    from obsidian.sync import sync_sources

    monkeypatch.setattr("rag.qdrant_store.QdrantStore", MagicMock())
    monkeypatch.setattr(
        "rag.embedding_service.EmbeddingService",
        lambda *a, **k: type("Embedding", (), {"is_available": lambda self: False})(),
    )

    (library / "课程包").mkdir()
    (library / "课程包" / "第一课.md").write_text("# 第一课\n\n内容足够长，能切出一段。", encoding="utf-8")
    sync_sources(workspace=str(library), vault_path=str(library), course_dir=str(library), mode="full")

    service = KBService(str(library))
    document = next(
        item for item in service.list_documents(collection="all")["documents"]
        if item["relative_path"] == "课程包/第一课.md"
    )
    chunk_id = service.get_document(document["document_id"])["sections"][0]["chunk_id"]

    concept_db = os.path.join(knowledge_dir(str(library)), "concept_graph.db")
    concepts = ConceptStore(concept_db)
    raw = sqlite3.connect(concept_db)
    raw.execute("PRAGMA foreign_keys=OFF")
    raw.execute(
        "INSERT INTO evidence (evidence_id, rel_id, document_id, chunk_id, document_title,"
        " excerpt, location_type, location_value, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        ("e-folder", "rel-1", document["document_id"], chunk_id, "第一课", "", "", "", 0.0),
    )
    raw.commit()
    raw.close()

    result = service.delete_folder("课程包")

    assert result["ok"], result
    documents = service.list_documents(collection="all")["documents"]
    moved = next((item for item in documents if item["document_id"] == document["document_id"]), None)
    assert moved is not None, "身份必须保留，不能被当成新资料重新索引"
    assert moved["relative_path"] == "第一课.md"

    new_ids = {section["chunk_id"] for section in service.get_document(document["document_id"])["sections"]}
    assert new_ids and chunk_id not in new_ids
    evidence = concepts.evidence_for_relationship("rel-1")
    assert evidence[0]["chunk_id"] in new_ids, "证据必须跟着迁移"
