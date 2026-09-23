"""Embedding signature: which provider/model/dimension these vectors belong to (G2).

Vectors are only meaningful next to the model that produced them. Until now
nothing recorded that pairing, so switching provider or model quietly pointed the
retriever at vectors built by something else.

The signature is a small JSON file in the workspace knowledge directory. It is
rebuildable derived data - losing it costs nothing - but a *mismatch* has to be
surfaced instead of ignored, which is the whole point of recording it.
"""

from __future__ import annotations

import json
import logging
import os

from core.atomic_io import atomic_write_json
from knowledge.paths import knowledge_dir

logger = logging.getLogger(__name__)

SIGNATURE_VERSION = 1
SIGNATURE_FILENAME = "embedding_signature.json"
SIGNATURE_KEYS = ("provider", "model", "dim")


def signature_path(workspace: str) -> str:
    return os.path.join(knowledge_dir(workspace), SIGNATURE_FILENAME)


def signature_of(model_info: dict | None) -> dict:
    info = model_info or {}
    dim = info.get("dim")
    return {
        "version": SIGNATURE_VERSION,
        "provider": str(info.get("name") or ""),
        "model": str(info.get("model") or ""),
        "dim": int(dim) if dim else None,
    }


def read_signature(workspace: str) -> dict | None:
    try:
        with open(signature_path(workspace), "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, ValueError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def write_signature(workspace: str, model_info: dict | None) -> dict:
    payload = signature_of(model_info)
    atomic_write_json(signature_path(workspace), payload)
    return payload


def mismatch_reason(workspace: str, model_info: dict | None) -> str | None:
    """Why the stored vectors must not be used, or None when they still match."""
    stored = read_signature(workspace)
    if not stored:
        return None
    current = signature_of(model_info)
    if not current.get("dim"):
        # The current provider cannot even say how wide its vectors are, so it
        # cannot contradict anything.
        return None
    differing = [key for key in SIGNATURE_KEYS if stored.get(key) != current.get(key)]
    if not differing:
        return None
    stored_brief = {key: stored.get(key) for key in SIGNATURE_KEYS}
    current_brief = {key: current.get(key) for key in SIGNATURE_KEYS}
    return (
        "embedding signature mismatch (" + ", ".join(differing) + "): stored "
        + json.dumps(stored_brief, ensure_ascii=False)
        + " vs current " + json.dumps(current_brief, ensure_ascii=False)
        + "; rebuild the vectors before trusting semantic search"
    )
