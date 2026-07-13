"""Qdrant vector storage layer for RAG v2.

Uses Qdrant local persistent mode by default.
Supports switching to server mode via config.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from rag.schema import RetrievalHit
from knowledge.paths import knowledge_dir

logger = logging.getLogger(__name__)

# Default config
DEFAULT_COLLECTION = "bobodan_chunks"
DEFAULT_DISTANCE = "cosine"
_UUID_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")  # fixed namespace for deterministic UUIDs


def _chunk_id_to_uuid(chunk_id: str) -> str:
    """Convert a chunk_id hash to a deterministic UUID5 string.

    Qdrant requires point IDs to be unsigned integers or UUIDs.
    We use UUID5 (deterministic from chunk_id) so the same chunk
    always maps to the same point.
    """
    return str(uuid.uuid5(_UUID_NS, chunk_id))


class QdrantStore:
    """Qdrant vector store for chunk embeddings.

    Uses local persistent storage at .knowledge/qdrant/.
    """

    def __init__(self, workspace: str, config: dict | None = None):
        self.workspace = Path(workspace)
        rag_cfg = (config or {}).get("rag", {})
        vdb_cfg = rag_cfg.get("vector_db", {})

        self.mode = vdb_cfg.get("mode", "local")
        configured_path = vdb_cfg.get("local_path")
        if configured_path and configured_path.replace("\\", "/") != ".knowledge/qdrant":
            self.local_path = self.workspace / configured_path
        else:
            self.local_path = Path(knowledge_dir(str(self.workspace))) / "qdrant"
        self.url = vdb_cfg.get("url", "http://localhost:6333")
        self.collection = vdb_cfg.get("collection", DEFAULT_COLLECTION)
        self.distance = vdb_cfg.get("distance", DEFAULT_DISTANCE)

        self._client = None
        self._embedding_dim: int | None = None

    def _get_client(self):
        """Lazy-init Qdrant client."""
        if self._client is not None:
            return self._client

        try:
            from qdrant_client import QdrantClient
        except ImportError:
            raise RuntimeError(
                "qdrant-client is not installed. "
                "Install it with: pip install qdrant-client"
            )

        if self.mode == "local":
            self.local_path.mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=str(self.local_path))
        elif self.mode == "server":
            self._client = QdrantClient(url=self.url)
        else:
            raise ValueError(f"Unknown Qdrant mode: {self.mode!r}. Use 'local' or 'server'.")

        return self._client

    def init_collection(self, embedding_dim: int) -> None:
        """Create collection if it doesn't exist."""
        self._embedding_dim = embedding_dim
        client = self._get_client()

        try:
            from qdrant_client.models import Distance, VectorParams
        except ImportError:
            raise RuntimeError("qdrant-client is not installed.")

        existing = [c.name for c in client.get_collections().collections]
        if self.collection not in existing:
            distance_map = {
                "cosine": Distance.COSINE,
                "euclid": Distance.EUCLID,
                "dot": Distance.DOT,
            }
            client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=distance_map.get(self.distance, Distance.COSINE),
                ),
            )
            logger.info("Created Qdrant collection %s (dim=%d)", self.collection, embedding_dim)

    def upsert(
        self,
        chunk_ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict],
    ) -> None:
        """Upsert vectors with payloads.

        Args:
            chunk_ids: Unique chunk IDs (used as point IDs).
            vectors: Embedding vectors.
            payloads: Metadata dicts (stored as payload).
        """
        from qdrant_client.models import PointStruct

        client = self._get_client()
        points = [
            PointStruct(id=_chunk_id_to_uuid(cid), vector=vec, payload=pl)
            for cid, vec, pl in zip(chunk_ids, vectors, payloads)
        ]

        # Batch upsert (Qdrant handles large batches well)
        batch_size = 100
        for i in range(0, len(points), batch_size):
            client.upsert(
                collection_name=self.collection,
                points=points[i : i + batch_size],
            )

    def search(
        self,
        query_vector: list[float],
        top_k: int = 30,
        document_id: str | None = None,
    ) -> list[RetrievalHit]:
        """Search for similar vectors.

        Returns RetrievalHit objects with chunk metadata from payload.
        Hits should be validated against SQLite (hydrate) before use.
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = self._get_client()

        query_filter = None
        if document_id:
            query_filter = Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            )

        results = client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
        )

        hits = []
        for point in results.points:
            pl = point.payload or {}
            hits.append(
                RetrievalHit(
                    chunk_id=pl.get("chunk_id", str(point.id)),
                    document_id=pl.get("document_id", ""),
                    source=pl.get("source", ""),
                    text="",  # text not stored in Qdrant; hydrate from SQLite
                    heading_path=pl.get("heading_path", []),
                    heading_text=pl.get("heading_text", ""),
                    page_start=pl.get("page_start"),
                    page_end=pl.get("page_end"),
                    slide_start=pl.get("slide_start"),
                    slide_end=pl.get("slide_end"),
                    score=point.score,
                    retrievers=["vector"],
                    debug={"qdrant_score": point.score, "qdrant_id": str(point.id)},
                )
            )
        return hits

    def delete_by_filter(self, document_id: str) -> None:
        """Delete all vectors for a document."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = self._get_client()
        client.delete(
            collection_name=self.collection,
            points_selector=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
            ),
        )

    def get_stats(self) -> dict:
        """Return collection statistics."""
        client = self._get_client()
        try:
            info = client.get_collection(self.collection)
            return {
                "collection": self.collection,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "mode": self.mode,
                "embedding_dim": self._embedding_dim,
            }
        except Exception as e:
            return {
                "collection": self.collection,
                "error": str(e),
                "mode": self.mode,
            }

    def delete_collection(self) -> None:
        """Delete the entire collection (for full reindex)."""
        client = self._get_client()
        try:
            client.delete_collection(self.collection)
            logger.info("Deleted Qdrant collection %s", self.collection)
        except Exception:
            pass  # collection may not exist

    def close(self) -> None:
        """Close the client connection."""
        if self._client:
            self._client.close()
            self._client = None
