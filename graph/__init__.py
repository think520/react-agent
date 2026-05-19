"""Knowledge graph schema and store adapters."""

from .local_store import LocalGraphStore
from .store import get_graph_store

__all__ = ["LocalGraphStore", "get_graph_store"]
