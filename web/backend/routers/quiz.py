"""Practice session endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from service.quiz_service import QuizService
from web.backend.deps import get_config, get_workspace
from web.backend.errors import APIError, unwrap_service_result

router = APIRouter()


class GenerateQuestionsRequest(BaseModel):
    query: str = Field(..., min_length=1)
    course: str | None = None
    count: int = Field(default=5, ge=1, le=15)
    document_ids: list[str] = Field(default_factory=list, max_length=50)


class StartQuizRequest(BaseModel):
    count: int = Field(default=5, ge=1, le=15)
    course: str | None = None
    question_type: str | None = None
    question_ids: list[int] = Field(default_factory=list, max_length=15)


class SubmitAnswerRequest(BaseModel):
    practice_session_id: int
    question_id: int
    answer: str = Field(..., min_length=1)


def _service() -> QuizService:
    return QuizService(get_workspace(), config=get_config())


@router.post("/questions")
def generate_questions(request: GenerateQuestionsRequest) -> dict:
    return unwrap_service_result(_service().generate_questions(
        query=request.query,
        course=request.course,
        count=request.count,
        document_ids=request.document_ids,
    ))


@router.post("/sessions")
def start_quiz(request: StartQuizRequest) -> dict:
    result = unwrap_service_result(_service().start_quiz(
        count=request.count,
        course=request.course,
        question_type=request.question_type,
        question_ids=request.question_ids,
    ))
    return {
        "practice_session_id": result["session_id"],
        "question_ids": result["question_ids"],
        "questions": result["questions"],
    }


@router.get("/sessions/active")
def active_sessions(limit: int = 10) -> dict:
    return unwrap_service_result(_service().list_active_sessions(limit=max(1, min(limit, 50))))


@router.get("/sessions/{practice_session_id}")
def session_state(practice_session_id: int) -> dict:
    result = _service().get_session_state(practice_session_id)
    if not result.get("ok"):
        raise APIError(404, "practice_session_not_found", result["error"])
    return {key: value for key, value in result.items() if key != "ok"}


@router.delete("/sessions/{practice_session_id}")
def abandon_session(practice_session_id: int) -> dict:
    result = _service().abandon_session(practice_session_id)
    if not result.get("ok"):
        raise APIError(404, "practice_session_not_found", result["error"])
    return {key: value for key, value in result.items() if key != "ok"}


@router.post("/answers")
def submit_answer(request: SubmitAnswerRequest) -> dict:
    return unwrap_service_result(_service().submit_answer(
        session_id=request.practice_session_id,
        question_id=request.question_id,
        answer=request.answer,
    ))


@router.get("/wrong")
def wrong(limit: int = 20) -> dict:
    return unwrap_service_result(_service().get_wrong_answer_book(limit=limit))


@router.get("/weakness")
def weakness() -> dict:
    return unwrap_service_result(_service().get_weakness_analysis())


@router.get("/stats")
def stats() -> dict:
    return unwrap_service_result(_service().get_stats())
