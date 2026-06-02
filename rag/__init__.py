"""Local RAG ingestion and retrieval modules."""

from .chunker import TextChunk, chunk_text
from .dense_store import DenseVectorStore
from .ollama import OllamaEmbeddingClient
from .retriever import search_index
from .router import VectorStoreRouter
from .vector_store import LocalVectorStore

__all__ = [
    "TextChunk", "chunk_text", "search_index", "LocalVectorStore",
    "DenseVectorStore", "OllamaEmbeddingClient", "VectorStoreRouter",
]
