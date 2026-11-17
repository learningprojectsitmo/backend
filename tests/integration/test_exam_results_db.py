from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
import test_exam_attempts_db as attempt_cases
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_exam_attempts_db import NOW, count, finish, organized, set_settings, start

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_repository import ExamRepository
from src.repository.exam_result_repository import ExamResultRepository
from src.repository.project_repository import ProjectRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.repository.workspace_repository import WorkSpaceRepository
from src.schema.exam import ExamWeights
from src.schema.exam_result import ResultAccept, ResultPublish
from src.services.exam_result_service import ExamResultService
from src.services.exam_score import SheetScore
from src.services.exam_service import ExamService
from src.services.project_relations import ProjectRelationsService

pytestmark = pytest.mark.integration


seeded_base = attempt_cases.seeded


@pytest_asyncio.fixture(loop_scope="function")
async def seeded(seeded_base):
    """Seeded workspace where the author-teacher also participates (NULL local role -> global teacher).

    Result operations need *participation* with an effective teacher/admin role, and the shared
    fixture only makes `teacher` the workspace author, so the participation row is added here.
    """
    s = seeded_base
    await set_participation(s, "teacher", local=None)
    return s


async def set_participation(s, name, *, local: str | None | bool):
    """Create/replace a participation row; `local=False` removes it, `None` makes the role NULL."""
    user_id = s["users"][name].id
    async with s["uow"]() as u:
        await u.session.execute(
            text("DELETE FROM workspace_participation WHERE workspace_id = :w AND participant_id = :u"),
            {"w": s["workspace"], "u": user_id},
        )
        if local is not False:
            await u.session.execute(
                text(
                    "INSERT INTO workspace_participation (workspace_id, participant_id, role_id) "
                    "VALUES (:w, :u, (SELECT id FROM role WHERE name = :r))"
                ),
                {"w": s["workspace"], "u": user_id, "r": local},
            )


AFTER_WINDOW = NOW + timedelta(minutes=10 + 3)


class Sheets:
    def __init__(self, sheets):
        self.sheets = sheets

    async def load_submitted_sheets(self, *, attempt_id):  # noqa: ARG002
        return self.sheets


# Seeded type has one question, so the sheet maximum is 5 and max_score defaults to 25.
DEFAULT_SHEETS = [SheetScore("teacher", 4), SheetScore("manager", 3), SheetScore("member", 5)]


def result_service(uow, *, now=AFTER_WINDOW, sheets=None):
    return ExamResultService(
        ExamResultRepository(uow),
        ExamAttemptRepository(uow),
        ExamRepository(uow),
        ExamService(ExamRepository(uow), ProjectTypeQuestionRepository(uow)),
        Sheets(DEFAULT_SHEETS if sheets is None else sheets),
        ProjectRelationsService(ProjectRepository(uow), WorkSpaceRepository(uow)),
        clock=lambda: now,
    )


async def finished_attempt(s, *, project="manager"):
    registration = await organized(s, project=project)
    attempt, _ = await start(s, registration)
    await finish(s, attempt, now=NOW + timedelta(minutes=10))
    return attempt


async def accept(s, attempt, *, version=0, reason=None, now=AFTER_WINDOW, sheets=None, actor="teacher", exam=0):
    async with s["uow"]() as u:
        return await result_service(u, now=now, sheets=sheets).accept(
            s["workspace"],
            s["exams"][exam],
            attempt.id,
            ResultAccept(expected_version=version, reason=reason),
            s["users"][actor],
        )


async def publish(s, attempt, *, version=1, now=AFTER_WINDOW, actor="teacher"):
    async with s["uow"]() as u:
        return await result_service(u, now=now).publish(
            s["workspace"], s["exams"][0], attempt.id, ResultPublish(expected_version=version), s["users"][actor]
        )


async def code_of(awaitable):
    with pytest.raises(BusinessLogicError) as error:
        await awaitable
    return error.value.detail["code"]


async def test_accept_stores_first_edition_with_snapshot(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    result = await accept(s, attempt)
    edition = result.edition
    assert (edition.version, edition.kind) == (1, "calculated")
    assert edition.calculated_score == edition.final_score == Decimal("19.00")
    assert edition.snapshot.weights == ExamWeights(teacher=60, manager=30, member=10)
    assert (edition.snapshot.max_score, edition.snapshot.sheet_max, edition.snapshot.settings_version) == (
        Decimal("25.00"),
        5,
        1,
    )
    assert edition.decided_by == s["users"]["teacher"].id and edition.decided_at == AFTER_WINDOW
    assert await count(s, "exam_result_edition") == 1


async def test_accept_before_window_closes_is_rejected_and_stores_nothing(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    assert await code_of(accept(s, attempt, now=NOW + timedelta(minutes=12))) == "assessment_window_open"
    assert await count(s, "exam_result_edition") == 0


async def test_accept_of_unfinished_attempt_is_rejected(seeded):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    assert await code_of(accept(s, attempt)) == "attempt_not_finished"


async def test_no_calculation_is_rejected_without_row(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    assert await code_of(accept(s, attempt, sheets=[])) == "no_calculation"
    assert await count(s, "exam_result_edition") == 0


async def test_new_decision_is_a_new_version_and_old_one_is_untouched(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await accept(s, attempt)
    await set_settings(s, weights=ExamWeights(teacher=20, manager=40, member=40))
    second = await accept(s, attempt, version=1, reason="Новые веса")
    assert second.edition.version == 2 and second.edition.final_score == Decimal("20.00")
    async with s["engine"].connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT version, final_score, teacher_weight, settings_version FROM exam_result_edition ORDER BY version"
                )
            )
        ).all()
    assert [tuple(row) for row in rows] == [(1, Decimal("19.00"), 60, 1), (2, Decimal("20.00"), 20, 2)]


async def test_stale_version_conflicts(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await accept(s, attempt)
    assert await code_of(accept(s, attempt, version=0)) == "result_version_conflict"
    assert await count(s, "exam_result_edition") == 1


async def test_concurrent_double_accept_stores_exactly_one_edition(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    results = await asyncio.gather(accept(s, attempt), accept(s, attempt), return_exceptions=True)
    ok = [r for r in results if not isinstance(r, Exception)]
    failed = [r for r in results if isinstance(r, BusinessLogicError)]
    assert len(ok) == 1 and len(failed) == 1
    assert failed[0].detail["code"] == "result_version_conflict"
    assert await count(s, "exam_result_edition") == 1


async def test_get_shows_stored_snapshot_and_outdated_preliminary(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await accept(s, attempt)
    async with s["uow"]() as u:
        result = await result_service(u, sheets=[*DEFAULT_SHEETS, SheetScore("member", 1)]).get(
            s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"]
        )
    assert result.edition.final_score == Decimal("19.00")
    assert result.preliminary.score == Decimal("18.00") and result.outdated is True


async def test_publish_marks_once_and_is_idempotent(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await accept(s, attempt)
    first = await publish(s, attempt, now=AFTER_WINDOW + timedelta(minutes=1))
    again = await publish(s, attempt, now=AFTER_WINDOW + timedelta(hours=1), actor="local_admin")
    assert first.edition.published_at == AFTER_WINDOW + timedelta(minutes=1)
    assert again.edition.published_at == first.edition.published_at
    assert again.edition.published_by == s["users"]["teacher"].id


async def test_concurrent_publish_keeps_one_mark(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await accept(s, attempt)
    await asyncio.gather(publish(s, attempt), publish(s, attempt, actor="local_admin"))
    async with s["engine"].connect() as connection:
        rows = (await connection.execute(text("SELECT published_at, published_by FROM exam_result_edition"))).all()
    assert len(rows) == 1 and rows[0][0] is not None and rows[0][1] is not None


async def test_editions_listing_is_ascending(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await accept(s, attempt)
    await accept(s, attempt, version=1, reason="Повторное решение")
    async with s["uow"]() as u:
        listed = await result_service(u).editions(s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"])
    assert [item.version for item in listed.items] == [1, 2]


async def test_permissions_and_isolation(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    with pytest.raises(PermissionError):
        await accept(s, attempt, actor="manager")
    with pytest.raises(NotFoundError):
        await accept(s, attempt, actor="outsider")
    with pytest.raises(NotFoundError):
        await accept(s, attempt, exam=1)
    assert await count(s, "exam_result_edition") == 0
    await accept(s, attempt, actor="local_teacher")
    await accept(s, attempt, version=1, reason="Админ", actor="local_admin")
    assert await count(s, "exam_result_edition") == 2


async def all_calls(s, attempt, actor):
    """Run every result operation as *actor*; return the exception class (or None) per operation."""
    outcomes = {}
    user = s["users"][actor]
    ids = (s["workspace"], s["exams"][0], attempt.id)
    calls = {
        "get": lambda u: result_service(u).get(*ids, user),
        "editions": lambda u: result_service(u).editions(*ids, user),
        "accept": lambda u: result_service(u).accept(*ids, ResultAccept(expected_version=0), user),
        "publish": lambda u: result_service(u).publish(*ids, ResultPublish(expected_version=1), user),
    }
    for name, call in calls.items():
        try:
            async with s["uow"]() as u:
                await call(u)
        except (PermissionError, NotFoundError, BusinessLogicError) as error:
            outcomes[name] = type(error)
    return outcomes


@pytest.mark.parametrize("actor", ["admin", "manager", "member", "demoted"])
async def test_global_admin_outside_workspace_and_participants_are_forbidden(seeded, actor):
    # `admin` has the global admin role but no participation in the workspace: no access (403, not 404,
    # because the exam is visible to a global admin; the role check then fails).
    s = seeded
    attempt = await finished_attempt(s)
    outcomes = await all_calls(s, attempt, actor)
    assert outcomes == dict.fromkeys(["get", "editions", "accept", "publish"], PermissionError)
    assert await count(s, "exam_result_edition") == 0


@pytest.mark.parametrize("local", ["teacher", "admin", None])
async def test_effective_teacher_or_admin_of_the_workspace_may_decide_and_publish(seeded, local):
    # `outsider` is a global teacher: local teacher/admin and NULL (-> global teacher) all qualify.
    s = seeded
    attempt = await finished_attempt(s)
    await set_participation(s, "outsider", local=local)
    await accept(s, attempt, actor="outsider")
    published = await publish(s, attempt, actor="outsider")
    assert published.edition.published_by == s["users"]["outsider"].id


async def test_local_member_beats_global_teacher_role(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await set_participation(s, "outsider", local="member")
    outcomes = await all_calls(s, attempt, "outsider")
    assert outcomes == dict.fromkeys(["get", "editions", "accept", "publish"], PermissionError)


async def test_non_participant_global_teacher_cannot_see_the_workspace(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    outcomes = await all_calls(s, attempt, "outsider")
    assert outcomes == dict.fromkeys(["get", "editions", "accept", "publish"], NotFoundError)


async def test_workspace_author_without_participation_is_forbidden(seeded):
    # The author-teacher sees the workspace but without participation has no effective role.
    s = seeded
    attempt = await finished_attempt(s)
    await set_participation(s, "teacher", local=False)
    outcomes = await all_calls(s, attempt, "teacher")
    assert outcomes == dict.fromkeys(["get", "editions", "accept", "publish"], PermissionError)


async def test_foreign_attempt_or_exam_is_not_found_for_a_teacher(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    with pytest.raises(NotFoundError):
        await accept(s, attempt, exam=1)
    async with s["uow"]() as u:
        with pytest.raises(NotFoundError):
            await result_service(u).get(s["workspace"], s["exams"][0], attempt.id + 999, s["users"]["teacher"])


async def insert_row(s, attempt, **overrides):
    values = {
        "workspace_id": s["workspace"],
        "exam_id": s["exams"][0],
        "attempt_id": attempt.id,
        "version": 1,
        "kind": "calculated",
        "calculated_score": Decimal("19.00"),
        "final_score": Decimal("19.00"),
        "settings_version": 1,
        "teacher_weight": 60,
        "manager_weight": 30,
        "member_weight": 10,
        "max_score": Decimal("25.00"),
        "sheet_max": 5,
        "teacher_sheets": 1,
        "manager_sheets": 1,
        "member_sheets": 1,
        "used_weight": 100,
        "reason": None,
        "decided_by": s["users"]["teacher"].id,
        "decided_at": AFTER_WINDOW,
        "published_at": None,
        "published_by": None,
    }
    values.update(overrides)
    columns = ", ".join(values)
    params = ", ".join(f":{key}" for key in values)
    async with s["engine"].begin() as connection:
        await connection.execute(text(f"INSERT INTO exam_result_edition ({columns}) VALUES ({params})"), values)


@pytest.mark.parametrize(
    "overrides,constraint",
    [
        ({"kind": "other"}, "ck_result_edition_kind"),
        ({"version": 0, "reason": "Причина"}, "ck_result_edition_version"),
        ({"version": 2, "reason": None}, "ck_result_edition_reason_required"),
        ({"reason": "   "}, "ck_result_edition_reason_nonblank"),
        ({"teacher_weight": 50}, "ck_result_edition_weights"),
        ({"kind": "manual", "final_score": Decimal("26.00")}, "ck_result_edition_final_range"),
        ({"final_score": Decimal("18.00")}, "ck_result_edition_calculated_kind"),
        ({"calculated_score": None}, "ck_result_edition_calculated_kind"),
        (
            {"max_score": Decimal("0"), "calculated_score": Decimal("0"), "final_score": Decimal("0")},
            "ck_result_edition_max_score",
        ),
        ({"sheet_max": 0}, "ck_result_edition_sheet_max"),
        ({"published_at": AFTER_WINDOW}, "ck_result_edition_published_pair"),
        ({"exam_id": 999}, "fk_result_edition_attempt_scope"),
        ({"settings_version": 9}, "fk_result_edition_settings"),
    ],
)
async def test_database_rejects_invalid_rows(seeded, overrides, constraint):
    s = seeded
    attempt = await finished_attempt(s)
    with pytest.raises(IntegrityError) as error:
        await insert_row(s, attempt, **overrides)
    assert constraint in str(error.value)


async def test_manual_kind_fits_the_same_table(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await insert_row(s, attempt, kind="manual", calculated_score=None, final_score=Decimal("7.50"), used_weight=0)
    assert await count(s, "exam_result_edition") == 1


async def test_version_is_unique_per_attempt_and_isolated_between_attempts(seeded):
    s = seeded
    first = await finished_attempt(s)
    await insert_row(s, first)
    with pytest.raises(IntegrityError) as error:
        await insert_row(s, first)
    assert "uq_result_edition_version" in str(error.value)
    second_registration = await organized(s, project="manager2")
    second, _ = await start(s, second_registration, now=NOW + timedelta(minutes=30))
    await insert_row(s, second)
    assert await count(s, "exam_result_edition") == 2


async def test_migration_is_reversible_and_keeps_previous_tables(seeded, registration_database_url, run_migrations):
    s = seeded
    run_migrations(registration_database_url, "check")
    await s["engine"].dispose()
    run_migrations(registration_database_url, "downgrade", "d109a10b20c8")
    async with s["engine"].connect() as connection:
        tables = set(
            (await connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).scalars()
        )
    assert "exam_result_edition" not in tables and "exam_attempt" in tables
    run_migrations(registration_database_url, "upgrade", "head")
    run_migrations(registration_database_url, "check")
    assert await count(s, "exam") == 3
