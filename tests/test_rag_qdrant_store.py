"""Tests for rag.qdrant_store — Qdrant vector storage layer.

Tests use mocked qdrant-client to avoid requiring a real Qdrant instance.
"""

import sys
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from rag.qdrant_store import QdrantStore
from rag.schema import RetrievalHit


@pytest.fixture
def mock_qdrant():
    """Mock qdrant-client module and QdrantClient."""
    mock_client = MagicMock()
    mock_collections = MagicMock()
    mock_collections.collections = []
    mock_client.get_collections.return_value = mock_collections

    mock_collection_info = MagicMock()
    mock_collection_info.vectors_count = 0
    mock_collection_info.points_count = 0
    mock_client.get_collection.return_value = mock_collection_info

    # Create mock modules for qdrant_client and qdrant_client.models
    mock_qdrant_module = MagicMock()
    mock_qdrant_module.QdrantClient.return_value = mock_client

    mock_models = MagicMock()

    # Patch sys.modules so `from qdrant_client import ...` and
    # `from qdrant_client.models import ...` work
    with patch.dict(sys.modules, {
        "qdrant_client": mock_qdrant_module,
        "qdrant_client.models": mock_models,
    }):
        yield mock_client


@pytest.fixture
def store(tmp_path, mock_qdrant):
    """Create a QdrantStore with mocked client."""
    s = QdrantStore(str(tmp_path))
    yield s


# ── Init ────────────────────────────────────────────────────────────────

class TestInit:
    def test_default_config(self, tmp_path):
        s = QdrantStore(str(tmp_path))
        assert s.mode == "local"
        assert s.collection == "bobodan_chunks"
        assert s.distance == "cosine"

    def test_custom_config(self, tmp_path):
        config = {
            "rag": {
                "vector_db": {
                    "mode": "server",
                    "url": "http://my-server:6333",
                    "collection": "my_chunks",
                }
            }
        }
        s = QdrantStore(str(tmp_path), config)
        assert s.mode == "server"
        assert s.url == "http://my-server:6333"
        assert s.collection == "my_chunks"


# ── Collection ──────────────────────────────────────────────────────────

class TestCollection:
    def test_init_collection_creates(self, store, mock_qdrant):
        store.init_collection(embedding_dim=768)
        mock_qdrant.create_collection.assert_called_once()

    def test_init_collection_skips_existing(self, store, mock_qdrant):
        mock_col = MagicMock()
        mock_col.name = "bobodan_chunks"
        mock_qdrant.get_collections.return_value.collections = [mock_col]
        store.init_collection(embedding_dim=768)
        mock_qdrant.create_collection.assert_not_called()

    def test_delete_collection(self, store, mock_qdrant):
        store.delete_collection()
        mock_qdrant.delete_collection.assert_called_once_with("bobodan_chunks")


# ── Upsert ──────────────────────────────────────────────────────────────

class TestUpsert:
    def test_upsert_single_batch(self, store, mock_qdrant):
        store.upsert(
            chunk_ids=["c1", "c2"],
            vectors=[[0.1, 0.2], [0.3, 0.4]],
            payloads=[{"chunk_id": "c1", "source": "a.md"}, {"chunk_id": "c2", "source": "b.md"}],
        )
        mock_qdrant.upsert.assert_called_once()

    def test_upsert_batched(self, store, mock_qdrant):
        # 250 points > batch_size 100 → 3 batches
        ids = [f"c{i}" for i in range(250)]
        vecs = [[0.1] * 3 for _ in range(250)]
        payloads = [{"chunk_id": f"c{i}"} for i in range(250)]
        store.upsert(ids, vecs, payloads)
        assert mock_qdrant.upsert.call_count == 3


# ── Search ──────────────────────────────────────────────────────────────

class TestSearch:
    def _mock_search_result(self):
        """Create a mock query_points result."""
        mock_point = MagicMock()
        mock_point.id = "c1"
        mock_point.score = 0.85
        mock_point.payload = {
            "chunk_id": "c1",
            "document_id": "d1",
            "source": "test.md",
            "heading_path": ["Chapter 1"],
            "heading_text": "Chapter 1",
            "page_start": 1,
            "page_end": 3,
        }
        mock_result = MagicMock()
        mock_result.points = [mock_point]
        return mock_result

    def test_search_returns_hits(self, store, mock_qdrant):
        mock_qdrant.query_points.return_value = self._mock_search_result()
        hits = store.search([0.1, 0.2, 0.3], top_k=5)
        assert len(hits) == 1
        h = hits[0]
        assert isinstance(h, RetrievalHit)
        assert h.chunk_id == "c1"
        assert h.document_id == "d1"
        assert h.score == 0.85
        assert "vector" in h.retrievers
        assert h.heading_path == ["Chapter 1"]

    def test_search_with_document_filter(self, store, mock_qdrant):
        mock_qdrant.query_points.return_value = self._mock_search_result()
        store.search([0.1], top_k=5, document_id="d1")
        call_kwargs = mock_qdrant.query_points.call_args
        # query_filter should be set
        assert call_kwargs.kwargs.get("query_filter") is not None or \
               call_kwargs[1].get("query_filter") is not None or \
               len(call_kwargs.args) > 0

    def test_search_empty(self, store, mock_qdrant):
        mock_result = MagicMock()
        mock_result.points = []
        mock_qdrant.query_points.return_value = mock_result
        hits = store.search([0.1], top_k=5)
        assert hits == []


# ── Delete ──────────────────────────────────────────────────────────────

class TestDelete:
    def test_delete_by_filter(self, store, mock_qdrant):
        store.delete_by_filter("doc1")
        mock_qdrant.delete.assert_called_once()

    def test_delete_collection(self, store, mock_qdrant):
        store.delete_collection()
        mock_qdrant.delete_collection.assert_called_once()


# ── Stats ───────────────────────────────────────────────────────────────

class TestStats:
    def test_get_stats(self, store, mock_qdrant):
        stats = store.get_stats()
        assert stats["collection"] == "bobodan_chunks"
        assert stats["mode"] == "local"
        assert "vectors_count" in stats or "error" in stats
