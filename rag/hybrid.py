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


#: 本地 Qdrant 是单进程存储，被占用时的**唯一**特征串。
#: 审查 F4：以前只匹配「Storage folder」，会把路径里带这个词的其它错误误诊成占用。
VECTOR_STORE_LOCK_MARKER = "already accessed by another instance"


def classify_vector_error(message: str) -> str:
    # 把向量腿的异常分类成上层使用的 stable code（见 rag/retrieval_status.py）。
    text = str(message or "")
    if VECTOR_STORE_LOCK_MARKER in text:
        return "vector_store_locked"
    return "vector_store_error"


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
        # B2: any EmbeddingProvider (Ollama or an OpenAI-compatible API) or None.
        self.embedding_client = embedding_client

        rag_cfg = (config or {}).get("rag", {})
        ret_cfg = rag_cfg.get("retrieval", {})
        self.rrf_k = ret_cfg.get("rrf", {}).get("k", 60)
        self.rrf_weights = ret_cfg.get("rrf", {}).get("weights", {"vector": 1.0, "fts5": 1.0})
        self.vector_top_k = ret_cfg.get("vector_top_k", 30)
        self.fts_top_k = ret_cfg.get("fts_top_k", 30)
        #: 最近一次向量腿失败的种类 / 原始信息（给上层做"如实说明"用）。
        self.vector_error = ""
        self.vector_error_detail = ""

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
        # 审查 F5：这两个字段是「最近一次失败」的状态，必须**每次查询重置** ——
        # 管线是缓存的，同一实例会服务很多次查询；不重置就会出现
        # vector_available=True 却 vector_error=locked 这种自相矛盾的结果。
        self.vector_error = ""
        self.vector_error_detail = ""

        # Probe once per search so callers can distinguish "no semantic hit"
        # from "semantic retrieval is unavailable".
        embedding_available = self._vector_available()
        vector_hits, vector_available = self._vector_search(
            query, candidate_k, course, vector_available=embedding_available
        )

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
            vector_available=vector_available,
            vector_error=self.vector_error,
        )

    def _vector_available(self) -> bool:
        if self.embedding_client is None:
            return False
        try:
            return bool(self.embedding_client.is_available())
        except Exception:
            return False

    def _vector_search(
        self,
        query: str,
        top_k: int,
        course: str | None,
        *,
        vector_available: bool | None = None,
    ) -> tuple[list[RetrievalHit], bool]:
        """Search Qdrant for semantically similar chunks.

        失败时**记下种类**（«self.vector_error»）—— 上层要能把原因说清楚：
        「后端探活失败」和「本地向量库被另一个进程占用」对用户的下一步完全不同。
        """
        if vector_available is None:
            vector_available = self._vector_available()
        if not vector_available or self.embedding_client is None:
            self.vector_error = "embedding_provider_unavailable"
            return [], False

        try:
            # Get query embedding
            vectors = self.embedding_client.embed([query])
            if not vectors or not vectors[0]:
                self.vector_error = "embedding_returned_nothing"
                return [], False

            query_vector = vectors[0]

            # Search Qdrant
            hits = self.qdrant.search(query_vector, top_k=top_k)

            # Filter by course if specified (Qdrant payload filter)
            if course:
                hits = [h for h in hits if self._matches_course(h, course)]

            return hits, True

        except Exception as e:
            logger.warning("Vector search failed: %s", e)
            message = str(e)
            # 本地 Qdrant 是单进程存储：服务在跑时，别的进程打开会得到这句话。
            if "already accessed" in message or "Storage folder" in message:
                self.vector_error = "vector_store_locked"
            else:
                self.vector_error = "vector_store_error"
            self.vector_error_detail = message
            return [], False

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
        missing_ids = [hit.chunk_id for hit in hits if not hit.text]
        chunks_by_id = self.sqlite.get_chunks_by_ids(missing_ids)
        for hit in hits:
            if not hit.text:
                row = chunks_by_id.get(hit.chunk_id)
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
