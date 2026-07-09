"""Quiz endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from service.quiz_service import QuizService
from web.backend.deps import get_workspace

router = APIRouter()


class GenerateQuestionsRequest(BaseModel):
    query: str = Field(..., min_length=1)
    course: str | None = None
    count: int = 5


class StartQuizRequest(BaseModel):
    count: int = 5
    course: str | None = None
    question_type: str | None = None


class SubmitAnswerRequest(BaseModel):
    session_id: int
    question_id: int
    answer: str


def _service() -> QuizService:
    return QuizService(get_workspace())


def _unwrap(result: dict):
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "request failed"))
    return result


@router.post("/questions")
def generate_questions(request: GenerateQuestionsRequest) -> dict:
    return _unwrap(_service().generate_questions(
        query=request.query,
        course=request.course,
        count=request.count,
    ))


@router.post("/sessions")
def start_quiz(request: StartQuizRequest) -> dict:
    return _unwrap(_service().start_quiz(
        count=request.count,
        course=request.course,
        question_type=request.question_type,
    ))


@router.post("/answers")
def submit_answer(request: SubmitAnswerRequest) -> dict:
    return _unwrap(_service().submit_answer(
        session_id=request.session_id,
        question_id=request.question_id,
        answer=request.answer,
    ))


@router.get("/wrong")
def wrong(limit: int = 20) -> dict:
    return _unwrap(_service().get_wrong_answer_book(limit=limit))


@router.get("/weakness")
def weakness() -> dict:
    return _unwrap(_service().get_weakness_analysis())


@router.get("/stats")
def stats() -> dict:
    return _unwrap(_service().get_stats())
