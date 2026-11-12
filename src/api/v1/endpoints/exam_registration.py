from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from src.core.container import get_exam_registration_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.user import User
from src.schema.exam_registration import (
    EventListRead,
    RegistrationCancel,
    RegistrationCreate,
    RegistrationListRead,
    RegistrationMove,
    RegistrationMoveRead,
    RegistrationRead,
    RegistrationStatus,
    SlotBatchCreate,
    SlotListRead,
    SlotRead,
)
from src.services.exam_registration_service import ExamRegistrationService

exam_registration_router = APIRouter(
    prefix="/workspaces/{workspace_id}/exams/{exam_id}", tags=["exam-registration"], dependencies=[Depends(setup_audit)]
)


@exam_registration_router.get("/slots", response_model=SlotListRead)
async def list_slots(
    workspace_id: int = Path(ge=1),
    exam_id: int = Path(ge=1),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    service: ExamRegistrationService = Depends(get_exam_registration_service),
):
    return await service.list_slots(workspace_id, exam_id, user, limit=limit, offset=offset)


@exam_registration_router.post("/slots", response_model=list[SlotRead], status_code=201)
async def add_slots(
    data: SlotBatchCreate,
    workspace_id: int = Path(ge=1),
    exam_id: int = Path(ge=1),
    user: User = Depends(get_current_user),
    service: ExamRegistrationService = Depends(get_exam_registration_service),
):
    return await service.add_slots(workspace_id, exam_id, data, user)


@exam_registration_router.post("/registrations/self", response_model=RegistrationRead, status_code=201)
async def create_self_registration(
    data: RegistrationCreate,
    workspace_id: int = Path(ge=1),
    exam_id: int = Path(ge=1),
    user: User = Depends(get_current_user),
    service: ExamRegistrationService = Depends(get_exam_registration_service),
):
    return await service.create_self(workspace_id, exam_id, data, user)


@exam_registration_router.get("/registrations/self", response_model=RegistrationListRead)
async def list_self_registrations(
    workspace_id: int = Path(ge=1),
    exam_id: int = Path(ge=1),
    project_id: int | None = Query(None, ge=1),
    status: RegistrationStatus | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    service: ExamRegistrationService = Depends(get_exam_registration_service),
):
    return await service.list_self(
        workspace_id, exam_id, user, project_id=project_id, status=status, limit=limit, offset=offset
    )


@exam_registration_router.post("/registrations/{registration_id}/self-cancel", response_model=RegistrationRead)
async def cancel_self_registration(
    data: RegistrationCancel,
    workspace_id: int = Path(ge=1),
    exam_id: int = Path(ge=1),
    registration_id: int = Path(ge=1),
    user: User = Depends(get_current_user),
    service: ExamRegistrationService = Depends(get_exam_registration_service),
):
    return await service.cancel_self(workspace_id, exam_id, registration_id, data, user)


@exam_registration_router.post("/registrations/{registration_id}/self-move", response_model=RegistrationMoveRead)
async def move_self_registration(
    data: RegistrationMove,
    workspace_id: int = Path(ge=1),
    exam_id: int = Path(ge=1),
    registration_id: int = Path(ge=1),
    user: User = Depends(get_current_user),
    service: ExamRegistrationService = Depends(get_exam_registration_service),
):
    return await service.move_self(workspace_id, exam_id, registration_id, data, user)


@exam_registration_router.get("/registrations/{registration_id}/history", response_model=EventListRead)
async def registration_history(
    workspace_id: int = Path(ge=1),
    exam_id: int = Path(ge=1),
    registration_id: int = Path(ge=1),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    service: ExamRegistrationService = Depends(get_exam_registration_service),
):
    return await service.history(workspace_id, exam_id, registration_id, user, limit=limit, offset=offset)
