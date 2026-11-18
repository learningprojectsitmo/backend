from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Response

from src.core.container import get_exam_csv_service
from src.core.exam_csv_dependencies import get_exam_csv_user
from src.model.user import User
from src.schema.exam_result import PG_INTEGER_MAX
from src.services.exam_csv_service import ExamCsvService

exam_csv_router = APIRouter(prefix="/workspaces/{workspace_id}/exams/{exam_id}/exports", tags=["exam-csv"])


@exam_csv_router.get(
    "/csv",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}, 413: {"description": "Export exceeds limits"}},
)
async def download_exam_csv(
    workspace_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    exam_id: int = Path(ge=1, le=PG_INTEGER_MAX),
    user: User = Depends(get_exam_csv_user),
    service: ExamCsvService = Depends(get_exam_csv_service),
) -> Response:
    body = await service.download(workspace_id, exam_id, user)
    return Response(
        body,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="exam-{exam_id}-csv.zip"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
