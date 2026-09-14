"""Register the specialist delegate tools for the web runtime (P1-16).

`cli/repl.py` registered delegate_doc_reader / delegate_triage /
delegate_planner at REPL start, so the same three specialists were simply
unavailable in the browser - the two front ends did not offer the same
capabilities. Registration is process-wide and idempotent; the calling session
travels with each tool call (tools.base.execute_tool), because a web process
runs turns concurrently and cannot close over one "current session".
"""

from __future__ import annotations

import logging
import threading

from agents.registry import SpecialistRegistry, register_builtin_specialists
from tools.agents import register_delegate_tools
from tools.base import TOOL_REGISTRY

logger = logging.getLogger(__name__)

DELEGATE_TOOL_NAMES = ("delegate_doc_reader", "delegate_triage", "delegate_planner")

_lock = threading.Lock()
_registered = False


def ensure_specialist_tools(config: dict | None = None) -> int:
    """Register the delegate tools once per process; returns the count live."""
    global _registered
    with _lock:
        if _registered:
            return sum(1 for name in DELEGATE_TOOL_NAMES if name in TOOL_REGISTRY)
        section = (config or {}).get("specialists") or {}
        try:
            registry: SpecialistRegistry = register_builtin_specialists(section)
            count = register_delegate_tools(registry, get_app_config=lambda: config or {})
        except Exception:
            logger.exception("Specialist registration failed for the web runtime")
            return 0
        _registered = True
        logger.info("Registered %d specialist delegate tools for the web", count)
        return count
