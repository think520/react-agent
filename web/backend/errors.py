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
    status_code: int | None = None,
    code: str = "request_failed",
) -> dict:
    if not result.get("ok"):
        error_code = result.get("code") or code
        mapped_status = {
            "wrong_answer_not_found": 404,
            "question_not_found": 404,
            "question_set_not_found": 404,
            "evidence_missing": 409,
            "grading_unavailable": 503,
            "variant_generation_failed": 503,
            "document_not_found": 404,
            "document_read_only": 409,
            "document_conflict": 409,
            "version_not_found": 404,
            "knowledge_revision_conflict": 409,
            "concept_not_found": 404,
            "concept_name_conflict": 409,
            "relationship_not_found": 404,
            "relationship_exists": 409,
            "self_relationship": 409,
            "invalid_rel_type": 400,
        }.get(error_code, 400)
        # 审查 F07：失败结果里的**结构化部分结果**（moved / failed / batch_id …）必须穿过
        # HTTP 边界。丢掉它们，界面就不知道"已经搬走了哪几份"，也就没有恢复入口。
        details = result.get("details")
        if details is None:
            extra = {
                key: value for key, value in result.items()
                if key not in {"ok", "code", "error", "details"}
            }
            details = extra or None
        raise APIError(
            status_code=status_code or mapped_status,
            code=error_code,
            message=result.get("error", "request failed"),
            details=details,
        )
    return result

