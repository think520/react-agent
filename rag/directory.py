"""DirectoryRetriever — document-level routing.

Finds "which documents are relevant" by combining:
1. Metadata lexical search (title, summary, keywords)
2. Chunk aggregation from HybridRetriever results

The DirectoryRetriever does NOT call HybridRetriever internally.
chunk_hits are passed in by the Orchestrator.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict

from rag.schema import RetrievalHit, DocumentHit

logger = logging.getLogger(__name__)


class DirectoryRetriever:
    """Document-level routing via metadata + chunk aggregation."""

    def __init__(self, sqlite_store, config: dict | None = None):
        self.sqlite = sqlite_store

        rag_cfg = (config or {}).get("rag", {})
        ret_cfg = rag_cfg.get("retrieval", {})
        dir_cfg = ret_cfg.get("directory", {})
        self.metadata_weight = dir_cfg.get("metadata_weight", 0.4)
        self.chunk_aggregate_weight = dir_cfg.get("chunk_aggregate_weight", 0.6)

    def search(
        self,
        query: str,
        chunk_hits: list[RetrievalHit] | None = None,
        top_k: int = 8,
        top_chunks_per_doc: int = 3,
        course: str | None = None,
    ) -> list[DocumentHit]:
        """Find relevant documents via metadata + chunk aggregation.

        Args:
            query: User query text.
            chunk_hits: Results from HybridRetriever (for chunk aggregation).
            top_k: Max documents to return.
            top_chunks_per_doc: Top chunks to include per document.
            course: Optional course filter.

        Returns:
            Sorted list of DocumentHit.
        """
        # 1. Metadata search
        metadata_scores: dict[str, dict] = {}
        dir_entries = self.sqlite.search_directory(query, top_k=top_k * 2, course=course)
        for entry in dir_entries:
            doc_id = entry["document_id"]
            score = abs(entry.get("bm25_rank", 0))
            metadata_scores[doc_id] = {
                "score": score,
                "matched_fields": _detect_matched_fields(query, entry),
                "title": entry.get("title", ""),
                "source": entry.get("source", ""),
                "course": entry.get("course"),
                "chunk_count": entry.get("chunk_count", 0),
            }

        # 2. Chunk aggregation
        chunk_agg_scores: dict[str, list[RetrievalHit]] = defaultdict(list)
        if chunk_hits:
            for hit in chunk_hits:
                chunk_agg_scores[hit.document_id].append(hit)

        # 3. Normalize scores
        max_meta = max((v["score"] for v in metadata_scores.values()), default=1.0) or 1.0
        max_chunk = max(
            (max((h.score for h in hits), default=0.0) for hits in chunk_agg_scores.values()),
            default=1.0,
        ) or 1.0

        # 4. Merge and rank
        all_doc_ids = set(metadata_scores.keys()) | set(chunk_agg_scores.keys())
        doc_hits: list[DocumentHit] = []

        for doc_id in all_doc_ids:
            meta = metadata_scores.get(doc_id, {})
            agg_hits = chunk_agg_scores.get(doc_id, [])

            # Normalize scores
            meta_score = (meta.get("score", 0) / max_meta) if max_meta > 0 else 0
            chunk_score = (max((h.score for h in agg_hits), default=0) / max_chunk) if max_chunk > 0 else 0

            # Weighted combination
            final_score = (
                meta_score * self.metadata_weight +
                chunk_score * self.chunk_aggregate_weight
            )

            # Build reason
            reason_parts = []
            matched_fields = meta.get("matched_fields", [])
            if matched_fields:
                reason_parts.append(f"metadata: {', '.join(matched_fields)}")
            if agg_hits:
                matched_terms = _extract_matched_terms(query, agg_hits)
                if matched_terms:
                    reason_parts.append(f"chunks matched: {', '.join(matched_terms)}")
            reason = "; ".join(reason_parts) if reason_parts else "chunk aggregation"

            # Get document info from SQLite
            doc = self.sqlite.get_document(doc_id)
            title = (doc or {}).get("title") or meta.get("title", "")
            source = (doc or {}).get("source") or meta.get("source", "")
            doc_course = (doc or {}).get("course") or meta.get("course")
            real_path = (doc or {}).get("path") or ""

            # Sort top chunks by score
            top_chunks = sorted(agg_hits, key=lambda h: h.score, reverse=True)[:top_chunks_per_doc]

            doc_hits.append(DocumentHit(
                document_id=doc_id,
                source=source,
                title=title,
                course=doc_course,
                heading_path=top_chunks[0].heading_path if top_chunks else [],
                score=final_score,
                reason=reason,
                chunk_count=meta.get("chunk_count", len(agg_hits)),
                top_chunks=top_chunks,
                path=real_path,
                debug={
                    "metadata_score": meta_score,
                    "chunk_aggregate_score": chunk_score,
                    "matched_fields": matched_fields,
                },
            ))

        # Sort by score
        doc_hits.sort(key=lambda d: d.score, reverse=True)
        return doc_hits[:top_k]


def _detect_matched_fields(query: str, entry: dict) -> list[str]:
    """Detect which metadata fields matched the query."""
    matched = []
    q_lower = query.lower()

    title = (entry.get("title") or "").lower()
    summary = (entry.get("summary") or "").lower()
    keywords_json = entry.get("keywords_json") or "[]"
    source = (entry.get("source") or "").lower()

    try:
        keywords = json.loads(keywords_json)
    except (ValueError, TypeError):
        keywords = []

    if q_lower in title or any(t in title for t in q_lower.split()):
        matched.append("title")
    if q_lower in summary or any(t in summary for t in q_lower.split()):
        matched.append("summary")
    if any(q_lower in kw.lower() for kw in keywords):
        matched.append("keywords")
    if q_lower in source:
        matched.append("source")

    return matched


def _extract_matched_terms(query: str, hits: list[RetrievalHit]) -> list[str]:
    """Extract which query terms appeared in chunk text."""
    terms = set()
    q_tokens = set(query.lower().split())
    for hit in hits:
        text_lower = hit.text.lower()
        for token in q_tokens:
            if token in text_lower and len(token) > 1:
                terms.add(token)
    return sorted(terms)[:5]
