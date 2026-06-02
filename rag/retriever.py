import os

from .router import VectorStoreRouter
from .vector_store import LocalVectorStore


def search_index(
    workspace: str,
    query: str,
    course: str | None = None,
    top_k: int = 5,
    config: dict | None = None,
) -> list[dict]:
    """Search the workspace-local RAG index via VectorStoreRouter."""
    if config and config.get("rag"):
        router = VectorStoreRouter(workspace, config)
        return router.search(query=query, course=course, top_k=top_k)
    # Fallback: no config, use sparse store directly (backward compatible)
    index_path = os.path.join(workspace, ".knowledge", "rag_index.json")
    store = LocalVectorStore(index_path)
    return store.search(query=query, course=course, top_k=top_k)
