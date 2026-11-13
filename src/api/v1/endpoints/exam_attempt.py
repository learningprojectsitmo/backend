from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Response

from src.core.container import get_exam_attempt_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.user import User
from src.schema.exam_attempt import (
    PG_INTEGER_MAX,
    AttemptCommand,
    AttemptEventListRead,
    AttemptPause,
    AttemptRead,
    AttemptStart,
    CurrentAttemptRead,
)
from src.services.exam_attempt_service import ExamAttemptService

exam_attempt_router = APIRouter(
    prefix="/workspaces/{workspace_id}/exams/{exam_id}/attempts",
    tags=["exam-attempt"],
    dependencies=[Depends(setup_audit)],
)


@exam_attempt_router.post(
    "", response_model=AttemptRead, responses={201: {"model": AttemptRead, "description": "Attempt created"}}
)
async def start_attempt(
    data: AttemptStart,
    response: Response,
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_exam_attempt_service),
):
    attempt, created = await service.start(workspace_id, exam_id, data, user)
    response.status_code = 201 if created else 200
    return attempt


@exam_attempt_router.get("/current", response_model=CurrentAttemptRead)
async def current_attempt(
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_exam_attempt_service),
):
    return await service.current(workspace_id, exam_id, user)


@exam_attempt_router.get("/{attempt_id}", response_model=AttemptRead)
async def get_attempt(
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    attempt_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_exam_attempt_service),
):
    return await service.get(workspace_id, exam_id, attempt_id, user)


@exam_attempt_router.post("/{attempt_id}/questions", response_model=AttemptRead)
async def questions_attempt(
    data: AttemptCommand,
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    attempt_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_exam_attempt_service),
):
    return await service.questions(workspace_id, exam_id, attempt_id, data, user)


@exam_attempt_router.post("/{attempt_id}/pause", response_model=AttemptRead)
async def pause_attempt(
    data: AttemptPause,
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    attempt_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_exam_attempt_service),
):
    return await service.pause(workspace_id, exam_id, attempt_id, data, user)


@exam_attempt_router.post("/{attempt_id}/resume", response_model=AttemptRead)
async def resume_attempt(
    data: AttemptCommand,
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    attempt_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_exam_attempt_service),
):
    return await service.resume(workspace_id, exam_id, attempt_id, data, user)


@exam_attempt_router.post("/{attempt_id}/finish", response_model=AttemptRead)
async def finish_attempt(
    data: AttemptCommand,
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    attempt_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_exam_attempt_service),
):
    return await service.finish(workspace_id, exam_id, attempt_id, data, user)


@exam_attempt_router.get("/{attempt_id}/events", response_model=AttemptEventListRead)
async def attempt_events(
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    attempt_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamAttemptService = Depends(get_exam_attempt_service),
):
    return await service.events(workspace_id, exam_id, attempt_id, user, limit=limit, offset=offset)
