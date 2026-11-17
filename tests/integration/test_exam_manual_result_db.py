from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest
import test_exam_assessment_submit_db as submit_cases
import test_exam_results_db as results_cases
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_exam_results_db import (
    AFTER_WINDOW,
    NOW,
    accept,
    code_of,
    finished_attempt,
    publish,
    result_service,
    set_participation,
)
from test_exam_results_db import count as count_rows

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError, ValidationError
from src.schema.exam_result import ResultManual, ResultPublish

pytestmark = pytest.mark.integration

# Fixtures are shared with the result tests.
seeded_base = results_cases.seeded_base
seeded = results_cases.seeded

EDITION_SQL = (
    "SELECT version, kind, calculated_score, final_score, reason, decided_by, published_at "
    "FROM exam_result_edition ORDER BY version"
)


async def manual(
    s, attempt, score="20", *, version=0, reason="Устная защита", now=AFTER_WINDOW, sheets=None, actor="teacher", exam=0
):
    async with s["uow"]() as u:
        return await result_service(u, now=now, sheets=sheets).manual(
            s["workspace"],
            s["exams"][exam],
            attempt.id,
            ResultManual(expected_version=version, final_score=score, reason=reason),
            s["users"][actor],
        )


async def rows(s):
    async with s["engine"].connect() as connection:
        return [tuple(row) for row in (await connection.execute(text(EDITION_SQL))).all()]


async def test_manual_is_stored_with_both_values_reason_and_snapshot(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    result = await manual(s, attempt, "17.5")
    edition = result.edition
    assert (edition.version, edition.kind) == (1, "manual")
    assert (edition.calculated_score, edition.final_score) == (Decimal("19.00"), Decimal("17.50"))
    assert edition.reason == "Устная защита" and edition.decided_by == s["users"]["teacher"].id
    assert edition.decided_at == AFTER_WINDOW and edition.snapshot.sheet_max == 5
    assert (edition.snapshot.max_score, edition.snapshot.settings_version) == (Decimal("25.00"), 1)
    assert await rows(s) == [
        (1, "manual", Decimal("19.00"), Decimal("17.50"), "Устная защита", s["users"]["teacher"].id, None)
    ]


async def test_manual_without_calculation_is_stored_with_null_calculated_score(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    assert await code_of(accept(s, attempt, sheets=[])) == "no_calculation"
    result = await manual(s, attempt, "12", sheets=[])
    assert result.edition.calculated_score is None and result.edition.snapshot.used_weight == 0
    assert (await rows(s))[0][:4] == (1, "manual", None, Decimal("12.00"))


async def test_range_is_checked_against_current_max_score(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    with pytest.raises(ValidationError) as error:
        await manual(s, attempt, "25.01")
    assert error.value.detail["code"] == "final_score_out_of_range"
    assert await count_rows(s, "exam_result_edition") == 0
    for score in ("0", "25"):
        version = await count_rows(s, "exam_result_edition")
        await manual(s, attempt, score, version=version)
    assert [row[3] for row in await rows(s)] == [Decimal("0.00"), Decimal("25.00")]


async def test_window_and_attempt_conditions_are_the_same_as_for_accept(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    assert await code_of(manual(s, attempt, now=NOW)) == "assessment_window_open"
    registration = await results_cases.organized(s, project="manager2")
    unfinished, _ = await results_cases.start(s, registration, now=NOW + timedelta(minutes=30))
    assert await code_of(manual(s, unfinished)) == "attempt_not_finished"
    assert await count_rows(s, "exam_result_edition") == 0


async def test_versions_are_append_only_and_old_editions_are_untouched(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await manual(s, attempt, "10")
    first = await rows(s)
    await accept(s, attempt, version=1, reason="Пересчёт")
    await manual(s, attempt, "21", version=2, reason="Итог пересмотрен")
    final = await rows(s)
    assert final[0] == first[0]
    assert [(r[0], r[1], r[3]) for r in final] == [
        (1, "manual", Decimal("10.00")),
        (2, "calculated", Decimal("19.00")),
        (3, "manual", Decimal("21.00")),
    ]
    assert await code_of(manual(s, attempt, version=1)) == "result_version_conflict"
    assert await count_rows(s, "exam_result_edition") == 3


async def test_publish_works_for_manual_edition(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await manual(s, attempt, "18")
    published = await publish(s, attempt)
    assert published.edition.kind == "manual" and published.edition.published_at == AFTER_WINDOW
    assert (await rows(s))[0][6] == AFTER_WINDOW


async def test_concurrent_double_manual_stores_exactly_one_edition(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    results = await asyncio.gather(manual(s, attempt, "10"), manual(s, attempt, "11"), return_exceptions=True)
    ok = [r for r in results if not isinstance(r, Exception)]
    failed = [r for r in results if isinstance(r, BusinessLogicError)]
    assert len(ok) == 1 and len(failed) == 1
    assert failed[0].detail["code"] == "result_version_conflict"
    assert await count_rows(s, "exam_result_edition") == 1


async def test_concurrent_manual_and_accept_store_exactly_one_edition(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    results = await asyncio.gather(manual(s, attempt, "10"), accept(s, attempt), return_exceptions=True)
    assert sum(isinstance(r, BusinessLogicError) for r in results) == 1
    assert await count_rows(s, "exam_result_edition") == 1


@pytest.mark.parametrize("actor", ["manager", "member", "admin", "demoted"])
async def test_non_teachers_cannot_set_manual_result(seeded, actor):
    # `admin` is a global admin without participation: no effective role in this workspace (403).
    s = seeded
    attempt = await finished_attempt(s)
    with pytest.raises(PermissionError):
        await manual(s, attempt, actor=actor)
    assert await count_rows(s, "exam_result_edition") == 0


async def test_local_member_with_global_teacher_role_is_forbidden(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await set_participation(s, "outsider", local="member")
    with pytest.raises(PermissionError):
        await manual(s, attempt, actor="outsider")


async def test_isolation_and_local_roles(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    with pytest.raises(NotFoundError):
        await manual(s, attempt, actor="outsider")  # global teacher who does not see the workspace
    with pytest.raises(NotFoundError):
        await manual(s, attempt, exam=1)  # exam of another workspace scope
    await manual(s, attempt, actor="local_teacher")
    await manual(s, attempt, "15", version=1, actor="local_admin")
    assert await count_rows(s, "exam_result_edition") == 2


@pytest.mark.parametrize("reason", [None, "", "   "])
async def test_database_requires_a_reason_for_manual_editions(seeded, reason):
    s = seeded
    attempt = await finished_attempt(s)
    with pytest.raises(IntegrityError) as error:
        await results_cases.insert_row(
            s, attempt, kind="manual", calculated_score=None, final_score=Decimal("7.50"), reason=reason
        )
    assert "ck_result_edition_manual_reason" in str(error.value) or "ck_result_edition_reason_nonblank" in str(
        error.value
    )
    assert await count_rows(s, "exam_result_edition") == 0


async def test_end_to_end_with_real_sheet_source(seeded):
    """Nobody voted -> accept 409 -> manual v1 (no calculation) -> publish; votes -> accept v2 -> manual v3."""
    s = seeded
    attempt = await finished_attempt(s)
    submit = submit_cases

    def service(u):
        return submit.result_service(u)

    async with s["uow"]() as u:
        with pytest.raises(BusinessLogicError) as error:
            await service(u).accept(
                s["workspace"],
                s["exams"][0],
                attempt.id,
                results_cases.ResultAccept(expected_version=0),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "no_calculation"

    async with s["uow"]() as u:
        first = await service(u).manual(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            ResultManual(expected_version=0, final_score="13.5", reason="Никто не оценивал"),
            s["users"]["teacher"],
        )
    assert (first.edition.version, first.edition.kind) == (1, "manual")
    assert first.edition.calculated_score is None and first.outdated is False
    async with s["uow"]() as u:
        published = await service(u).publish(
            s["workspace"], s["exams"][0], attempt.id, ResultPublish(expected_version=1), s["users"]["teacher"]
        )
    assert published.edition.published_by == s["users"]["teacher"].id
    before = await rows(s)

    for actor, score in [("local_teacher", 4), ("local_manager", 3), ("member", 5)]:
        await submit.draft(s, attempt, actor, score)
        await submit.submit(s, attempt, actor)
    async with s["uow"]() as u:
        read = await service(u).get(s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"])
    assert read.outdated is True and read.edition.final_score == Decimal("13.50")

    async with s["uow"]() as u:
        second = await service(u).accept(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            results_cases.ResultAccept(expected_version=1, reason="Листы отправлены"),
            s["users"]["teacher"],
        )
    assert (second.edition.version, second.edition.final_score) == (2, Decimal("19.00"))
    async with s["uow"]() as u:
        third = await service(u).manual(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            ResultManual(expected_version=2, final_score="20", reason="Корректировка преподавателя"),
            s["users"]["teacher"],
        )
    assert (third.edition.version, third.edition.kind) == (3, "manual")
    assert (third.edition.calculated_score, third.edition.final_score) == (Decimal("19.00"), Decimal("20.00"))
    assert third.outdated is False
    after = await rows(s)
    assert after[0] == before[0] and len(after) == 3
    assert after[1][:4] == (2, "calculated", Decimal("19.00"), Decimal("19.00"))
