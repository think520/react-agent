"""Trusted web research primitives."""

from .providers import SearchCandidate, SearchProviderError
from .store import ResearchStore

__all__ = ["ResearchStore", "SearchCandidate", "SearchProviderError"]
