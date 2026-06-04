"""Tests for SpecialistConfig parsing + Python/YAML merge."""
from __future__ import annotations

import pytest

from agents.config import SpecialistConfig
from agents.specialists.triage import TriageSpecialist


def test_from_specialist_pure_defaults():
    sp = TriageSpecialist()
    cfg = SpecialistConfig.from_specialist(sp, raw=None)
    assert cfg.name == "triage"
    assert cfg.enabled is True
    assert cfg.timeout_seconds == sp.default_timeout_seconds
    assert cfg.max_iterations == sp.default_max_iterations
    assert cfg.allowed_tools == sp.default_allowed_tools
    assert cfg.allow_mcp is False
    assert cfg.provider is None
    assert cfg.model is None


def test_from_specialist_yaml_overrides():
    sp = TriageSpecialist()
    raw = {
        "enabled": False,
        "timeout_seconds": 90,
        "max_iterations": 4,
        "allow_mcp": True,
        "allowed_tools": ["x", "y"],
        "provider": "minimax",
        "model": "MiniMax-M2.7",
    }
    cfg = SpecialistConfig.from_specialist(sp, raw=raw)
    assert cfg.enabled is False
    assert cfg.timeout_seconds == 90
    assert cfg.max_iterations == 4
    assert cfg.allow_mcp is True
    assert cfg.allowed_tools == ["x", "y"]
    assert cfg.provider == "minimax"
    assert cfg.model == "MiniMax-M2.7"


def test_unknown_key_raises():
    sp = TriageSpecialist()
    with pytest.raises(ValueError, match="unknown config keys"):
        SpecialistConfig.from_specialist(sp, raw={"bogus_key": "x"})


def test_partial_override_keeps_defaults():
    """Only specified fields override; rest stay at specialist defaults."""
    sp = TriageSpecialist()
    raw = {"timeout_seconds": 99}
    cfg = SpecialistConfig.from_specialist(sp, raw=raw)
    assert cfg.timeout_seconds == 99
    assert cfg.max_iterations == sp.default_max_iterations
    assert cfg.allowed_tools == sp.default_allowed_tools
