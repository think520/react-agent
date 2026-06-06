"""SpecialistRegistry — owns the set of registered specialists and the
recent-invocation store surfaced via /specialists.

Separation of concerns:
  - registry.py: "which specialists exist" + "what was their last few calls"
  - runner.py:    "how to actually run a specialist"

The registry is in-memory only. Recent invocations are a deque(maxlen=10)
that resets on REPL restart (Decision 11).
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .base import BaseSpecialist
from .config import SpecialistConfig

logger = logging.getLogger(__name__)

_MAX_INVOCATIONS = 10
_PREVIEW_CHARS = 200


@dataclass
class InvocationRecord:
    """One past specialist invocation. Stored in the in-memory deque."""

    specialist: str
    ok: bool
    error_type: str | None
    duration_ms: int
    content_preview: str
    model: str | None
    ts: float = field(default_factory=time.time)


class SpecialistRegistry:
    """Holds BaseSpecialist instances and their resolved SpecialistConfig.

    Built once at REPL startup by register_builtin_specialists(). Lookup
    is by name (string). Disabled specialists remain registered but are
    filtered out at tool registration time.
    """

    def __init__(self) -> None:
        self._specialists: dict[str, BaseSpecialist] = {}
        self._configs: dict[str, SpecialistConfig] = {}
        self._invocations: deque[InvocationRecord] = deque(maxlen=_MAX_INVOCATIONS)

    # --- registration ---

    def register(
        self,
        specialist: BaseSpecialist,
        yaml_overrides: dict | None = None,
    ) -> SpecialistConfig:
        """Register a specialist and resolve its config. Returns the config."""
        if specialist.name in self._specialists:
            raise ValueError(f"Specialist {specialist.name!r} already registered")
        self._specialists[specialist.name] = specialist
        cfg = SpecialistConfig.from_specialist(specialist, yaml_overrides)
        self._configs[specialist.name] = cfg
        logger.info(
            "Specialist registered: %s (enabled=%s, timeout=%ds, iter=%d, allow_mcp=%s)",
            specialist.name, cfg.enabled, cfg.timeout_seconds,
            cfg.max_iterations, cfg.allow_mcp,
        )
        return cfg

    # --- lookup ---

    def get(self, name: str) -> BaseSpecialist | None:
        return self._specialists.get(name)

    def get_config(self, name: str) -> SpecialistConfig | None:
        return self._configs.get(name)

    def list_names(self) -> list[str]:
        return list(self._specialists.keys())

    def list_enabled(self) -> list[tuple[str, BaseSpecialist, SpecialistConfig]]:
        return [
            (name, sp, self._configs[name])
            for name, sp in self._specialists.items()
            if self._configs[name].enabled
        ]

    def get_invocation(self, n: int = 3) -> list[InvocationRecord]:
        """Return the most recent n invocations (oldest first or newest first?)."""
        items = list(self._invocations)
        return items[-n:]

    def record_invocation(
        self,
        specialist: str,
        ok: bool,
        error_type: str | None,
        duration_ms: int,
        content: str,
        model: str | None,
    ) -> None:
        """Append a record. Content is truncated to a preview before storing."""
        preview = content if len(content) <= _PREVIEW_CHARS else content[:_PREVIEW_CHARS] + "..."
        self._invocations.append(InvocationRecord(
            specialist=specialist,
            ok=ok,
            error_type=error_type,
            duration_ms=duration_ms,
            content_preview=preview,
            model=model,
        ))


def register_builtin_specialists(
    yaml_section: dict | None = None,
) -> SpecialistRegistry:
    """Construct the v1 registry with all 3 built-in specialists.

    The YAML section under `config['specialists']` (or None for all defaults)
    is merged per-specialist.
    """
    from .specialists.doc_reader import DocReaderSpecialist
    from .specialists.planner import PlannerSpecialist
    from .specialists.triage import TriageSpecialist

    registry = SpecialistRegistry()
    yaml_section = yaml_section or {}
    for cls in (DocReaderSpecialist, TriageSpecialist, PlannerSpecialist):
        instance = cls()
        registry.register(instance, yaml_overrides=yaml_section.get(instance.name))
    return registry
