"""Structured personal knowledge and read-only legacy migration support."""

from .legacy import LegacyMemoryEntry, LegacyMemoryReader
from .personal_store import PersonalKnowledgeStore

__all__ = ["LegacyMemoryEntry", "LegacyMemoryReader", "PersonalKnowledgeStore"]
