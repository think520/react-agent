"""Memory facade (AG-0.5): the single door to personal-knowledge storage.

Re-exports the low-level store that AG-3 (core/memory_injector.py) will build
its injection lifecycle on. Kept at the store layer so core/ never depends on
service/.
"""

from __future__ import annotations

from memory.personal_store import PersonalKnowledgeStore

__all__ = ["PersonalKnowledgeStore"]
