"""Shared service-layer result envelope."""

from typing import Any


def ok(**values: Any) -> dict[str, Any]:
    return {"ok": True, **values}


def err(error: str, *, code: str | None = None, **values: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "error": error, **values}
    if code:
        result["code"] = code
    return result
