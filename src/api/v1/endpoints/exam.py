from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Path, Query

from src.core.container import get_exam_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.user import User
from src.schema.exam import (
    ExamCreate,
    ExamListRead,
    ExamPublish,
    ExamRead,
    ExamSettingsHistoryRead,
    ExamSettingsReplace,
    ExamSettingsRevisionRead,
)
from src.services.exam_service import ExamService

exam_router = APIRouter(prefix="/workspaces/{workspace_id}/exams", tags=["exam"], dependencies=[Depends(setup_audit)])


@exam_router.post("", response_model=ExamRead, status_code=201)
async def create_exam(
    data: ExamCreate,
    workspace_id: int = Path(ge=1),
    user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
):
    return await service.create(workspace_id, data, user)


@exam_router.get("", response_model=ExamListRead)
async def list_exams(
    workspace_id: int = Path(ge=1),
    status: Literal["draft", "published"] | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
):
    return await service.list(workspace_id, user, status=status, limit=limit, offset=offset)


@exam_router.get("/{exam_id}", response_model=ExamRead)
async def get_exam(
    workspace_id: int = Path(ge=1),
    exam_id: int = Path(ge=1),
    user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
):
    return await service.get(workspace_id, exam_id, user)


@exam_router.put("/{exam_id}/settings", response_model=ExamRead)
async def replace_exam_settings(
    data: ExamSettingsReplace,
    workspace_id: int = Path(ge=1),
    exam_id: int = Path(ge=1),
    user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
):
    return await service.replace_settings(workspace_id, exam_id, data, user)


@exam_router.post("/{exam_id}/publish", response_model=ExamRead)
async def publish_exam(
    data: ExamPublish,
    workspace_id: int = Path(ge=1),
    exam_id: int = Path(ge=1),
    user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
):
    return await service.publish(workspace_id, exam_id, data, user)


@exam_router.get("/{exam_id}/settings", response_model=ExamSettingsHistoryRead)
async def list_exam_settings(
    workspace_id: int = Path(ge=1),
    exam_id: int = Path(ge=1),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
):
    return await service.list_settings(workspace_id, exam_id, user, limit=limit, offset=offset)


@exam_router.get("/{exam_id}/settings/{version}", response_model=ExamSettingsRevisionRead)
async def get_exam_settings(
    workspace_id: int = Path(ge=1),
    exam_id: int = Path(ge=1),
    version: int = Path(ge=1),
    user: User = Depends(get_current_user),
    service: ExamService = Depends(get_exam_service),
):
    return await service.get_settings(workspace_id, exam_id, version, user)
