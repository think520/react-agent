"""Unified retrieval result schemas for RAG v2.

TextChunk = chunking stage product (stored in SQLite + Qdrant).
RetrievalHit = retrieval stage product (assembled from SQLite + Qdrant results).
DocumentHit = document-level result from DirectoryRetriever.
RetrievalResult = top-level result from RetrievalOrchestrator.
HybridResult = intermediate result from HybridRetriever (shared with Directory).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievalHit:
    """Chunk-level retrieval result."""

    # Core identity
    chunk_id: str
    document_id: str
    source: str  # "course/deep-learning/ch03.md"

    # Content
    text: str  # chunk body (pure text, no heading prefix)
    heading_path: list[str] = field(default_factory=list)  # ["深度学习", "激活函数", "ReLU"]
    heading_text: str = ""  # "深度学习 > 激活函数 > ReLU"

    # Source location
    page_start: int | None = None
    page_end: int | None = None
    slide_start: int | None = None
    slide_end: int | None = None
    char_start: int | None = None
    char_end: int | None = None

    # Retrieval info
    score: float = 0.0
    retrievers: list[str] = field(default_factory=list)  # ["vector", "fts5"]
    debug: dict = field(default_factory=dict)  # {"vector_rank": 2, "fts_rank": 5, "rrf_score": 0.032}

    # Grep-specific
    match_context: str | None = None


@dataclass
class DocumentHit:
    """Document-level result from DirectoryRetriever."""

    document_id: str
    source: str
    title: str
    course: str | None = None
    heading_path: list[str] = field(default_factory=list)
    score: float = 0.0
    reason: str = ""  # "chunks matched '激活函数', 'ReLU'"
    chunk_count: int = 0
    top_chunks: list[RetrievalHit] = field(default_factory=list)
    debug: dict = field(default_factory=dict)  # {"metadata_score": 0.42, "chunk_aggregate_score": 0.68}


@dataclass
class RetrievalResult:
    """Top-level result from RetrievalOrchestrator."""

    hits: list[RetrievalHit] = field(default_factory=list)
    document_hits: list[DocumentHit] | None = None  # directory mode
    mode: str = "hybrid"  # hybrid | directory | directory_grep
    confidence: str = "high"  # high | medium | low
    fallback_from: str | None = None  # degraded from which mode
    debug: dict = field(default_factory=dict)


@dataclass
class HybridResult:
    """Intermediate result from HybridRetriever.

    top_chunks: final top_k results for the caller.
    all_chunk_hits: full RRF-fused candidates (for DirectoryRetriever to consume).
    vector_hits: raw vector results (for debugging).
    fts_hits: raw FTS5 results (for debugging).
    """

    top_chunks: list[RetrievalHit] = field(default_factory=list)
    all_chunk_hits: list[RetrievalHit] = field(default_factory=list)
    vector_hits: list[RetrievalHit] = field(default_factory=list)
    fts_hits: list[RetrievalHit] = field(default_factory=list)
