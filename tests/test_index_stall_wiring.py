"""W2 G3：向量腿卡住时**停得干净** —— 已完成保留、未完成仍 pending、文本索引照做。

守卫本身是纯函数（见 test_index_stall_guard.py）；这里钉的是**接线**：
一旦判定卡住，后续资料不再逐份硬试，而且这一轮的文本索引不受影响。
"""

from __future__ import annotations

import pytest

from obsidian.sync import sync_sources
from rag.sqlite_store import KBSQLiteStore
from service.library_service import LibraryService


class StallingGuard:
    """第一份资料的向量落库后，就假装已经超过 600 秒没有进度。"""

    def __init__(self, timeout_seconds=None):
        self.timeout_seconds = timeout_seconds
        self._beats = 0
        self.stall_message = ""

    def beat(self) -> None:
        self._beats += 1

    def ensure_progress(self) -> None:
        if self._beats >= 1:
            self.stall_message = "向量索引已 601 秒没有进度（阈值 600 秒）。"
            from rag.index_guard import IndexStalledError

            raise IndexStalledError(self.stall_message)


class FakeEmbedding:
    def __init__(self, *args, **kwargs):
        pass

    def is_available(self) -> bool:
        return True

    def get_model_info(self) -> dict:
        return {"name": "fake", "model": "fake-3", "dim": 3}

    def embed_texts(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


@pytest.fixture
def portable_library(tmp_path):
    root = tmp_path / "library"
    LibraryService(str(tmp_path / "home")).initialize(str(root), name="Portable")
    return root


def test_a_stalled_vector_leg_stops_without_losing_text_indexing(portable_library, monkeypatch):
    from unittest.mock import MagicMock

    monkeypatch.setattr("rag.qdrant_store.QdrantStore", MagicMock())
    monkeypatch.setattr("rag.embedding_service.EmbeddingService", FakeEmbedding)
    monkeypatch.setattr("obsidian.sync.StallGuard", StallingGuard)

    inbox = portable_library / "raw" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "a.md").write_text("# 甲\n\n贪心策略每次选局部最优。", encoding="utf-8")
    (inbox / "b.md").write_text("# 乙\n\n动态规划保存子问题结果。", encoding="utf-8")

    summary = sync_sources(
        workspace=str(portable_library),
        vault_path=str(portable_library),
        course_dir=str(portable_library / "raw"),
        mode="full",
    )

    # 卡住这件事要在汇总里说清楚（可行动），而不是静默。
    assert summary.vector_stall, summary
    assert "秒没有进度" in summary.vector_stall

    store = KBSQLiteStore(str(portable_library))
    store.init_db()
    try:
        documents = store.list_documents()
        statuses = sorted(str(doc.get("vector_status")) for doc in documents)
        chunk_counts = [
            len(store.get_chunks_by_document(str(doc.get("id") or doc.get("document_id") or "")))
            for doc in documents
        ]
    finally:
        store.close()

    # 一份写成 indexed（进度真的推进过），另一份仍是 pending（可重试），**没有**被记成 error。
    assert statuses == ["indexed", "pending"], statuses
    # 文本索引不受影响：两份资料都有 chunk。
    assert all(count > 0 for count in chunk_counts), chunk_counts
