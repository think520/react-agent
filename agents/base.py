"""BaseSpecialist — abstract base for all specialists.

A specialist describes how to run a sub-AgentLoop for a specific
class of work. The runner (agents/runner.py) consumes a
SpecialistConfig and instantiates the actual sub-AgentLoop.

Subclasses must implement:
  - name: str
  - description: str  (one line, used in tool schema and /specialists list)
  - system_prompt_template: str  (rendered with the task and any extras)
  - data_to_content(result_dict, content_cap) -> str
  - default_max_iterations: int
  - default_timeout_seconds: int
  - default_allowed_tools: list[str]

The ABC is intentionally minimal: v1 has no plugin loader, so each
specialist is a Python class registered via SpecialistRegistry.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseSpecialist(ABC):
    """Contract every v1 specialist must satisfy."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique specialist name (matches the delegate tool suffix)."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description, shown in tool schema and /specialists list."""

    @property
    @abstractmethod
    def system_prompt_template(self) -> str:
        """Template string. Receives {task}, {context}, {allowed_tools} via str.format."""

    @abstractmethod
    def data_to_content(self, result: dict[str, Any], content_cap: int) -> str:
        """Render the structured result dict into a human-readable content string.

        v1 rule: any structured field that drives the parent LLM's next
        decision MUST be rendered into content. Otherwise the parent
        only sees the prose summary.
        """

    @property
    @abstractmethod
    def default_max_iterations(self) -> int:
        """Default ReAct loop cap for this specialist."""

    @property
    @abstractmethod
    def default_timeout_seconds(self) -> int:
        """Default wall-clock cap for this specialist invocation."""

    @property
    @abstractmethod
    def default_allowed_tools(self) -> list[str]:
        """Default tool allowlist (before allowed_tools YAML override)."""

    @property
    @abstractmethod
    def default_provider(self) -> str:
        """Provider name (e.g. 'minimax', 'deepseek') used when YAML doesn't override."""

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Model name used when YAML doesn't override."""
