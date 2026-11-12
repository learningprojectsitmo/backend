from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from src.core.container import get_exam_registration_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.user import User
from src.schema.exam_registration import SlotBatchCreate, SlotListRead, SlotRead
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
