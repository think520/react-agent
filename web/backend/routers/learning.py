"""Learning endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from service.learning_service import LearningService
from service.memory_service import MemoryService
from web.backend.deps import get_preferences, get_config, get_request_workspace
from web.backend.errors import unwrap_service_result

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


def _service(request: Request) -> LearningService:
    return LearningService(get_request_workspace(request), config=get_config())


def _unwrap(result: dict):
    return unwrap_service_result(result)


@router.post("/plans")
def generate_plan(body: LearningPlanRequest, request: Request) -> dict:
    return _unwrap(_service(request).generate_path(
        goal=body.goal,
        course=body.course,
        deadline=body.deadline,
    ))


@router.get("/progress")
def progress(request: Request, concept: str | None = None) -> dict:
    return _unwrap(_service(request).get_progress(concept=concept))


@router.get("/reviews")
def reviews(request: Request, limit: int = 20) -> dict:
    return _unwrap(_service(request).get_due_reviews(limit=limit))


@router.get("/review-queue")
def review_queue(request: Request, limit: int = 20) -> dict:
    result = _unwrap(_service(request).get_review_queue(limit=max(1, min(limit, 50))))
    preferences = get_preferences()
    if not preferences.get("memory", {}).get("enabled", True):
        result["personalization"] = []
        return result

    records = [
        *result.get("due_concepts", []),
        *result.get("wrong_answers", []),
        *result.get("weaknesses", []),
    ]
    query = " ".join(
        str(record.get(key) or "")
        for record in records
        for key in ("concept", "question", "title")
    )
    context = MemoryService(get_request_workspace(request)).personalization_context(query)
    content = context.get("content", "").casefold()

    def priority(record: dict) -> int:
        values = [str(record.get(key) or "").strip().casefold() for key in ("concept", "question", "title")]
        return 0 if any(value and value in content for value in values) else 1

    matched = any(priority(record) == 0 for record in records)
    if matched:
        for key in ("due_concepts", "wrong_answers", "weaknesses"):
            result[key] = sorted(result.get(key, []), key=priority)
        result["personalization"] = context.get("references", [])
    else:
        result["personalization"] = []
    return result


@router.post("/mastery")
def mark_mastery(body: MarkMasteryRequest, request: Request) -> dict:
    return _unwrap(_service(request).mark_mastery(body.concept, body.status))


@router.get("/plans")
def list_plans(request: Request, limit: int = 10) -> dict:
    return _unwrap(_service(request).list_plans(limit=limit))


@router.get("/today")
def today(request: Request) -> dict:
    return _unwrap(_service(request).get_today_tasks())


@router.get("/plans/{plan_id}/progress")
def plan_progress(plan_id: int, request: Request) -> dict:
    return _unwrap(_service(request).get_plan_progress(plan_id))


@router.post("/plans/complete-task")
def complete_task(body: CompleteTaskRequest, request: Request) -> dict:
    return _unwrap(_service(request).complete_task(
        body.plan_id,
        body.day,
        body.task_index,
    ))


@router.post("/plans/complete-step")
def complete_step(body: CompleteStepRequest, request: Request) -> dict:
    return _unwrap(_service(request).complete_step(body.plan_id, body.day))
