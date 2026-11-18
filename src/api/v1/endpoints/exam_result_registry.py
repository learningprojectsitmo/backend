from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from src.core.container import get_exam_result_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.user import User
from src.schema.exam_result import PG_INTEGER_MAX, ResultRegistryRead, ResultRegistryState
from src.services.exam_result_service import ExamResultService

exam_result_registry_router = APIRouter(
    prefix="/workspaces/{workspace_id}/exams/{exam_id}/results",
    tags=["exam-result"],
    dependencies=[Depends(setup_audit)],
)


@exam_result_registry_router.get("", response_model=ResultRegistryRead)
async def list_exam_results(
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    q: str | None = Query(None, max_length=200),
    state: ResultRegistryState | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    service: ExamResultService = Depends(get_exam_result_service),
):
    return await service.registry(workspace_id, exam_id, user, q=q, state=state, limit=limit, offset=offset)
