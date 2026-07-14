"""Practice session endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from service.preference_service import PreferenceService
from service.quiz_service import QuizService
from web.backend.capabilities import WEB_SKILL_NAMES
from web.backend.deps import get_config, get_default_provider_name, get_request_workspace
from web.backend.errors import APIError, unwrap_service_result

router = APIRouter()


class GenerateQuestionsRequest(BaseModel):
    query: str = Field(..., min_length=1)
    course: str | None = None
    count: int = Field(default=5, ge=1, le=15)
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    web_research_id: str | None = Field(default=None, max_length=64)
    web_confirmed: bool = False


class StartQuizRequest(BaseModel):
    count: int = Field(default=5, ge=1, le=15)
    course: str | None = None
    question_type: str | None = None
    question_ids: list[int] = Field(default_factory=list, max_length=15)


class SubmitAnswerRequest(BaseModel):
    practice_session_id: int
    question_id: int
    answer: str = Field(..., min_length=1)


def _service(request: Request) -> QuizService:
    return QuizService(get_request_workspace(request), config=get_config())


@router.post("/questions")
def generate_questions(body: GenerateQuestionsRequest, request: Request) -> dict:
    config = get_config()
    preferences = PreferenceService(
        get_default_provider_name(config),
        sorted(WEB_SKILL_NAMES),
    ).get()
    search = preferences.get("search") or {}
    return unwrap_service_result(_service(request).generate_questions(
        query=body.query,
        course=body.course,
        count=body.count,
        document_ids=body.document_ids,
        web_research_id=body.web_research_id,
        web_confirmed=body.web_confirmed,
        search_permission=search.get("permission", "ask"),
        search_provider=search.get("provider", "auto"),
        jina_fallback=bool(search.get("jina_fallback", True)),
    ))


@router.post("/sessions")
def start_quiz(body: StartQuizRequest, request: Request) -> dict:
    result = unwrap_service_result(_service(request).start_quiz(
        count=body.count,
        course=body.course,
        question_type=body.question_type,
        question_ids=body.question_ids,
    ))
    return {
        "practice_session_id": result["session_id"],
        "question_ids": result["question_ids"],
        "questions": result["questions"],
    }


@router.get("/sessions/active")
def active_sessions(request: Request, limit: int = 10) -> dict:
    return unwrap_service_result(_service(request).list_active_sessions(limit=max(1, min(limit, 50))))


@router.get("/sessions/{practice_session_id}")
def session_state(practice_session_id: int, request: Request) -> dict:
    result = _service(request).get_session_state(practice_session_id)
    if not result.get("ok"):
        raise APIError(404, "practice_session_not_found", result["error"])
    return {key: value for key, value in result.items() if key != "ok"}


@router.delete("/sessions/{practice_session_id}")
def abandon_session(practice_session_id: int, request: Request) -> dict:
    result = _service(request).abandon_session(practice_session_id)
    if not result.get("ok"):
        raise APIError(404, "practice_session_not_found", result["error"])
    return {key: value for key, value in result.items() if key != "ok"}


@router.post("/answers")
def submit_answer(body: SubmitAnswerRequest, request: Request) -> dict:
    return unwrap_service_result(_service(request).submit_answer(
        session_id=body.practice_session_id,
        question_id=body.question_id,
        answer=body.answer,
    ))


@router.get("/wrong")
def wrong(request: Request, limit: int = 20) -> dict:
    return unwrap_service_result(_service(request).get_wrong_answer_book(limit=limit))


@router.get("/weakness")
def weakness(request: Request) -> dict:
    return unwrap_service_result(_service(request).get_weakness_analysis())


@router.get("/stats")
def stats(request: Request) -> dict:
    return unwrap_service_result(_service(request).get_stats())
