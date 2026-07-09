"""Local RAG ingestion and retrieval modules."""

from .chunker import TextChunk, chunk_text
from .retriever import search_index

# Legacy stores (kept for backward compatibility)
from .dense_store import DenseVectorStore
from .ollama import OllamaEmbeddingClient
from .router import VectorStoreRouter
from .vector_store import LocalVectorStore

# RAG v2 components
from .schema import RetrievalHit, DocumentHit, RetrievalResult, HybridResult
from .sqlite_store import KBSQLiteStore
from .qdrant_store import QdrantStore
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
    # Legacy
    "TextChunk", "chunk_text", "search_index", "LocalVectorStore",
    "DenseVectorStore", "OllamaEmbeddingClient", "VectorStoreRouter",
    # RAG v2
    "RetrievalHit", "DocumentHit", "RetrievalResult", "HybridResult",
    "KBSQLiteStore", "QdrantStore", "EmbeddingService",
    "SourceSection", "chunk_sections", "ChunkingConfig",
    "rrf_fuse", "HybridRetriever", "DirectoryRetriever",
    "GrepRetriever", "RetrievalOrchestrator", "auto_route",
]
