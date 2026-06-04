"""Tests for BaseSpecialist ABC."""
from __future__ import annotations

import pytest

from agents.base import BaseSpecialist


def test_base_specialist_cannot_instantiate():
    """ABC: cannot instantiate BaseSpecialist directly."""
    with pytest.raises(TypeError):
        BaseSpecialist()


def test_subclass_must_implement_all_abstracts():
    """Incomplete subclass raises TypeError on instantiation."""

    class HalfBaked(BaseSpecialist):
        @property
        def name(self) -> str:
            return "x"

        # Missing: description, system_prompt_template, etc.

    with pytest.raises(TypeError):
        HalfBaked()


def test_complete_subclass_instantiates():
    class Complete(BaseSpecialist):
        @property
        def name(self) -> str:
            return "complete"

        @property
        def description(self) -> str:
            return "d"

        @property
        def system_prompt_template(self) -> str:
            return "t"

        def data_to_content(self, result, cap):
            return ""

        @property
        def default_max_iterations(self) -> int:
            return 3

        @property
        def default_timeout_seconds(self) -> int:
            return 30

        @property
        def default_allowed_tools(self) -> list:
            return ["read_file"]

        @property
        def default_provider(self) -> str:
            return "minimax"

        @property
        def default_model(self) -> str:
            return "m"

    s = Complete()
    assert s.name == "complete"
    assert s.default_timeout_seconds == 30
