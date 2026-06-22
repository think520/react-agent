"""Reciprocal Rank Fusion (RRF) for merging ranked lists.

RRF merges results from multiple retrievers (vector + FTS5) into a single
ranked list. It only considers rank position, not raw scores.

Formula: rrf_score = sum(weight[source] / (k + rank))
"""

from __future__ import annotations

from rag.schema import RetrievalHit


def rrf_fuse(
    vector_hits: list[RetrievalHit],
    fts_hits: list[RetrievalHit],
    k: int = 60,
    weights: dict[str, float] | None = None,
) -> list[RetrievalHit]:
    """Fuse vector and FTS5 results using RRF.

    Args:
        vector_hits: Ranked list from vector retriever.
        fts_hits: Ranked list from FTS5 retriever.
        k: RRF constant (default 60).
        weights: Per-source weights. Default: {"vector": 1.0, "fts5": 1.0}.

    Returns:
        De-duplicated, re-ranked list of RetrievalHits.
    """
    if weights is None:
        weights = {"vector": 1.0, "fts5": 1.0}

    # Build chunk_id → RRF score map
    scores: dict[str, float] = {}
    # Track which hits we've seen (by chunk_id)
    hit_map: dict[str, RetrievalHit] = {}

    for rank, hit in enumerate(vector_hits):
        cid = hit.chunk_id
        w = weights.get("vector", 1.0)
        scores[cid] = scores.get(cid, 0.0) + w / (k + rank + 1)
        if cid not in hit_map:
            hit_map[cid] = hit

    for rank, hit in enumerate(fts_hits):
        cid = hit.chunk_id
        w = weights.get("fts5", 1.0)
        scores[cid] = scores.get(cid, 0.0) + w / (k + rank + 1)
        if cid not in hit_map:
            hit_map[cid] = hit

    # Sort by RRF score descending
    sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)

    # Build result
    results: list[RetrievalHit] = []
    for cid in sorted_ids:
        hit = hit_map[cid]
        # Collect retriever sources
        retrievers = list(set(hit.retrievers))
        # Check if this chunk appeared in both lists
        in_vector = any(h.chunk_id == cid for h in vector_hits)
        in_fts = any(h.chunk_id == cid for h in fts_hits)
        if in_vector and "vector" not in retrievers:
            retrievers.append("vector")
        if in_fts and "fts5" not in retrievers:
            retrievers.append("fts5")

        results.append(RetrievalHit(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            source=hit.source,
            text=hit.text,
            heading_path=hit.heading_path,
            heading_text=hit.heading_text,
            page_start=hit.page_start,
            page_end=hit.page_end,
            slide_start=hit.slide_start,
            slide_end=hit.slide_end,
            char_start=hit.char_start,
            char_end=hit.char_end,
            score=scores[cid],
            retrievers=retrievers,
            debug={
                "rrf_score": scores[cid],
                "vector_rank": _find_rank(vector_hits, cid),
                "fts_rank": _find_rank(fts_hits, cid),
            },
            match_context=hit.match_context,
        ))

    return results


def dedupe_hits(hits: list[RetrievalHit]) -> list[RetrievalHit]:
    """Remove duplicate hits by chunk_id, keeping the first (highest-ranked)."""
    seen: set[str] = set()
    results: list[RetrievalHit] = []
    for hit in hits:
        if hit.chunk_id not in seen:
            seen.add(hit.chunk_id)
            results.append(hit)
    return results


def _find_rank(hits: list[RetrievalHit], chunk_id: str) -> int | None:
    """Find 1-based rank of a chunk_id in a hit list."""
    for i, h in enumerate(hits):
        if h.chunk_id == chunk_id:
            return i + 1
    return None
