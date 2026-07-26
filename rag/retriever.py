"""Top-level search entry point.

Delegates to RetrievalOrchestrator for the new RAG v2 pipeline.
Falls back to legacy VectorStoreRouter if new stores are not initialized.
"""

from __future__ import annotations

import os
from knowledge.paths import knowledge_path


def search_index(
    workspace: str,
    query: str,
    course: str | None = None,
    top_k: int = 5,
    config: dict | None = None,
    mode: str = "auto",
) -> list[dict]:
    """Search the knowledge base.

    Tries the new RAG v2 pipeline (Orchestrator) first.
    Falls back to legacy VectorStoreRouter if SQLite store is not initialized.

    Args:
        workspace: Workspace root path.
        query: Search query.
        course: Optional course filter.
        top_k: Max results.
        config: Config dict with 'rag' section.
        mode: Retrieval mode — "auto" | "hybrid" | "directory" | "directory_grep"

    Returns:
        List of result dicts with text, source, score, etc.
    """
    config = config or {}

    # Try new RAG v2 pipeline
    db_path = knowledge_path(workspace, "knowledge.db")
    if os.path.exists(db_path):
        return _search_v2(workspace, query, course, top_k, config, mode)

    # Legacy fallback — old JSON index
    return _search_legacy(workspace, query, course, top_k, config)


def _search_v2(
    workspace: str,
    query: str,
    course: str | None,
    top_k: int,
    config: dict,
    mode: str,
) -> list[dict]:
    """Search using the new RAG v2 pipeline (Orchestrator)."""
    from rag.sqlite_store import KBSQLiteStore
    from rag.qdrant_store import QdrantStore
    from rag.embedding_service import EmbeddingService
    from rag.hybrid import HybridRetriever
    from rag.directory import DirectoryRetriever
    from rag.grep_retriever import GrepRetriever
    from rag.orchestrator import RetrievalOrchestrator

    sqlite = KBSQLiteStore(workspace)
    sqlite.init_db()

    qdrant = QdrantStore(workspace, config)
    embedding = EmbeddingService(config)

    hybrid = HybridRetriever(sqlite, qdrant, embedding.client, config)
    directory = DirectoryRetriever(sqlite, config)
    grep = GrepRetriever(workspace, config)

    orch = RetrievalOrchestrator(hybrid, directory, grep, config)
    result = orch.search(query=query, mode=mode, top_k=top_k, course=course)

    # Convert results to dicts for backward compatibility
    output = []

    # Chunk-level hits (hybrid, directory_grep)
    for hit in result.hits:
        d = {
            "chunk_id": hit.chunk_id,
            "document_id": hit.document_id,
            "text": hit.text,
            "source": hit.source,
            "score": hit.score,
            "metadata": {
                "heading_path": hit.heading_path,
                "heading_text": hit.heading_text,
                "page_start": hit.page_start,
                "page_end": hit.page_end,
                "slide_start": hit.slide_start,
                "slide_end": hit.slide_end,
            },
            "retrievers": hit.retrievers,
            "match_context": hit.match_context,
            "debug": hit.debug,
        }
        output.append(d)

    # Document-level hits (directory mode)
    if result.document_hits:
        for doc in result.document_hits:
            d = {
                "type": "document",
                "document_id": doc.document_id,
                "source": doc.source,
                "title": doc.title,
                "course": doc.course,
                "score": doc.score,
                "reason": doc.reason,
                "chunk_count": doc.chunk_count,
                "heading_path": doc.heading_path,
                "top_chunks": [
                    {
                        "text": c.text,
                        "source": c.source,
                        "score": c.score,
                        "heading_text": c.heading_text,
                    }
                    for c in doc.top_chunks
                ],
                "debug": doc.debug,
            }
            output.append(d)

    # Log retrieval
    sqlite.log_retrieval(query, result.mode, len(output))
    sqlite.close()

    return output


def _search_legacy(
    workspace: str,
    query: str,
    course: str | None,
    top_k: int,
    config: dict,
) -> list[dict]:
    """Legacy search over the old JSON sparse index."""
    del config  # legacy dense routing is retired; sparse JSON index only
    index_path = knowledge_path(workspace, "rag_index.json")
    from .vector_store import LocalVectorStore
    store = LocalVectorStore(index_path)
    return store.search(query=query, course=course, top_k=top_k)
