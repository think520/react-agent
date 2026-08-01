"""Tests for rag retrievers — RRF, Hybrid, Directory, Grep."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from rag.schema import RetrievalHit, DocumentHit, HybridResult
from rag.rrf import rrf_fuse, dedupe_hits, _find_rank
from rag.hybrid import HybridRetriever
from rag.directory import DirectoryRetriever
from rag.grep_retriever import (
    GrepRetriever, GrepMatch, _is_evidence_thin, _assess_confidence,
    _python_grep, _matches_to_hits,
)
from rag.retriever import (
    _acquire_retrieval_pipeline,
    _release_retrieval_pipeline,
    _retrieval_pipeline,
    clear_retrieval_cache,
)


# ── Helpers ─────────────────────────────────────────────────────────────

def _hit(chunk_id, score, source="test.md", document_id="d1", text="hello",
         retrievers=None, heading_path=None):
    return RetrievalHit(
        chunk_id=chunk_id,
        document_id=document_id,
        source=source,
        text=text,
        score=score,
        retrievers=retrievers or ["vector"],
        heading_path=heading_path or [],
    )


# ── RRF ─────────────────────────────────────────────────────────────────

class TestRRF:
    def test_single_source_preserves_order(self):
        hits = [_hit(f"c{i}", 1.0 - i * 0.1) for i in range(5)]
        result = rrf_fuse(hits, [])
        assert len(result) == 5
        assert result[0].chunk_id == "c0"

    def test_fusion_merges_lists(self):
        vec = [_hit("c1", 0.9), _hit("c2", 0.8), _hit("c3", 0.7)]
        fts = [_hit("c2", 0.95), _hit("c4", 0.85), _hit("c1", 0.75)]
        result = rrf_fuse(vec, fts)
        chunk_ids = [h.chunk_id for h in result]
        # c2 appears in both (rank 2 in vec, rank 1 in fts) — should rank high
        assert "c2" in chunk_ids[:2]
        # c1 appears in both
        assert "c1" in chunk_ids[:3]
        # All unique
        assert len(chunk_ids) == len(set(chunk_ids))

    def test_weights_affect_ranking(self):
        vec = [_hit("c1", 0.9), _hit("c2", 0.8)]
        fts = [_hit("c3", 0.9), _hit("c4", 0.8)]
        # High vector weight → vector results rank higher
        result = rrf_fuse(vec, fts, weights={"vector": 10.0, "fts5": 1.0})
        assert result[0].chunk_id == "c1"

    def test_dedupe(self):
        hits = [_hit("c1", 0.9), _hit("c1", 0.8), _hit("c2", 0.7)]
        result = dedupe_hits(hits)
        assert len(result) == 2
        assert result[0].chunk_id == "c1"
        assert result[1].chunk_id == "c2"

    def test_find_rank(self):
        hits = [_hit("c1", 0.9), _hit("c2", 0.8), _hit("c3", 0.7)]
        assert _find_rank(hits, "c1") == 1
        assert _find_rank(hits, "c2") == 2
        assert _find_rank(hits, "c999") is None

    def test_retrievers_merged(self):
        vec = [_hit("c1", 0.9, retrievers=["vector"])]
        fts = [_hit("c1", 0.85, retrievers=["fts5"])]
        result = rrf_fuse(vec, fts)
        assert "vector" in result[0].retrievers
        assert "fts5" in result[0].retrievers

    def test_empty_inputs(self):
        assert rrf_fuse([], []) == []
        # Single source still returns results
        assert len(rrf_fuse([_hit("c1", 0.9)], [])) == 1
        assert len(rrf_fuse([], [_hit("c1", 0.9)])) == 1


# ── HybridRetriever ─────────────────────────────────────────────────────

class TestHybridRetriever:
    def _make_retriever(self):
        mock_sqlite = MagicMock()
        mock_qdrant = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.is_available.return_value = True
        mock_embedding.embed.return_value = [[0.1, 0.2, 0.3]]

        # Configure SQLite mock
        mock_sqlite.search_fts5.return_value = [
            _hit("fts1", 0.5, retrievers=["fts5"], text="FTS result 1"),
        ]
        mock_sqlite.get_chunks_by_ids.return_value = {
            "vec1": {
                "id": "vec1", "text": "Vector result 1",
                "heading_path_json": '["Ch1"]', "heading_text": "Ch1",
            },
        }

        # Configure Qdrant mock
        mock_qdrant.search.return_value = [
            _hit("vec1", 0.9, retrievers=["vector"], text=""),
        ]

        return HybridRetriever(mock_sqlite, mock_qdrant, mock_embedding)

    def test_search_returns_hybrid_result(self):
        retriever = self._make_retriever()
        result = retriever.search("test query", top_k=5)
        assert isinstance(result, HybridResult)
        assert len(result.top_chunks) > 0
        assert result.vector_hits is not None
        assert result.fts_hits is not None

    def test_hydrates_vector_texts(self):
        retriever = self._make_retriever()
        result = retriever.search("test query", top_k=5)
        # The vector hit should have been hydrated
        vec_hit = next((h for h in result.top_chunks if h.chunk_id == "vec1"), None)
        assert vec_hit is not None
        assert vec_hit.text == "Vector result 1"
        retriever.sqlite.get_chunks_by_ids.assert_called_once_with(["vec1"])

    def test_no_embedding_client(self):
        mock_sqlite = MagicMock()
        mock_qdrant = MagicMock()
        mock_sqlite.search_fts5.return_value = [_hit("fts1", 0.5, retrievers=["fts5"])]

        retriever = HybridRetriever(mock_sqlite, mock_qdrant, embedding_client=None)
        result = retriever.search("test", top_k=5)
        assert len(result.vector_hits) == 0
        assert len(result.fts_hits) > 0
        assert result.vector_available is False

    def test_empty_embedding_falls_back_to_fts(self):
        retriever = self._make_retriever()
        retriever.embedding_client.embed.return_value = []

        result = retriever.search("test", top_k=5)

        assert result.vector_hits == []
        assert result.vector_available is False
        assert len(result.fts_hits) > 0


def test_retrieval_pipeline_is_cached_per_workspace(tmp_path, monkeypatch):
    created = []
    closed = []

    class SQLite:
        def __init__(self, workspace, **kwargs):
            created.append((workspace, kwargs))

        def init_db(self):
            pass

        def close(self):
            closed.append("sqlite")

    class Qdrant:
        def close(self):
            closed.append("qdrant")

    class Embedding:
        def __init__(self, _config):
            self.client = object()

    monkeypatch.setattr("rag.sqlite_store.KBSQLiteStore", SQLite)
    monkeypatch.setattr("rag.qdrant_store.QdrantStore", lambda *_args: Qdrant())
    monkeypatch.setattr("rag.embedding_service.EmbeddingService", Embedding)
    monkeypatch.setattr("rag.hybrid.HybridRetriever", lambda *_args: object())
    monkeypatch.setattr("rag.directory.DirectoryRetriever", lambda *_args: object())
    monkeypatch.setattr("rag.grep_retriever.GrepRetriever", lambda *_args: object())
    monkeypatch.setattr("rag.orchestrator.RetrievalOrchestrator", lambda *_args: object())

    clear_retrieval_cache()
    first = _retrieval_pipeline(str(tmp_path), {"rag": {"retrieval": {"default_mode": "hybrid"}}})
    second = _retrieval_pipeline(str(tmp_path), {"rag": {"retrieval": {"default_mode": "hybrid"}}})
    assert first is second
    assert len(created) == 1
    assert created[0][1]["check_same_thread"] is False
    clear_retrieval_cache()
    assert closed == ["sqlite", "qdrant"]


def test_acquire_release_refcount_and_deferred_close(tmp_path, monkeypatch):
    """A cache reset during an in-flight search must not close the live pipeline."""
    closed = []

    class SQLite:
        def __init__(self, _workspace, **kwargs):
            pass

        def init_db(self):
            pass

        def close(self):
            closed.append("sqlite")

        def log_retrieval(self, *_args):
            pass

    class Qdrant:
        def close(self):
            closed.append("qdrant")

    class Embedding:
        def __init__(self, _config):
            self.client = object()

    monkeypatch.setattr("rag.sqlite_store.KBSQLiteStore", SQLite)
    monkeypatch.setattr("rag.qdrant_store.QdrantStore", lambda *_args: Qdrant())
    monkeypatch.setattr("rag.embedding_service.EmbeddingService", Embedding)
    monkeypatch.setattr("rag.hybrid.HybridRetriever", lambda *_args: object())
    monkeypatch.setattr("rag.directory.DirectoryRetriever", lambda *_args: object())
    monkeypatch.setattr("rag.grep_retriever.GrepRetriever", lambda *_args: object())
    monkeypatch.setattr("rag.orchestrator.RetrievalOrchestrator", lambda *_args: object())

    config = {"rag": {"retrieval": {"default_mode": "hybrid"}}}
    clear_retrieval_cache()
    pipeline = _acquire_retrieval_pipeline(str(tmp_path), config)
    assert pipeline.refcount == 1

    # Reset while pinned: evicted from cache but physically kept alive.
    clear_retrieval_cache()
    assert pipeline.refcount == 1
    assert "sqlite" not in closed
    assert "qdrant" not in closed

    _release_retrieval_pipeline(pipeline)
    assert pipeline.refcount == 0
    assert "sqlite" in closed
    assert "qdrant" in closed


def test_vector_store_failure_marks_semantic_search_unavailable():
    retriever = TestHybridRetriever()._make_retriever()
    retriever.qdrant.search.side_effect = RuntimeError("qdrant unavailable")

    result = retriever.search("test", top_k=5)

    assert result.vector_hits == []
    assert result.vector_available is False
    assert len(result.fts_hits) > 0


# ── DirectoryRetriever ──────────────────────────────────────────────────

class TestDirectoryRetriever:
    def _make_retriever(self):
        mock_sqlite = MagicMock()
        mock_sqlite.search_directory.return_value = [
            {
                "document_id": "d1", "title": "Neural Networks",
                "source": "ch01.md", "course": "ml",
                "keywords_json": '["neural", "activation"]',
                "summary": "Introduction to neural networks",
                "chunk_count": 5,
                "bm25_rank": -2.5,
            },
        ]
        mock_sqlite.get_document.return_value = {
            "id": "d1", "title": "Neural Networks",
            "source": "ch01.md", "course": "ml",
        }
        return DirectoryRetriever(mock_sqlite)

    def test_search_returns_document_hits(self):
        retriever = self._make_retriever()
        results = retriever.search("neural networks")
        assert len(results) > 0
        assert isinstance(results[0], DocumentHit)
        assert results[0].document_id == "d1"

    def test_search_with_chunk_hits(self):
        retriever = self._make_retriever()
        chunk_hits = [_hit("c1", 0.8, document_id="d1", text="neural network content")]
        results = retriever.search("neural", chunk_hits=chunk_hits)
        assert len(results) > 0
        assert results[0].score > 0

    def test_reason_includes_matched_fields(self):
        retriever = self._make_retriever()
        results = retriever.search("neural networks")
        assert results[0].reason  # has some reason string


# ── GrepRetriever ───────────────────────────────────────────────────────

class TestGrepRetriever:
    def test_python_grep(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("This document discusses neural networks and backpropagation.\n" * 10,
                     encoding="utf-8")
        matches = _python_grep("neural", f, "d1", "test.md", 200)
        assert len(matches) > 0
        assert matches[0].match_type == "exact_phrase"
        assert matches[0].document_id == "d1"

    def test_python_grep_no_match(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("Hello world", encoding="utf-8")
        matches = _python_grep("quantum", f, "d1", "test.md", 200)
        assert len(matches) == 0

    def test_evidence_thin_exact_lookup_no_strong(self):
        matches = [GrepMatch(
            document_id="d1", source="test.md", text="x",
            match_context="short", match_type="partial", context_chars=100,
        )]
        assert _is_evidence_thin(matches, 100, "exact_lookup") is True

    def test_evidence_thin_exact_lookup_has_strong(self):
        matches = [GrepMatch(
            document_id="d1", source="test.md", text="x",
            match_context="a" * 400, match_type="exact_phrase", context_chars=400,
        )]
        assert _is_evidence_thin(matches, 400, "exact_lookup") is False

    def test_evidence_thin_coverage_needs_diversity(self):
        # Only 1 doc, 1 section — thin for coverage
        matches = [GrepMatch(
            document_id="d1", source="test.md", text="x",
            match_context="a" * 400, match_type="all_terms",
            context_chars=400, heading_text="Ch1",
        )]
        assert _is_evidence_thin(matches, 400, "coverage") is True

    def test_evidence_not_thin_coverage_diverse(self):
        matches = [
            GrepMatch(
                document_id="d1", source="a.md", text="x",
                match_context="a" * 400, match_type="all_terms",
                context_chars=400, heading_text="Ch1",
            ),
            GrepMatch(
                document_id="d2", source="b.md", text="y",
                match_context="b" * 400, match_type="all_terms",
                context_chars=400, heading_text="Ch2",
            ),
        ]
        assert _is_evidence_thin(matches, 800, "coverage") is False

    def test_confidence_high(self):
        matches = [GrepMatch(
            document_id="d1", source="test.md", text="x",
            match_context="a" * 400, match_type="exact_phrase", context_chars=400,
        )]
        assert _assess_confidence(matches, "exact_lookup", False) == "high"

    def test_confidence_low_expanded(self):
        matches = [GrepMatch(
            document_id="d1", source="test.md", text="x",
            match_context="a" * 400, match_type="partial", context_chars=400,
        )]
        assert _assess_confidence(matches, "coverage", True) == "low"

    def test_matches_to_hits(self):
        matches = [GrepMatch(
            document_id="d1", source="test.md", text="found it",
            match_context="context with found it inside",
            match_type="exact_phrase", context_chars=30,
        )]
        hits = _matches_to_hits(matches, "high", False, 500)
        assert len(hits) == 1
        assert isinstance(hits[0], RetrievalHit)
        assert hits[0].match_context is not None
        assert "grep" in hits[0].retrievers

    def test_grep_retriever_with_documents(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("Activation functions like ReLU are important.\n" * 20,
                     encoding="utf-8")

        retriever = GrepRetriever(str(tmp_path))
        docs = [DocumentHit(
            document_id="d1", source="test.md", title="Test",
            score=1.0,
        )]
        hits = retriever.search("ReLU", documents=docs)
        assert len(hits) > 0
        assert any("ReLU" in h.match_context for h in hits)
