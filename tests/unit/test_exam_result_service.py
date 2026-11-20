# ruff: noqa: ARG002  (fake signatures mirror the real collaborators)
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError, ValidationError
from src.model.exam_result import ExamResultEdition
from src.schema.exam_result import ResultAccept, ResultManual, ResultPublish
from src.services.exam_result_service import ExamResultService
from src.services.exam_score import SheetScore
from src.services.exam_sheet_source import UnconfiguredExamSheetSource

NOW = datetime(2026, 11, 30, 7, 0, tzinfo=UTC)
USER = SimpleNamespace(id=5)
OTHER = SimpleNamespace(id=6)
WS, EXAM, ATTEMPT = 7, 12, 31


class Flush:
    async def flush(self):
        return None


class Fakes:
    """In-memory stand-ins for the repositories and collaborators of ExamResultService."""

    def __init__(self):
        self.visibility_error: Exception | None = None
        self.is_teacher = True
        self.teacher_calls: list[tuple[int, int]] = []
        self.revoke_after_calls: int | None = None
        self.exam = SimpleNamespace(id=EXAM, workspace_id=WS, current_settings_version=1)
        self.revision = SimpleNamespace(
            teacher_weight=60, manager_weight=30, member_weight=10, max_score=Decimal("25.00")
        )
        self.attempt = SimpleNamespace(id=ATTEMPT, workspace_id=WS, exam_id=EXAM, project_type_id=8, status="finished")
        self.window = SimpleNamespace(closes_at=NOW - timedelta(minutes=1))
        self.questions = 5
        self.sheets = [SheetScore("teacher", 20), SheetScore("manager", 15), SheetScore("member", 25)]
        self.editions: list[ExamResultEdition] = []
        self.uow = SimpleNamespace(session=Flush())

    # exam service (visibility of the exam in the workspace: 404 for foreign or hidden ones)
    async def require_read_access(self, workspace_id, exam_id, user):
        if self.visibility_error is not None:
            raise self.visibility_error

    # project relations service (effective teacher/admin role of the workspace)
    async def is_workspace_teacher(self, user_id, *, workspace_id):
        self.teacher_calls.append((user_id, workspace_id))
        if self.revoke_after_calls is not None and len(self.teacher_calls) > self.revoke_after_calls:
            return False
        return self.is_teacher

    # exam repository
    async def get_scoped(self, workspace_id, exam_id, *, lock=False):
        return self.exam if (workspace_id, exam_id) == (WS, EXAM) else None

    async def get_revision(self, exam_id, version):
        return self.revision if version == self.exam.current_settings_version else None

    # attempt repository
    async def get(self, workspace_id, exam_id, attempt_id, *, lock=False):
        return self.attempt if (workspace_id, exam_id, attempt_id) == (WS, EXAM, ATTEMPT) else None

    async def window_for(self, attempt_id):
        return self.window

    # result repository
    async def latest(self, attempt_id):
        return self.editions[-1] if self.editions else None

    async def list_editions(self, attempt_id):
        return list(self.editions)

    async def add(self, edition):
        edition.id = len(self.editions) + 1
        self.editions.append(edition)
        return edition

    async def sheet_max(self, project_type_id):
        return 5 * self.questions

    # sheet source
    async def load_submitted_sheets(self, *, attempt_id):
        return self.sheets


class Results:
    def __init__(self, fakes: Fakes):
        self.uow = fakes.uow
        self.latest = fakes.latest
        self.editions = fakes.list_editions
        self.add = fakes.add
        self.sheet_max = fakes.sheet_max


class Attempts:
    def __init__(self, fakes: Fakes):
        self.get = fakes.get
        self.window = fakes.window_for


class Exams:
    def __init__(self, fakes: Fakes):
        self.get_scoped = fakes.get_scoped
        self.get_revision = fakes.get_revision


def make(fakes: Fakes | None = None, *, now: datetime = NOW, sheets=None):
    fakes = fakes or Fakes()
    service = ExamResultService(
        Results(fakes), Attempts(fakes), Exams(fakes), fakes, sheets or fakes, fakes, clock=lambda: now
    )
    return service, fakes


async def accept(service, version=0, reason=None, user=USER):
    return await service.accept(WS, EXAM, ATTEMPT, ResultAccept(expected_version=version, reason=reason), user)


async def manual(service, score="20", version=0, reason="oral defense", user=USER):
    data = ResultManual(expected_version=version, final_score=score, reason=reason)
    return await service.manual(WS, EXAM, ATTEMPT, data, user)


async def code_of(awaitable) -> str:
    with pytest.raises(BusinessLogicError) as error:
        await awaitable
    return error.value.detail["code"]


async def test_accept_first_edition_matches_documented_example():
    service, fakes = make()
    result = await accept(service)
    edition = result.edition
    assert (edition.version, edition.kind) == (1, "calculated")
    assert edition.calculated_score == edition.final_score == Decimal("19.00")
    assert edition.snapshot.sheet_max == 25 and edition.snapshot.used_weight == 100
    assert (edition.snapshot.sheets.teacher, edition.snapshot.sheets.member) == (1, 1)
    assert edition.decided_by == USER.id and edition.decided_at == NOW
    assert edition.published_at is None
    assert result.outdated is False and result.preliminary.score == Decimal("19.00")
    assert len(fakes.editions) == 1


async def test_sheet_max_follows_question_count():
    fakes = Fakes()
    fakes.questions = 3
    fakes.sheets = [SheetScore("teacher", 12)]
    service, _ = make(fakes)
    result = await accept(service)
    assert result.edition.snapshot.sheet_max == 15
    assert result.edition.final_score == Decimal("20.00")


async def test_small_or_empty_groups_do_not_block_accept():
    fakes = Fakes()
    fakes.sheets = [SheetScore("teacher", 20)]
    service, _ = make(fakes)
    result = await accept(service)
    assert result.edition.final_score == Decimal("20.00")
    assert result.edition.snapshot.used_weight == 60


async def test_accept_without_any_counted_sheet_is_rejected():
    fakes = Fakes()
    fakes.sheets = []
    service, fakes = make(fakes)
    assert await code_of(accept(service)) == "no_calculation"
    assert fakes.editions == []


async def test_accept_rejects_only_zero_weight_roles_as_no_calculation():
    fakes = Fakes()
    fakes.revision.teacher_weight, fakes.revision.manager_weight, fakes.revision.member_weight = 100, 0, 0
    fakes.sheets = [SheetScore("member", 20)]
    service, _ = make(fakes)
    assert await code_of(accept(service)) == "no_calculation"


async def test_accept_requires_finished_attempt():
    fakes = Fakes()
    fakes.attempt.status = "questions"
    service, fakes = make(fakes)
    assert await code_of(accept(service)) == "attempt_not_finished"


async def test_accept_requires_closed_window():
    service, _ = make(now=NOW - timedelta(minutes=2))
    assert await code_of(accept(service)) == "assessment_window_open"


async def test_accept_at_exact_close_time_is_allowed():
    fakes = Fakes()
    fakes.window.closes_at = NOW
    service, _ = make(fakes)
    assert (await accept(service)).edition.version == 1


async def test_accept_without_window_is_a_conflict():
    fakes = Fakes()
    fakes.window = None
    service, _ = make(fakes)
    assert await code_of(accept(service)) == "assessment_window_missing"


async def test_accept_without_questions_is_a_conflict():
    fakes = Fakes()
    fakes.questions = 0
    service, _ = make(fakes)
    assert await code_of(accept(service)) == "questions_missing"


async def test_invalid_sheet_data_is_a_conflict_not_a_crash():
    fakes = Fakes()
    fakes.sheets = [SheetScore("teacher", 26)]
    service, _ = make(fakes)
    assert await code_of(accept(service)) == "invalid_sheet_data"


async def test_unconfigured_sheet_source_fails_loudly():
    service, fakes = make(sheets=UnconfiguredExamSheetSource())
    assert await code_of(accept(service)) == "sheet_source_not_configured"
    assert fakes.editions == []


async def test_stale_expected_version_conflicts():
    service, _ = make()
    await accept(service)
    assert await code_of(accept(service, version=0)) == "result_version_conflict"
    assert await code_of(accept(service, version=2, reason="x")) == "result_version_conflict"


async def test_repeated_accept_creates_new_version_and_keeps_old():
    service, fakes = make()
    await accept(service)
    first = fakes.editions[0]
    fakes.revision.teacher_weight, fakes.revision.manager_weight, fakes.revision.member_weight = 20, 40, 40
    fakes.exam.current_settings_version = 2
    result = await accept(service, version=1, reason="weights changed")
    assert result.edition.version == 2 and result.edition.reason == "weights changed"
    assert result.edition.final_score == Decimal("20.00")
    assert len(fakes.editions) == 2 and fakes.editions[0] is first
    assert first.final_score == Decimal("19.00") and first.teacher_weight == 60


async def test_accepted_result_does_not_change_with_new_votes_but_is_outdated():
    service, fakes = make()
    await accept(service)
    fakes.sheets = [*fakes.sheets, SheetScore("member", 5)]
    result = await service.get(WS, EXAM, ATTEMPT, USER)
    assert result.edition.final_score == Decimal("19.00")
    assert result.preliminary.score == Decimal("18.00")
    assert result.outdated is True


async def test_outdated_after_settings_change_even_if_score_is_equal():
    service, fakes = make()
    await accept(service)
    fakes.exam.current_settings_version = 2
    result = await service.get(WS, EXAM, ATTEMPT, USER)
    assert result.outdated is True and result.edition.snapshot.settings_version == 1


async def test_get_before_accept_has_preliminary_only():
    service, _ = make()
    result = await service.get(WS, EXAM, ATTEMPT, USER)
    assert result.edition is None and result.outdated is False
    assert result.preliminary.score == Decimal("19.00")


async def test_get_without_calculation_shows_no_calculation():
    fakes = Fakes()
    fakes.sheets = []
    service, _ = make(fakes)
    result = await service.get(WS, EXAM, ATTEMPT, USER)
    assert result.preliminary.no_calculation is True and result.preliminary.score is None


async def test_get_of_unfinished_attempt_has_no_preliminary():
    fakes = Fakes()
    fakes.attempt.status = "speaking"
    service, _ = make(fakes)
    assert (await service.get(WS, EXAM, ATTEMPT, USER)).preliminary is None


async def test_editions_are_listed_ascending():
    service, _ = make()
    await accept(service)
    await accept(service, version=1, reason="again")
    listed = await service.editions(WS, EXAM, ATTEMPT, USER)
    assert [item.version for item in listed.items] == [1, 2]


async def test_publish_marks_current_edition_and_is_idempotent():
    service, fakes = make()
    await accept(service)
    first = await service.publish(WS, EXAM, ATTEMPT, ResultPublish(expected_version=1), USER)
    assert first.edition.published_at == NOW and first.edition.published_by == USER.id
    later = ExamResultService(
        Results(fakes), Attempts(fakes), Exams(fakes), fakes, fakes, fakes, clock=lambda: NOW + timedelta(hours=1)
    )
    again = await later.publish(WS, EXAM, ATTEMPT, ResultPublish(expected_version=1), OTHER)
    assert again.edition.published_at == NOW and again.edition.published_by == USER.id


async def test_publish_requires_accepted_result_and_matching_version():
    service, _ = make()
    assert await code_of(service.publish(WS, EXAM, ATTEMPT, ResultPublish(expected_version=1), USER)) == (
        "result_not_accepted"
    )
    await accept(service)
    assert await code_of(service.publish(WS, EXAM, ATTEMPT, ResultPublish(expected_version=2), USER)) == (
        "result_version_conflict"
    )


async def test_publishing_an_outdated_edition_is_allowed_and_flagged():
    service, fakes = make()
    await accept(service)
    fakes.revision.max_score = Decimal("50.00")
    result = await service.publish(WS, EXAM, ATTEMPT, ResultPublish(expected_version=1), USER)
    assert result.edition.published_at == NOW and result.outdated is True


async def test_publish_of_older_edition_after_new_decision_conflicts():
    service, _ = make()
    await accept(service)
    await accept(service, version=1, reason="again")
    assert await code_of(service.publish(WS, EXAM, ATTEMPT, ResultPublish(expected_version=1), USER)) == (
        "result_version_conflict"
    )


def calls_for(service):
    return {
        "accept": lambda: accept(service, version=1, reason="x"),
        "manual": lambda: manual(service, version=1),
        "publish": lambda: service.publish(WS, EXAM, ATTEMPT, ResultPublish(expected_version=1), USER),
        "get": lambda: service.get(WS, EXAM, ATTEMPT, USER),
        "editions": lambda: service.editions(WS, EXAM, ATTEMPT, USER),
    }


@pytest.mark.parametrize("call", ["accept", "manual", "publish", "get", "editions"])
async def test_user_without_workspace_teacher_role_is_forbidden(call):
    # Covers: global admin outside the workspace, local member with a global teacher role,
    # a plain participant: all of them are `False` from is_workspace_teacher.
    service, fakes = make()
    await accept(service)
    fakes.is_teacher = False
    with pytest.raises(PermissionError):
        await calls_for(service)[call]()
    assert len(fakes.editions) == 1 and fakes.editions[0].published_at is None


async def test_role_is_checked_for_the_requested_workspace_and_user():
    service, fakes = make()
    await service.get(WS, EXAM, ATTEMPT, USER)
    assert fakes.teacher_calls == [(USER.id, WS)]


async def test_workspace_teacher_is_allowed_for_every_operation():
    service, fakes = make()
    await accept(service)
    for call in ["publish", "get", "editions"]:
        await calls_for(service)[call]()
    assert fakes.editions[0].published_at == NOW


async def test_visibility_is_checked_before_role():
    service, fakes = make()
    fakes.visibility_error = NotFoundError("Workspace not found")
    fakes.is_teacher = False
    with pytest.raises(NotFoundError):
        await service.get(WS, EXAM, ATTEMPT, USER)
    assert fakes.teacher_calls == []


async def test_foreign_scope_is_not_found():
    service, fakes = make()
    fakes.visibility_error = NotFoundError("Exam not found")
    for call in ["accept", "manual", "publish", "get", "editions"]:
        with pytest.raises(NotFoundError):
            await calls_for(service)[call]()


async def test_accept_rechecks_role_after_the_lock_and_stores_nothing():
    service, fakes = make()
    fakes.revoke_after_calls = 1  # first check passes, the check after the lock wait fails
    with pytest.raises(PermissionError):
        await accept(service)
    assert fakes.editions == [] and len(fakes.teacher_calls) == 2


async def test_publish_rechecks_role_after_the_lock_and_keeps_edition_unpublished():
    service, fakes = make()
    await accept(service)
    fakes.teacher_calls.clear()
    fakes.revoke_after_calls = 1
    with pytest.raises(PermissionError):
        await service.publish(WS, EXAM, ATTEMPT, ResultPublish(expected_version=1), USER)
    assert fakes.editions[0].published_at is None and len(fakes.teacher_calls) == 2


@pytest.mark.parametrize("ids", [(WS, EXAM, 99), (WS, 99, ATTEMPT), (99, EXAM, ATTEMPT)])
async def test_unknown_attempt_or_exam_is_not_found(ids):
    service, _ = make()
    with pytest.raises(NotFoundError):
        await service.accept(*ids, ResultAccept(expected_version=0), USER)
    with pytest.raises(NotFoundError):
        await service.get(*ids, USER)


# ---- manual result (#116) ----


async def test_manual_stores_both_values_reason_author_and_snapshot():
    service, fakes = make()
    result = await manual(service, "17.5")
    edition = result.edition
    assert (edition.version, edition.kind) == (1, "manual")
    assert edition.final_score == Decimal("17.50") and edition.calculated_score == Decimal("19.00")
    assert edition.reason == "oral defense" and edition.decided_by == USER.id and edition.decided_at == NOW
    assert edition.snapshot.sheet_max == 25 and edition.snapshot.used_weight == 100
    assert edition.snapshot.weights.teacher == 60 and edition.snapshot.max_score == Decimal("25.00")
    assert (edition.snapshot.sheets.teacher, edition.snapshot.sheets.manager) == (1, 1)
    assert len(fakes.editions) == 1 and fakes.editions[0].kind == "manual"


async def test_manual_without_calculation_is_allowed_with_null_calculated_score():
    fakes = Fakes()
    fakes.sheets = []
    service, fakes = make(fakes)
    assert await code_of(accept(service)) == "no_calculation"
    result = await manual(service, "12")
    assert result.edition.calculated_score is None and result.edition.final_score == Decimal("12.00")
    assert result.edition.snapshot.used_weight == 0
    assert result.preliminary.no_calculation is True


async def test_manual_without_calculation_is_not_outdated_until_votes_appear():
    fakes = Fakes()
    fakes.sheets = []
    service, fakes = make(fakes)
    await manual(service, "12")
    assert (await service.get(WS, EXAM, ATTEMPT, USER)).outdated is False
    fakes.sheets = [SheetScore("teacher", 20)]
    assert (await service.get(WS, EXAM, ATTEMPT, USER)).outdated is True


async def test_manual_final_score_is_not_compared_with_the_calculation():
    service, fakes = make()
    await manual(service, "3")  # far from the calculated 19.00
    assert (await service.get(WS, EXAM, ATTEMPT, USER)).outdated is False
    fakes.revision.max_score = Decimal("50.00")
    assert (await service.get(WS, EXAM, ATTEMPT, USER)).outdated is True


@pytest.mark.parametrize("score", ["0", "25", "25.00", "0.01"])
async def test_manual_range_bounds_are_inclusive(score):
    service, _ = make()
    assert (await manual(service, score)).edition.final_score == Decimal(score).quantize(Decimal("0.01"))


async def test_manual_above_max_score_is_422_and_stores_nothing():
    service, fakes = make()
    with pytest.raises(ValidationError) as error:
        await manual(service, "25.01")
    assert error.value.detail["code"] == "final_score_out_of_range" and error.value.detail["max_score"] == "25.00"
    assert fakes.editions == []


async def test_manual_range_uses_current_settings_max_score():
    fakes = Fakes()
    fakes.revision.max_score = Decimal("100.00")
    service, _ = make(fakes)
    assert (await manual(service, "76")).edition.final_score == Decimal("76.00")
    assert (await manual(service, "100", version=1)).edition.snapshot.max_score == Decimal("100.00")


async def test_manual_value_is_not_rounded_to_integer():
    service, _ = make()
    assert (await manual(service, "19.45")).edition.final_score == Decimal("19.45")


async def test_manual_requires_finished_attempt_and_closed_window():
    fakes = Fakes()
    fakes.attempt.status = "questions"
    service, _ = make(fakes)
    assert await code_of(manual(service)) == "attempt_not_finished"
    fakes.attempt.status = "finished"
    fakes.window = None
    assert await code_of(manual(service)) == "assessment_window_missing"
    fakes.window = SimpleNamespace(closes_at=NOW + timedelta(seconds=1))
    assert await code_of(manual(service)) == "assessment_window_open"
    assert fakes.editions == []


async def test_manual_at_exact_close_time_is_allowed():
    fakes = Fakes()
    fakes.window.closes_at = NOW
    service, _ = make(fakes)
    assert (await manual(service)).edition.version == 1


async def test_manual_version_conflicts():
    service, fakes = make()
    assert await code_of(manual(service, version=1)) == "result_version_conflict"
    await manual(service)
    assert await code_of(manual(service, version=0)) == "result_version_conflict"
    assert await code_of(manual(service, version=2)) == "result_version_conflict"
    assert len(fakes.editions) == 1


async def test_manual_propagates_source_and_data_conflicts():
    fakes = Fakes()
    fakes.sheets = [SheetScore("teacher", 26)]
    service, _ = make(fakes)
    assert await code_of(manual(service)) == "invalid_sheet_data"
    service, fakes = make(sheets=UnconfiguredExamSheetSource())
    assert await code_of(manual(service)) == "sheet_source_not_configured"
    assert fakes.editions == []


async def test_manual_is_forbidden_for_non_teachers_and_stores_nothing():
    service, fakes = make()
    fakes.is_teacher = False
    with pytest.raises(PermissionError):
        await manual(service)
    assert fakes.editions == []


async def test_manual_rechecks_role_after_the_lock():
    service, fakes = make()
    fakes.revoke_after_calls = 1
    with pytest.raises(PermissionError):
        await manual(service)
    assert fakes.editions == [] and len(fakes.teacher_calls) == 2


async def test_accept_after_manual_and_manual_after_accept_make_next_versions():
    service, fakes = make()
    await manual(service, "10")
    after_accept = await accept(service, version=1, reason="recalculated")
    assert (after_accept.edition.version, after_accept.edition.kind) == (2, "calculated")
    after_manual = await manual(service, "21", version=2, reason="regrade")
    assert (after_manual.edition.version, after_manual.edition.kind) == (3, "manual")
    first, second, third = fakes.editions
    assert (first.kind, first.final_score, first.reason) == ("manual", Decimal("10.00"), "oral defense")
    assert (second.kind, second.final_score, second.calculated_score) == (
        "calculated",
        Decimal("19.00"),
        Decimal("19.00"),
    )
    assert third.final_score == Decimal("21.00") and len(fakes.editions) == 3


async def test_publish_works_for_manual_edition():
    service, _ = make()
    await manual(service, "18")
    result = await service.publish(WS, EXAM, ATTEMPT, ResultPublish(expected_version=1), USER)
    assert result.edition.kind == "manual" and result.edition.published_at == NOW
    assert result.edition.published_by == USER.id and result.edition.final_score == Decimal("18.00")


async def test_manual_does_not_touch_sheets_source_data():
    service, fakes = make()
    before = list(fakes.sheets)
    await manual(service, "5")
    assert fakes.sheets == before
