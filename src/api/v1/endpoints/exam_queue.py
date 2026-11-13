from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from src.core.container import get_exam_queue_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.user import User
from src.schema.exam_attempt import PG_INTEGER_MAX
from src.schema.exam_queue import QueueCommand, QueueMutationRead, QueuePlace, QueueRead, QueueReason
from src.services.exam_queue_service import ExamQueueService

exam_queue_router = APIRouter(
    prefix="/workspaces/{workspace_id}/exams/{exam_id}/queue",
    tags=["exam-queue"],
    dependencies=[Depends(setup_audit)],
)


@exam_queue_router.get("", response_model=QueueRead)
async def read_queue(
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamQueueService = Depends(get_exam_queue_service),
):
    return await service.read(workspace_id, exam_id, user)


@exam_queue_router.post("/{registration_id}/place", response_model=QueueMutationRead)
async def place_registration(
    data: QueuePlace,
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    registration_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamQueueService = Depends(get_exam_queue_service),
):
    return await service.place(workspace_id, exam_id, registration_id, data, user)


@exam_queue_router.post("/{registration_id}/next", response_model=QueueMutationRead)
async def place_registration_next(
    data: QueueCommand,
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    registration_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamQueueService = Depends(get_exam_queue_service),
):
    return await service.next(workspace_id, exam_id, registration_id, data, user)


@exam_queue_router.post("/{registration_id}/postpone", response_model=QueueMutationRead)
async def postpone_registration(
    data: QueueReason,
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    registration_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamQueueService = Depends(get_exam_queue_service),
):
    return await service.postpone(workspace_id, exam_id, registration_id, data, user)


@exam_queue_router.post("/{registration_id}/no-show", response_model=QueueMutationRead)
async def no_show_registration(
    data: QueueReason,
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    registration_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamQueueService = Depends(get_exam_queue_service),
):
    return await service.no_show(workspace_id, exam_id, registration_id, data, user)
