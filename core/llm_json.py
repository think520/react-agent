"""Shared parsing helpers for LLM JSON output.

Every subsystem that asks a model for JSON used to carry its own copy of
"strip code fences, find brackets, fix trailing commas". This module is the
single implementation. Parsers are lenient on formatting but strict on shape:
callers state whether they expect an object or an array.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_FENCE_OPEN = re.compile(r"```(?:json)?\s*")
_FENCE_CLOSE = re.compile(r"```\s*$")
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _strip_fences(text: str) -> str:
    text = _FENCE_OPEN.sub("", text or "")
    text = _FENCE_CLOSE.sub("", text)
    return text.strip()


def _bracket_slice(text: str, open_ch: str, close_ch: str) -> str | None:
    """Return the first balanced bracket region, or None."""
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _loads_with_repair(fragment: str) -> Any | None:
    try:
        return json.loads(fragment)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_TRAILING_COMMA.sub(r"\1", fragment))
    except json.JSONDecodeError:
        return None


def parse_llm_object(text: str) -> dict | None:
    """Extract a JSON object from an LLM response. None when unparseable."""
    cleaned = _strip_fences(text)
    value = _loads_with_repair(cleaned)
    if isinstance(value, dict):
        return value
    fragment = _bracket_slice(cleaned, "{", "}")
    if fragment is None:
        return None
    value = _loads_with_repair(fragment)
    return value if isinstance(value, dict) else None


def parse_llm_array(text: str) -> list:
    """Extract a JSON array from an LLM response. Empty list when unparseable."""
    cleaned = _strip_fences(text)
    value = _loads_with_repair(cleaned)
    if isinstance(value, list):
        return value
    fragment = _bracket_slice(cleaned, "[", "]")
    if fragment is None:
        logger.warning("No JSON array found in LLM response: %.200s", cleaned)
        return []
    value = _loads_with_repair(fragment)
    if not isinstance(value, list):
        logger.warning("LLM response is not a JSON array: %.200s", fragment)
        return []
    return value
