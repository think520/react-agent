import os

from .vector_store import LocalVectorStore


def search_index(workspace: str, query: str, course: str | None = None, top_k: int = 5) -> list[dict]:
    """Search the workspace-local RAG index."""
    index_path = os.path.join(workspace, ".knowledge", "rag_index.json")
    store = LocalVectorStore(index_path)
    return store.search(query=query, course=course, top_k=top_k)
