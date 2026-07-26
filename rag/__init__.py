"""Local SQLite/Qdrant ingestion and retrieval modules (RAG v2)."""

from .retriever import search_index

# RAG v2 components
from .schema import RetrievalHit, DocumentHit, RetrievalResult, HybridResult
from .sqlite_store import KBSQLiteStore
from .qdrant_store import QdrantStore
from .ollama import OllamaEmbeddingClient
from .embedding_service import EmbeddingService
from .source_section import SourceSection
from .chunker_v2 import chunk_sections, ChunkingConfig
from .rrf import rrf_fuse
from .hybrid import HybridRetriever
from .directory import DirectoryRetriever
from .grep_retriever import GrepRetriever
from .orchestrator import RetrievalOrchestrator
from .query_router import auto_route

__all__ = [
    "search_index",
    "RetrievalHit", "DocumentHit", "RetrievalResult", "HybridResult",
    "KBSQLiteStore", "QdrantStore", "OllamaEmbeddingClient", "EmbeddingService",
    "SourceSection", "chunk_sections", "ChunkingConfig",
    "rrf_fuse", "HybridRetriever", "DirectoryRetriever",
    "GrepRetriever", "RetrievalOrchestrator", "auto_route",
]
