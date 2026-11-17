from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.core.exceptions import BusinessLogicError
from src.repository.exam_assessment_repository import ExamAssessmentRepository
from src.services.exam_score import SheetScore


class ExamSheetSource(Protocol):
    """Supplies assessment sheets of one attempt to the result calculation.

    Contract for implementations (#111/#112):
    - only SUBMITTED sheets: no drafts, no sheets of excluded assessors;
    - one sheet per assessor: the latest valid edition of that assessor's sheet;
    - SheetScore.role comes from the audience snapshot taken when the assessment window opened,
      never from the client; SheetScore.total is the sum of the criteria scores of the sheet;
    - runs in the caller's unit of work (same session, no commit of its own);
    - an empty result means "nobody voted", not "unknown": fail loudly when the data is unavailable.
    """

    async def load_submitted_sheets(self, *, attempt_id: int) -> Sequence[SheetScore]: ...


class UnconfiguredExamSheetSource:
    """Test double that fails loudly instead of returning an empty list; not wired by default."""

    async def load_submitted_sheets(self, *, attempt_id: int) -> Sequence[SheetScore]:  # noqa: ARG002
        raise BusinessLogicError(
            {"code": "sheet_source_not_configured", "message": "assessment sheet source is not configured"}
        )


class SubmittedSheetSource:
    """Real source: latest submitted edition of every admitted assessor, role from the audience snapshot."""

    def __init__(self, repository: ExamAssessmentRepository):
        self._repository = repository

    async def load_submitted_sheets(self, *, attempt_id: int) -> Sequence[SheetScore]:
        window = await self._repository.window_for_attempt(attempt_id)
        if window is None:
            raise BusinessLogicError({"code": "assessment_window_missing", "message": "assessment window missing"})
        if not await self._repository.has_audience(window.id, window.workspace_id):
            raise BusinessLogicError(
                {
                    "code": "audience_snapshot_unavailable",
                    "message": "Historical audience is unavailable for this assessment window",
                }
            )
        rows = await self._repository.counted_sheets(attempt_id)
        return [SheetScore(role=role, total=total) for role, total in rows]
