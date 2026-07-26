"""Tests for rag.orchestrator — RetrievalOrchestrator."""

import pytest
from unittest.mock import MagicMock

from rag.schema import RetrievalHit, RetrievalResult, HybridResult, DocumentHit
from rag.orchestrator import RetrievalOrchestrator


def _hit(chunk_id, score=0.5, text="text"):
    return RetrievalHit(
        chunk_id=chunk_id, document_id="d1", source="test.md",
        text=text, score=score, retrievers=["vector", "fts5"],
    )


def _doc_hit(doc_id, score=0.8):
    return DocumentHit(
        document_id=doc_id, source="test.md", title="Test",
        score=score,
    )


class TestOrchestrator:
    def _make_orchestrator(self, hybrid_hits=None, doc_hits=None, grep_hits=None):
        mock_hybrid = MagicMock()
        mock_hybrid.search.return_value = HybridResult(
            top_chunks=hybrid_hits or [],
            all_chunk_hits=hybrid_hits or [],
        )

        mock_directory = MagicMock()
        mock_directory.search.return_value = doc_hits or []

        mock_grep = MagicMock()
        mock_grep.search.return_value = grep_hits or []

        return RetrievalOrchestrator(mock_hybrid, mock_directory, mock_grep)

    def test_hybrid_mode(self):
        hits = [_hit("c1"), _hit("c2")]
        orch = self._make_orchestrator(hybrid_hits=hits)
        result = orch.search("test", mode="hybrid", top_k=5)
        assert result.mode == "hybrid"
        assert len(result.hits) == 2
        assert result.debug["vector_available"] is False

    def test_directory_mode(self):
        doc_hits = [_doc_hit("d1")]
        orch = self._make_orchestrator(doc_hits=doc_hits)
        result = orch.search("test", mode="directory", top_k=5)
        assert result.mode == "directory"
        assert result.document_hits is not None
        assert len(result.document_hits) == 1

    def test_directory_grep_mode(self):
        grep_hits = [_hit("grep1")]
        doc_hits = [_doc_hit("d1")]
        orch = self._make_orchestrator(grep_hits=grep_hits, doc_hits=doc_hits)
        result = orch.search("在哪里提到test", mode="directory_grep", top_k=5)
        assert result.mode == "directory_grep"
        assert len(result.hits) == 1

    def test_auto_routes_to_hybrid(self):
        hits = [_hit("c1")]
        orch = self._make_orchestrator(hybrid_hits=hits)
        result = orch.search("什么是神经网络", mode="auto", top_k=5)
        assert result.mode == "hybrid"

    def test_auto_routes_to_directory_grep(self):
        grep_hits = [_hit("g1")]
        doc_hits = [_doc_hit("d1")]
        orch = self._make_orchestrator(grep_hits=grep_hits, doc_hits=doc_hits)
        result = orch.search("在哪里提到ReLU", mode="auto", top_k=5)
        assert result.mode == "directory_grep"

    def test_auto_fallback_hybrid_empty(self):
        """Auto mode: hybrid empty → fallback to directory_grep."""
        grep_hits = [_hit("g1")]
        doc_hits = [_doc_hit("d1")]
        orch = self._make_orchestrator(
            hybrid_hits=[],  # hybrid returns nothing
            grep_hits=grep_hits,
            doc_hits=doc_hits,
        )
        result = orch.search("什么是梯度", mode="auto", top_k=5)
        assert result.mode == "directory_grep"
        assert result.fallback_from == "hybrid"

    def test_explicit_mode_no_fallback(self):
        """Explicit hybrid mode: no fallback even if empty."""
        orch = self._make_orchestrator(hybrid_hits=[])
        result = orch.search("什么是梯度", mode="hybrid", top_k=5)
        assert result.mode == "hybrid"
        assert result.fallback_from is None

    def test_empty_query(self):
        orch = self._make_orchestrator()
        result = orch.search("", mode="auto", top_k=5)
        assert result.confidence == "low"

    def test_course_filter_passed(self):
        hits = [_hit("c1")]
        orch = self._make_orchestrator(hybrid_hits=hits)
        orch.search("test", mode="hybrid", top_k=5, course="ml")
        orch.hybrid.search.assert_called_with("test", top_k=5, course="ml")
