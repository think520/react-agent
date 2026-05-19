import os

from .local_store import LocalGraphStore
from .neo4j_store import Neo4jGraphStore


def get_graph_store(workspace: str):
    """Return Neo4j store when configured, otherwise local JSON fallback."""
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    if uri and username and password:
        try:
            return Neo4jGraphStore(uri, username, password)
        except Exception:
            pass

    graph_path = os.path.join(workspace, ".knowledge", "graph_store.json")
    return LocalGraphStore(graph_path)
