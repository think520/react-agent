"""SpecialistConfig — runtime configuration for one specialist.

A SpecialistConfig is built by merging:
  1. The specialist's BaseSpecialist defaults (default_* properties)
  2. The YAML config under `specialists.<name>` (overrides)

v1 does not allow creating a new specialist from YAML alone — there
must be a Python class providing defaults. YAML can only override
behavior of existing specialists.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .base import BaseSpecialist


@dataclass
class SpecialistConfig:
    """Resolved config for one specialist instance."""

    name: str
    enabled: bool = True
    provider: str | None = None
    model: str | None = None
    timeout_seconds: int = 60
    max_iterations: int = 5
    allow_mcp: bool = False
    allowed_tools: list[str] = field(default_factory=list)

    @classmethod
    def from_specialist(
        cls,
        specialist: BaseSpecialist,
        raw: dict | None = None,
    ) -> "SpecialistConfig":
        """Build a SpecialistConfig from a specialist's defaults + YAML overrides.

        Args:
            specialist: the BaseSpecialist instance providing defaults.
            raw: the dict from config.yaml under `specialists.<name>`,
                 or None for pure defaults.

        Raises:
            ValueError: if `raw` contains unknown keys (fail-fast).
        """
        raw = raw or {}
        _validate_keys(specialist.name, raw)

        cfg = cls(
            name=specialist.name,
            enabled=bool(raw.get("enabled", True)),
            provider=raw.get("provider"),
            model=raw.get("model"),
            timeout_seconds=int(raw.get("timeout_seconds", specialist.default_timeout_seconds)),
            max_iterations=int(raw.get("max_iterations", specialist.default_max_iterations)),
            allow_mcp=bool(raw.get("allow_mcp", False)),
            allowed_tools=list(raw.get("allowed_tools", specialist.default_allowed_tools)),
        )
        return cfg


_VALID_KEYS = frozenset({
    "enabled", "provider", "model", "timeout_seconds",
    "max_iterations", "allow_mcp", "allowed_tools",
})


def _validate_keys(name: str, raw: dict) -> None:
    unknown = set(raw) - _VALID_KEYS
    if unknown:
        raise ValueError(
            f"Specialist {name!r}: unknown config keys: {sorted(unknown)}. "
            f"Allowed: {sorted(_VALID_KEYS)}"
        )
