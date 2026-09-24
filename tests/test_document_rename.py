"""③（E17）：重命名/移动资料时**保留身份并迁移引用**。

实测枚举（本轮跑的，不是猜的）——引用 document_id 或 chunk_id 的地方：
- `documents`（id / source / path）与 `chunks`（document_id / **chunk_id / source**）；
- 概念证据 `concept_graph.db::evidence`（document_id / chunk_id）；
- 笔记关联 `personal_knowledge.references`（JSON 里的 document_id / chunk_id）；
- 阅读进度 `reading_progress.document_id`；
- Qdrant 向量 payload（document_id / source，point id = chunk_id）。

关键事实：`rag/sqlite_store.py:23` 的 `_stable_hash(source)` 同时给 document_id 与
chunk_id 派生身份，而 `chunk_id = f(source, index, text)` —— 所以**改个文件名会让
所有 chunk id 变化**，挂在它们上面的证据与引用会一起断掉。
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


def _seed(library, monkeypatch):
    pack = library / "course-pack"
    pack.mkdir()
    (pack / "第一课.md").write_text("# 第一课\n\n内容足够长，能切出一段。", encoding="utf-8")
    _sync(library, monkeypatch)
    service = KBService(str(library))
    document = next(
        item for item in service.list_documents(collection="all")["documents"]
        if item["relative_path"] == "course-pack/第一课.md"
    )
    return service, document


def test_rename_keeps_the_document_identity(library, monkeypatch):
    service, document = _seed(library, monkeypatch)
    old_chunk = service.get_document(document["document_id"])["sections"][0]["chunk_id"]

    result = service.move_document(document["document_id"], "course-pack/第二课.md")

    assert result["ok"], result
    assert result["migration"]["document_id"] == document["document_id"], "身份必须保留"
    assert result["migration"]["chunks_remapped"] >= 1
    assert (library / "course-pack" / "第二课.md").exists()
    assert not (library / "course-pack" / "第一课.md").exists()

    documents = service.list_documents(collection="all")["documents"]
    moved = next(item for item in documents if item["document_id"] == document["document_id"])
    assert moved["relative_path"] == "course-pack/第二课.md"

    sections = service.get_document(document["document_id"])["sections"]
    new_ids = {section["chunk_id"] for section in sections}
    assert new_ids and old_chunk not in new_ids, "chunk 身份必须跟着文件走"


def test_rename_migrates_concept_evidence_and_note_references(library, monkeypatch):
    from graph.concept_store import ConceptStore
    from memory.personal_store import PersonalKnowledgeStore

    service, document = _seed(library, monkeypatch)
    chunk_id = service.get_document(document["document_id"])["sections"][0]["chunk_id"]

    from knowledge.paths import knowledge_dir

    concept_db = os.path.join(knowledge_dir(str(library)), "concept_graph.db")
    concepts = ConceptStore(concept_db)
    # 这里只验证「迁移」这一步，所以直接插一条证据（关外键，绕开"先有关系"的前置）。
    import sqlite3

    raw = sqlite3.connect(concept_db)
    raw.execute("PRAGMA foreign_keys=OFF")
    raw.execute(
        "INSERT INTO evidence (evidence_id, rel_id, document_id, chunk_id, document_title,"
        " excerpt, location_type, location_value, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        ("e-test", "rel-1", document["document_id"], chunk_id, "第一课", "", "", "", 0.0),
    )
    raw.commit()
    raw.close()
    memory = PersonalKnowledgeStore(str(library))
    memory.create_item(
        scope="library",
        kind="course_insight",
        title="我的笔记",
        content="引用了第一课",
        references=[{"document_id": document["document_id"], "chunk_id": chunk_id, "title": "第一课"}],
    )
    memory.update_reading_progress(document["document_id"], 40, opened=True)

    result = service.move_document(document["document_id"], "course-pack/第二课.md")
    assert result["ok"], result
    assert result["migration"]["evidence_remapped"] == 1
    assert result["migration"]["references_remapped"] == 1

    evidence = concepts.evidence_for_relationship("rel-1")
    assert evidence[0]["chunk_id"] != chunk_id, "证据必须指向新的 chunk"
    new_ids = {section["chunk_id"] for section in service.get_document(document["document_id"])["sections"]}
    assert evidence[0]["chunk_id"] in new_ids

    notes = memory.list_items(scope="library")
    note = next(item for item in notes if item["title"] == "我的笔记")
    assert note["references"][0]["chunk_id"] in new_ids
    assert note["references"][0]["document_id"] == document["document_id"]

    with memory._conn("library") as conn:
        row = conn.execute(
            "SELECT progress FROM reading_progress WHERE document_id = ?",
            (document["document_id"],),
        ).fetchone()
    assert row and row["progress"] == 40, "阅读进度挂在 document_id 上，必须还在"


def test_rename_refuses_collisions_and_escapes(library, monkeypatch):
    service, document = _seed(library, monkeypatch)
    (library / "course-pack" / "已存在.md").write_text("# 已存在", encoding="utf-8")

    clash = service.move_document(document["document_id"], "course-pack/已存在.md")
    assert not clash["ok"] and clash["code"] == "target_exists"
    assert (library / "course-pack" / "第一课.md").exists(), "失败时不能动文件"

    escape = service.move_document(document["document_id"], "../外面.md")
    assert not escape["ok"] and escape["code"] == "invalid_target"
    assert (library / "course-pack" / "第一课.md").exists()

    bad_type = service.move_document(document["document_id"], "course-pack/换格式.exe")
    assert not bad_type["ok"] and bad_type["code"] == "unsupported_file_type"
