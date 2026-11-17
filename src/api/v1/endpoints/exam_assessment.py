from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from src.core.container import get_exam_assessment_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.user import User
from src.schema.exam_assessment import AssessmentDraftRead, AssessmentDraftWrite, AssessmentFormRead
from src.schema.exam_attempt import PG_INTEGER_MAX
from src.services.exam_assessment_service import ExamAssessmentService

exam_assessment_router = APIRouter(
    prefix="/workspaces/{workspace_id}/exams/{exam_id}/attempts/{attempt_id}/assessment",
    tags=["exam-assessment"],
    dependencies=[Depends(setup_audit)],
)


@exam_assessment_router.get("", response_model=AssessmentFormRead)
async def get_assessment_form(
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    attempt_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamAssessmentService = Depends(get_exam_assessment_service),
):
    return await service.get_form(workspace_id, exam_id, attempt_id, user)


@exam_assessment_router.put("/draft", response_model=AssessmentDraftRead)
async def save_assessment_draft(
    data: AssessmentDraftWrite,
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    attempt_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_current_user),
    service: ExamAssessmentService = Depends(get_exam_assessment_service),
):
    return await service.save_draft(workspace_id, exam_id, attempt_id, user, data)
