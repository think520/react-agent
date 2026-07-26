"""RetrievalOrchestrator — unified retrieval entry point.

Manages the flow between Hybrid, Directory, and Grep retrievers.
Supports three modes: hybrid, directory, directory_grep.

Core constraint: Hybrid is the chunk candidate generator.
Directory consumes Hybrid results. Orchestrator shares them.
Directory never calls Hybrid internally.
"""

from __future__ import annotations

import logging

from rag.schema import RetrievalResult, HybridResult
from rag.query_router import auto_route
from rag.hybrid import HybridRetriever
from rag.directory import DirectoryRetriever
from rag.grep_retriever import GrepRetriever

logger = logging.getLogger(__name__)


class RetrievalOrchestrator:
    """Unified retrieval entry point for all callers (CLI, tool, API)."""

    def __init__(
        self,
        hybrid: HybridRetriever,
        directory: DirectoryRetriever,
        grep: GrepRetriever,
        config: dict | None = None,
    ):
        self.hybrid = hybrid
        self.directory = directory
        self.grep = grep

        rag_cfg = (config or {}).get("rag", {})
        ret_cfg = rag_cfg.get("retrieval", {})
        self.default_top_k = ret_cfg.get("directory_top_k", 8)
        self.default_mode = ret_cfg.get("default_mode", "hybrid")

    def search(
        self,
        query: str,
        mode: str = "auto",
        top_k: int = 5,
        course: str | None = None,
    ) -> RetrievalResult:
        """Run retrieval with the specified mode.

        Args:
            query: User query text.
            mode: "auto" | "hybrid" | "directory" | "directory_grep"
            top_k: Number of results to return.
            course: Optional course filter.

        Returns:
            RetrievalResult with hits, mode, confidence, etc.
        """
        if not query.strip():
            return RetrievalResult(mode="hybrid", confidence="low", debug={"error": "empty query"})

        # Resolve mode
        if mode == "auto":
            resolved_mode = auto_route(query)
        else:
            resolved_mode = mode

        # Dispatch
        if resolved_mode == "hybrid":
            return self._search_hybrid(query, top_k, course, mode)

        if resolved_mode == "directory":
            return self._search_directory(query, top_k, course)

        if resolved_mode == "directory_grep":
            return self._search_directory_grep(query, top_k, course)

        # Unknown mode — fallback to hybrid
        logger.warning("Unknown retrieval mode %r, falling back to hybrid", mode)
        return self._search_hybrid(query, top_k, course, mode)

    def _search_hybrid(
        self, query: str, top_k: int, course: str | None, original_mode: str
    ) -> RetrievalResult:
        """Hybrid search: vector + FTS5 → RRF → top_k."""
        result = self.hybrid.search(query, top_k=top_k, course=course)

        retrieval_result = RetrievalResult(
            hits=result.top_chunks,
            mode="hybrid",
            confidence="high" if result.top_chunks else "low",
            debug={
                "vector_available": result.vector_available,
                "vector_count": len(result.vector_hits),
                "fts_count": len(result.fts_hits),
                "fused_count": len(result.all_chunk_hits),
            },
        )

        # Auto mode: if hybrid returns nothing, fallback to directory_grep
        if not result.top_chunks and original_mode == "auto":
            logger.info("Hybrid empty, falling back to directory_grep")
            fallback = self._search_directory_grep(query, top_k, course)
            fallback.fallback_from = "hybrid"
            return fallback

        return retrieval_result

    def _search_directory(
        self, query: str, top_k: int, course: str | None
    ) -> RetrievalResult:
        """Directory search: hybrid broad → document aggregation."""
        # Run hybrid with broader candidate_k for better aggregation
        hybrid_result = self.hybrid.search(query, top_k=top_k, candidate_k=50, course=course)

        # Pass chunk hits to directory
        doc_hits = self.directory.search(
            query,
            chunk_hits=hybrid_result.all_chunk_hits,
            top_k=self.default_top_k,
            course=course,
        )

        return RetrievalResult(
            hits=[],  # directory mode doesn't return chunk-level hits directly
            document_hits=doc_hits,
            mode="directory",
            confidence="high" if doc_hits else "low",
            debug={
                "vector_available": hybrid_result.vector_available,
                "hybrid_candidates": len(hybrid_result.all_chunk_hits),
                "documents_found": len(doc_hits),
            },
        )

    def _search_directory_grep(
        self, query: str, top_k: int, course: str | None
    ) -> RetrievalResult:
        """Directory + Grep: hybrid broad → document routing → grep evidence."""
        # Run hybrid with broader candidate_k
        hybrid_result = self.hybrid.search(query, top_k=top_k, candidate_k=50, course=course)

        # Directory routing
        doc_hits = self.directory.search(
            query,
            chunk_hits=hybrid_result.all_chunk_hits,
            top_k=self.default_top_k,
            course=course,
        )

        # Grep evidence search
        grep_hits = self.grep.search(query, documents=doc_hits)

        # Determine confidence from grep results
        confidence = "low"
        if grep_hits:
            debug_info = grep_hits[0].debug if grep_hits[0].debug else {}
            confidence = debug_info.get("confidence", "low")

        return RetrievalResult(
            hits=grep_hits,
            mode="directory_grep",
            confidence=confidence,
            debug={
                "vector_available": hybrid_result.vector_available,
                "hybrid_candidates": len(hybrid_result.all_chunk_hits),
                "documents_checked": len(doc_hits),
                "grep_matches": len(grep_hits),
            },
        )
