from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from src.core.container import get_exam_result_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.user import User
from src.schema.exam_result import (
    PG_INTEGER_MAX,
    ResultAccept,
    ResultEditionListRead,
    ResultPublish,
    ResultRead,
)
from src.services.exam_result_service import ExamResultService

exam_result_router = APIRouter(
    prefix="/workspaces/{workspace_id}/exams/{exam_id}/attempts/{attempt_id}/result",
    tags=["exam-result"],
    dependencies=[Depends(setup_audit)],
)


@exam_result_router.get("", response_model=ResultRead)
async def get_result(
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    attempt_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamResultService = Depends(get_exam_result_service),
):
    return await service.get(workspace_id, exam_id, attempt_id, user)


@exam_result_router.get("/editions", response_model=ResultEditionListRead)
async def list_result_editions(
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    attempt_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamResultService = Depends(get_exam_result_service),
):
    return await service.editions(workspace_id, exam_id, attempt_id, user)


@exam_result_router.post("/accept", response_model=ResultRead)
async def accept_result(
    data: ResultAccept,
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    attempt_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamResultService = Depends(get_exam_result_service),
):
    return await service.accept(workspace_id, exam_id, attempt_id, data, user)


@exam_result_router.post("/publish", response_model=ResultRead)
async def publish_result(
    data: ResultPublish,
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    attempt_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamResultService = Depends(get_exam_result_service),
):
    return await service.publish(workspace_id, exam_id, attempt_id, data, user)
