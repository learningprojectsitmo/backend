from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from src.core.container import get_exam_participation_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.user import User
from src.schema.exam_participation import PG_INTEGER_MAX, ParticipationRead
from src.services.exam_participation_service import ExamParticipationService

exam_participation_router = APIRouter(
    prefix="/workspaces/{workspace_id}/exams/{exam_id}/attempts/{attempt_id}/participation",
    tags=["exam-participation"],
    dependencies=[Depends(setup_audit)],
)


@exam_participation_router.get("", response_model=ParticipationRead)
async def get_participation(
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    attempt_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamParticipationService = Depends(get_exam_participation_service),
):
    return await service.get(workspace_id, exam_id, attempt_id, user)
