from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.core.exceptions import BusinessLogicError
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
    """Default source until sheets exist: fails loudly instead of returning an empty list."""

    async def load_submitted_sheets(self, *, attempt_id: int) -> Sequence[SheetScore]:  # noqa: ARG002
        raise BusinessLogicError(
            {"code": "sheet_source_not_configured", "message": "assessment sheet source is not configured"}
        )
