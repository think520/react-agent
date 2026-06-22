"""HybridRetriever — combines vector and FTS5 retrieval via RRF.

The HybridRetriever is a chunk-level candidate generator.
It produces HybridResult which is consumed by both the Orchestrator
(for direct hybrid mode) and the DirectoryRetriever (for chunk aggregation).
"""

from __future__ import annotations

import logging

from rag.schema import RetrievalHit, HybridResult
from rag.rrf import rrf_fuse, dedupe_hits

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Combines vector (Qdrant) and FTS5 retrieval via RRF fusion."""

    def __init__(
        self,
        sqlite_store,
        qdrant_store,
        embedding_client=None,
        config: dict | None = None,
    ):
        self.sqlite = sqlite_store
        self.qdrant = qdrant_store
        self.embedding_client = embedding_client  # OllamaEmbeddingClient or None

        rag_cfg = (config or {}).get("rag", {})
        ret_cfg = rag_cfg.get("retrieval", {})
        self.rrf_k = ret_cfg.get("rrf", {}).get("k", 60)
        self.rrf_weights = ret_cfg.get("rrf", {}).get("weights", {"vector": 1.0, "fts5": 1.0})
        self.vector_top_k = ret_cfg.get("vector_top_k", 30)
        self.fts_top_k = ret_cfg.get("fts_top_k", 30)

    def search(
        self,
        query: str,
        top_k: int = 5,
        candidate_k: int = 30,
        course: str | None = None,
    ) -> HybridResult:
        """Run hybrid search: vector + FTS5 → RRF fusion.

        Args:
            query: User query text.
            top_k: Number of final results to return.
            candidate_k: Number of candidates per retriever before RRF.
            course: Optional course filter.

        Returns:
            HybridResult with top_chunks, all_chunk_hits, and raw hits.
        """
        # Vector retrieval
        vector_hits = self._vector_search(query, candidate_k, course)

        # FTS5 retrieval
        fts_hits = self._fts_search(query, candidate_k, course)

        # RRF fusion
        all_fused = rrf_fuse(vector_hits, fts_hits, k=self.rrf_k, weights=self.rrf_weights)

        # Hydrate text from SQLite for vector hits (Qdrant doesn't store text)
        all_fused = self._hydrate_texts(all_fused)

        # Dedupe
        all_fused = dedupe_hits(all_fused)

        # Top-k
        top_chunks = all_fused[:top_k]

        return HybridResult(
            top_chunks=top_chunks,
            all_chunk_hits=all_fused,
            vector_hits=vector_hits,
            fts_hits=fts_hits,
        )

    def _vector_search(
        self, query: str, top_k: int, course: str | None
    ) -> list[RetrievalHit]:
        """Search Qdrant for semantically similar chunks."""
        if self.embedding_client is None:
            return []

        try:
            if not self.embedding_client.is_available():
                return []
        except Exception:
            return []

        try:
            # Get query embedding
            vectors = self.embedding_client.embed([query])
            if not vectors or not vectors[0]:
                return []

            query_vector = vectors[0]

            # Search Qdrant
            hits = self.qdrant.search(query_vector, top_k=top_k)

            # Filter by course if specified (Qdrant payload filter)
            if course:
                hits = [h for h in hits if self._matches_course(h, course)]

            return hits

        except Exception as e:
            logger.warning("Vector search failed: %s", e)
            return []

    def _fts_search(
        self, query: str, top_k: int, course: str | None
    ) -> list[RetrievalHit]:
        """Search SQLite FTS5 for keyword matches."""
        try:
            return self.sqlite.search_fts5(query, top_k=top_k, course=course)
        except Exception as e:
            logger.warning("FTS5 search failed: %s", e)
            return []

    def _hydrate_texts(self, hits: list[RetrievalHit]) -> list[RetrievalHit]:
        """Fill in text from SQLite for hits that came from Qdrant (text="")."""
        for hit in hits:
            if not hit.text:
                row = self.sqlite.get_chunk_by_id(hit.chunk_id)
                if row:
                    hit.text = row.get("text", "")
                    # Also update heading info if missing
                    if not hit.heading_path and row.get("heading_path_json"):
                        import json
                        try:
                            hit.heading_path = json.loads(row["heading_path_json"])
                        except (ValueError, TypeError):
                            pass
                    if not hit.heading_text and row.get("heading_text"):
                        hit.heading_text = row["heading_text"]
        return hits

    def _matches_course(self, hit: RetrievalHit, course: str) -> bool:
        """Check if a hit matches the course filter.

        Since we can't filter by course in Qdrant payload (we'd need to store
        course in payload), we check via SQLite.
        """
        doc = self.sqlite.get_document(hit.document_id)
        if doc and doc.get("course") == course:
            return True
        return False
