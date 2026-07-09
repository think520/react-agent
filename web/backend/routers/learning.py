"""Learning endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from service.learning_service import LearningService
from web.backend.deps import get_workspace

router = APIRouter()


class LearningPlanRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    course: str | None = None
    deadline: str | None = None


class MarkMasteryRequest(BaseModel):
    concept: str = Field(..., min_length=1)
    status: str


class CompleteTaskRequest(BaseModel):
    plan_id: int
    day: int
    task_index: int


class CompleteStepRequest(BaseModel):
    plan_id: int
    day: int


def _service() -> LearningService:
    return LearningService(get_workspace())


def _unwrap(result: dict):
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "request failed"))
    return result


@router.post("/plans")
def generate_plan(request: LearningPlanRequest) -> dict:
    return _unwrap(_service().generate_path(
        goal=request.goal,
        course=request.course,
        deadline=request.deadline,
    ))


@router.get("/progress")
def progress(concept: str | None = None) -> dict:
    return _unwrap(_service().get_progress(concept=concept))


@router.get("/reviews")
def reviews(limit: int = 20) -> dict:
    return _unwrap(_service().get_due_reviews(limit=limit))


@router.post("/mastery")
def mark_mastery(request: MarkMasteryRequest) -> dict:
    return _unwrap(_service().mark_mastery(request.concept, request.status))


@router.get("/plans")
def list_plans(limit: int = 10) -> dict:
    return _unwrap(_service().list_plans(limit=limit))


@router.get("/today")
def today() -> dict:
    return _unwrap(_service().get_today_tasks())


@router.get("/plans/{plan_id}/progress")
def plan_progress(plan_id: int) -> dict:
    return _unwrap(_service().get_plan_progress(plan_id))


@router.post("/plans/complete-task")
def complete_task(request: CompleteTaskRequest) -> dict:
    return _unwrap(_service().complete_task(
        request.plan_id,
        request.day,
        request.task_index,
    ))


@router.post("/plans/complete-step")
def complete_step(request: CompleteStepRequest) -> dict:
    return _unwrap(_service().complete_step(request.plan_id, request.day))
