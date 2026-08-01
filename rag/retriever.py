"""Top-level entry point for the SQLite/Qdrant RAG pipeline."""

from __future__ import annotations

import os
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any
from knowledge.paths import knowledge_path


@dataclass
class _CachedPipeline:
    orchestrator: Any
    sqlite: Any
    qdrant: Any
    lock: threading.RLock
    #: Number of searches currently pinning this pipeline. A pipeline with a
    #: non-zero count must not be closed under it even if cache reset runs.
    refcount: int = 0
    #: Set by clear_retrieval_cache when the pipeline should be evicted as soon
    #: as the last pinned search releases it (deferred close).
    _closed: bool = False


_PIPELINE_CACHE: OrderedDict[tuple[str, str], _CachedPipeline] = OrderedDict()
_PIPELINE_CACHE_LOCK = threading.Lock()
_PIPELINE_CACHE_LIMIT = 8


def _close_pipeline(pipeline: _CachedPipeline) -> None:
    with pipeline.lock:
        pipeline.sqlite.close()
        pipeline.qdrant.close()


def clear_retrieval_cache(workspace: str | None = None) -> None:
    """Close cached SQLite connections, optionally for one workspace.

    A pipeline that is currently pinned by an in-flight search is evicted from
    the cache but only physically closed once the last search releases it, so a
    mid-search reset (e.g. ``/kb reset``) never tears down a live connection.
    """
    target = os.path.normcase(os.path.abspath(workspace)) if workspace else None
    with _PIPELINE_CACHE_LOCK:
        keys = [
            key for key in _PIPELINE_CACHE
            if target is None or key[0] == target
        ]
        for key in keys:
            pipeline = _PIPELINE_CACHE.pop(key)
            pipeline._closed = True
            if pipeline.refcount <= 0:
                _close_pipeline(pipeline)


def _retrieval_pipeline_unlocked(workspace: str, config: dict) -> _CachedPipeline:
    from rag.sqlite_store import KBSQLiteStore
    from rag.qdrant_store import QdrantStore
    from rag.embedding_service import EmbeddingService
    from rag.hybrid import HybridRetriever
    from rag.directory import DirectoryRetriever
    from rag.grep_retriever import GrepRetriever
    from rag.orchestrator import RetrievalOrchestrator

    key = (
        os.path.normcase(os.path.abspath(workspace)),
        json.dumps(config.get("rag", {}), sort_keys=True, ensure_ascii=False, default=str),
    )
    cached = _PIPELINE_CACHE.get(key)
    if cached:
        _PIPELINE_CACHE.move_to_end(key)
        return cached

    sqlite = KBSQLiteStore(workspace, check_same_thread=False)
    sqlite.init_db()
    qdrant = QdrantStore(workspace, config)
    embedding = EmbeddingService(config)
    orchestrator = RetrievalOrchestrator(
        HybridRetriever(sqlite, qdrant, embedding.client, config),
        DirectoryRetriever(sqlite, config),
        GrepRetriever(workspace, config),
        config,
    )
    pipeline = _CachedPipeline(orchestrator, sqlite, qdrant, threading.RLock())
    _PIPELINE_CACHE[key] = pipeline
    while len(_PIPELINE_CACHE) > _PIPELINE_CACHE_LIMIT:
        _old_key, old_pipeline = _PIPELINE_CACHE.popitem(last=False)
        _close_pipeline(old_pipeline)
    return pipeline


def _retrieval_pipeline(workspace: str, config: dict) -> _CachedPipeline:
    with _PIPELINE_CACHE_LOCK:
        return _retrieval_pipeline_unlocked(workspace, config)


def _acquire_retrieval_pipeline(workspace: str, config: dict) -> _CachedPipeline:
    """Pin a cached pipeline until the caller calls ``_release_retrieval_pipeline``.

    The global cache lock is held only to look up or create the pipeline and
    bump its reference count; it is released *before* blocking on the
    per-pipeline lock, so a slow search in one workspace does not serialize
    every other RAG operation (other workspaces, ``/kb reset``, new pipelines).
    """
    with _PIPELINE_CACHE_LOCK:
        pipeline = _retrieval_pipeline_unlocked(workspace, config)
        pipeline.refcount += 1
    pipeline.lock.acquire()
    return pipeline


def _release_retrieval_pipeline(pipeline: _CachedPipeline) -> None:
    """Release a pipeline pinned by ``_acquire_retrieval_pipeline``."""
    pipeline.lock.release()
    with _PIPELINE_CACHE_LOCK:
        pipeline.refcount -= 1
        if pipeline.refcount <= 0 and pipeline._closed:
            for key, cached in list(_PIPELINE_CACHE.items()):
                if cached is pipeline:
                    del _PIPELINE_CACHE[key]
                    break
            _close_pipeline(pipeline)


def search_index(
    workspace: str,
    query: str,
    course: str | None = None,
    top_k: int = 5,
    config: dict | None = None,
    mode: str = "auto",
) -> list[dict]:
    """Search the knowledge base.

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
    results, _status = search_index_with_status(
        workspace,
        query,
        course=course,
        top_k=top_k,
        config=config,
        mode=mode,
    )
    return results


def search_index_with_status(
    workspace: str,
    query: str,
    course: str | None = None,
    top_k: int = 5,
    config: dict | None = None,
    mode: str = "auto",
) -> tuple[list[dict], dict]:
    """Search and return user-visible retrieval capability metadata."""
    config = config or {}

    db_path = knowledge_path(workspace, "knowledge.db")
    if os.path.exists(db_path):
        return _search_v2_with_status(workspace, query, course, top_k, config, mode)

    return [], {
        "retrieval_mode": "unavailable",
        "resolved_mode": "unavailable",
        "semantic_available": False,
        "fallback_from": "missing_index",
        "confidence": "low",
    }


def _search_v2_with_status(
    workspace: str,
    query: str,
    course: str | None,
    top_k: int,
    config: dict,
    mode: str,
) -> tuple[list[dict], dict]:
    """Search using the new RAG v2 pipeline (Orchestrator)."""
    pipeline = _acquire_retrieval_pipeline(workspace, config)
    try:
        result = pipeline.orchestrator.search(
            query=query, mode=mode, top_k=top_k, course=course,
        )
        result_count = len(result.hits) + len(result.document_hits or [])
        pipeline.sqlite.log_retrieval(query, result.mode, result_count)
    finally:
        _release_retrieval_pipeline(pipeline)

    output = []
    for hit in result.hits:
        output.append({
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
        })

    if result.document_hits:
        for doc in result.document_hits:
            output.append({
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
            })

    semantic_available = bool(result.debug.get("vector_available"))
    return output, {
        "retrieval_mode": result.mode if semantic_available else "fts_only",
        "resolved_mode": result.mode,
        "semantic_available": semantic_available,
        "fallback_from": result.fallback_from,
        "confidence": result.confidence,
    }
