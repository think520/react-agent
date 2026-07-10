"""Stable Web API error responses."""

from __future__ import annotations

from typing import Any


class APIError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def unwrap_service_result(
    result: dict,
    *,
    status_code: int = 400,
    code: str = "request_failed",
) -> dict:
    if not result.get("ok"):
        raise APIError(
            status_code=status_code,
            code=code,
            message=result.get("error", "request failed"),
        )
    return result

