from __future__ import annotations

from decimal import Decimal

import pytest
import test_exam_results_db as results_cases
from test_exam_attempts_db import organized, set_settings
from test_exam_results_db import accept, finished_attempt, insert_row, set_participation

from src.core.exceptions import NotFoundError, PermissionError
from src.services.exam_csv_service import ExamCsvService

pytestmark = pytest.mark.integration
seeded_base = results_cases.seeded_base
seeded = results_cases.seeded


async def snapshot(s, *, actor="teacher", workspace=None, exam=0, **kwargs):
    return await ExamCsvService(s["uow"], **kwargs).snapshot(
        workspace or s["workspace"], s["exams"][exam], s["users"][actor]
    )


async def test_register_keeps_registration_without_attempt_and_missing_values(seeded):
    registration = await organized(seeded)
    data = await snapshot(seeded)
    assert len(data.register) == 1
    row = data.register[0]
    assert row["registration_id"] == registration.id
    assert row["attempt_id"] is None and row["calculated_score"] is None and row["final_score"] is None
    assert row["eligible_count"] is None and row["presence"] == "unknown"
    assert row["registration_status"] == "active"


async def test_register_uses_complete_saved_edition_despite_new_settings(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await accept(s, attempt)
    await set_settings(s, max_score=Decimal("100.00"))
    row = (await snapshot(s)).register[0]
    assert (row["calculated_score"], row["final_score"], row["max_score"]) == (
        Decimal("19.00"),
        Decimal("19.00"),
        Decimal("25.00"),
    )
    assert row["settings_version"] == row["result_version"] == 1
    assert row["teacher_weight"] == 60 and row["decided_by_id"] == s["users"]["teacher"].id


async def test_register_manual_zero_without_calculation_is_not_empty(seeded):
    attempt = await finished_attempt(seeded)
    await insert_row(
        seeded, attempt, kind="manual", calculated_score=None, final_score=Decimal(0), reason="Нет голосов"
    )
    row = (await snapshot(seeded)).register[0]
    assert row["final_score"] == 0 and row["calculated_score"] is None
    assert row["decision_state"] == "accepted" and row["result_kind"] == "manual"


@pytest.mark.parametrize("actor", ["local_teacher", "local_admin", "teacher"])
async def test_workspace_teachers_can_export_empty_exam(seeded, actor):
    assert (await snapshot(seeded, actor=actor)).register == []


@pytest.mark.parametrize("actor", ["manager", "member", "local_manager", "demoted", "admin"])
async def test_non_workspace_teachers_cannot_export(seeded, actor):
    with pytest.raises(PermissionError):
        await snapshot(seeded, actor=actor)


async def test_foreign_scope_and_outsider_cannot_export(seeded):
    with pytest.raises(NotFoundError):
        await snapshot(seeded, workspace=seeded["foreign_workspace"])
    with pytest.raises(NotFoundError):
        await snapshot(seeded, actor="outsider")
    await set_participation(seeded, "teacher", local="member")
    with pytest.raises(PermissionError):
        await snapshot(seeded)
