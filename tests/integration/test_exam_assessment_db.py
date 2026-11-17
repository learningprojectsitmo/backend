from __future__ import annotations

import asyncio

import pytest
import test_exam_registrations_db as reg_cases
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.model.exam_assessment import ExamAssessmentSheet
from src.model.project_type_question import ProjectTypeQuestion
from src.repository.exam_assessment_repository import ExamAssessmentRepository
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_registration_repository import ExamRegistrationRepository
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam_attempt import AttemptCommand, AttemptStart
from src.schema.exam_registration import RegistrationCreate
from src.services.exam_attempt_service import ExamAttemptService
from src.services.exam_queue_service import ExamQueueService
from src.services.exam_service import ExamService

pytestmark = pytest.mark.integration

seeded = reg_cases.seeded
NOW = reg_cases.NOW


def _repo(uow):
    return ExamAssessmentRepository(uow)


def attempt_service(uow, now=NOW):
    clock = now if callable(now) else (lambda: now)
    exam_service = ExamService(ExamRepository(uow), ProjectTypeQuestionRepository(uow))
    queue = ExamQueueService(
        ExamRegistrationRepository(uow), ExamAttemptRepository(uow), ExamRepository(uow), exam_service, clock=clock
    )
    return ExamAttemptService(
        ExamAttemptRepository(uow),
        ExamRepository(uow),
        reg_cases.reg_service(uow, now),
        exam_service,
        queue,
        ExamRegistrationRepository(uow),
        clock=clock,
    )


async def _finished_attempt(s, *, project="manager"):
    """Create and finish an attempt via organizer registration + start + questions + finish."""
    async with s["uow"]() as u:
        reg = await reg_cases.reg_service(u).create_organized(
            s["workspace"], s["exams"][0], RegistrationCreate(project_id=s["projects"][project]), s["users"]["teacher"]
        )
    async with s["uow"]() as u:
        attempt, _created = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=reg.id, expected_version=reg.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        svc = attempt_service(u)
        attempt = await svc.get(s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"])
        await svc.questions(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptCommand(expected_version=attempt.version),
            s["users"]["teacher"],
        )
        attempt2 = await svc.get(s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"])
        return await svc.finish(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptCommand(expected_version=attempt2.version),
            s["users"]["teacher"],
        )


class TestSheetCRUD:
    async def test_get_or_create_sheet_creates_new(self, seeded):
        s = seeded
        attempt = await _finished_attempt(s)
        async with s["uow"]() as u:
            sheet = await _repo(u).get_or_create_sheet(
                workspace_id=s["workspace"],
                exam_id=s["exams"][0],
                attempt_id=attempt.id,
                user_id=s["users"]["member"].id,
            )
            assert sheet is not None
            assert sheet.status == "draft"
            assert sheet.attempt_id == attempt.id

    async def test_get_or_create_sheet_returns_existing(self, seeded):
        s = seeded
        attempt = await _finished_attempt(s)
        async with s["uow"]() as u:
            repo = _repo(u)
            uid = s["users"]["member"].id
            s1 = await repo.get_or_create_sheet(s["workspace"], s["exams"][0], attempt.id, uid)
            s2 = await repo.get_or_create_sheet(s["workspace"], s["exams"][0], attempt.id, uid)
            assert s1.id == s2.id

    async def test_get_sheet_returns_none_for_missing(self, seeded):
        s = seeded
        attempt = await _finished_attempt(s)
        async with s["uow"]() as u:
            assert await _repo(u).get_sheet(s["workspace"], s["exams"][0], attempt.id, 999999) is None

    async def test_get_sheet_returns_existing(self, seeded):
        s = seeded
        attempt = await _finished_attempt(s)
        async with s["uow"]() as u:
            repo = _repo(u)
            uid = s["users"]["member"].id
            created = await repo.get_or_create_sheet(s["workspace"], s["exams"][0], attempt.id, uid)
            found = await repo.get_sheet(s["workspace"], s["exams"][0], attempt.id, uid)
            assert found is not None
            assert found.id == created.id

    async def test_uq_sheet_user_attempt_prevents_duplicate(self, seeded):
        s = seeded
        attempt = await _finished_attempt(s)
        async with s["uow"]() as u:
            repo = _repo(u)
            uid = s["users"]["member"].id
            await repo.get_or_create_sheet(s["workspace"], s["exams"][0], attempt.id, uid)
            # Direct second insert must violate uq_sheet_user_attempt.
            sheet2 = ExamAssessmentSheet(
                workspace_id=s["workspace"], exam_id=s["exams"][0], attempt_id=attempt.id, user_id=uid, status="draft"
            )
            u.session.add(sheet2)
            with pytest.raises(IntegrityError):
                await u.session.flush()
            # Recovery: rollback the session so it is usable again.
            await u.session.rollback()


class TestAnswerUpsert:
    async def _make_sheet(self, s, attempt):
        async with s["uow"]() as u:
            s_ = await _repo(u).get_or_create_sheet(s["workspace"], s["exams"][0], attempt.id, s["users"]["member"].id)
            qid = await u.session.scalar(select(ProjectTypeQuestion.id).limit(1))
            return s_.id, qid

    async def test_upsert_inserts_and_updates(self, seeded):
        s = seeded
        attempt = await _finished_attempt(s)
        sheet_id, qid = await self._make_sheet(s, attempt)
        async with s["uow"]() as u:
            repo = _repo(u)
            await repo.upsert_answers(sheet_id, [(qid, 4, "good")])
            answers = await repo.get_answers(sheet_id)
            assert answers[qid].score == 4
            await repo.upsert_answers(sheet_id, [(qid, 5, "updated")])
            answers = await repo.get_answers(sheet_id)
            assert answers[qid].score == 5

    async def test_upsert_null_score_clears(self, seeded):
        s = seeded
        attempt = await _finished_attempt(s)
        sheet_id, qid = await self._make_sheet(s, attempt)
        async with s["uow"]() as u:
            repo = _repo(u)
            await repo.upsert_answers(sheet_id, [(qid, 4, "set")])
            await repo.upsert_answers(sheet_id, [(qid, None, None)])
            answers = await repo.get_answers(sheet_id)
            assert answers[qid].score is None


class TestAccessLogic:
    @pytest.mark.parametrize(
        "actor, admitted, role",
        [("manager", False, "manager"), ("local_teacher", True, "teacher"), ("member", True, "member")],
    )
    async def test_repository_reads_scoped_snapshot(self, seeded, actor, admitted, role):
        s = seeded
        attempt = await _finished_attempt(s)
        async with s["uow"]() as u:
            repo = _repo(u)
            window = (await repo.get_attempt_with_window_and_project(s["workspace"], s["exams"][0], attempt.id))[1]
            row = await repo.get_audience(window.id, s["workspace"], s["users"][actor].id)
            assert (row.admitted, row.role) == (admitted, role)
            assert await repo.get_audience(window.id, s["foreign_workspace"], s["users"][actor].id) is None
            assert await repo.get_audience(window.id, s["workspace"], s["users"]["outsider"].id) is None


class TestScopedFetch:
    async def test_get_attempt_with_window_and_project_returns_none_for_missing(self, seeded):
        s = seeded
        async with s["uow"]() as u:
            result = await _repo(u).get_attempt_with_window_and_project(workspace_id=999, exam_id=999, attempt_id=999)
            assert result is None


class TestQueueChangeAndConcurrency:
    async def test_two_attempts_have_distinct_sheets(self, seeded):
        """Queue change (next team) creates a new attempt and a distinct sheet — no replacement."""
        s = seeded
        first = await _finished_attempt(s, project="manager")
        second = await _finished_attempt(s, project="manager2")
        assert first.id != second.id
        async with s["uow"]() as u:
            repo = _repo(u)
            uid = s["users"]["local_teacher"].id
            s1 = await repo.get_or_create_sheet(s["workspace"], s["exams"][0], first.id, uid)
            s2 = await repo.get_or_create_sheet(s["workspace"], s["exams"][0], second.id, uid)
            assert s1.id != s2.id
            assert s1.attempt_id == first.id
            assert s2.attempt_id == second.id

    async def test_concurrent_get_or_create_produces_one_sheet(self, seeded):
        """Two parallel get_or_create calls for the same (user, attempt) yield one sheet."""
        s = seeded
        attempt = await _finished_attempt(s, project="manager")
        uid = s["users"]["local_teacher"].id

        async def create():
            async with s["uow"]() as u:
                sheet = await _repo(u).get_or_create_sheet(s["workspace"], s["exams"][0], attempt.id, uid)
                return sheet.id

        first_id, second_id = await asyncio.gather(create(), create())
        assert first_id == second_id

    async def test_sheet_creation_rolls_back_on_later_error(self, seeded):
        """An exception after lazy sheet creation rolls back the new sheet (UoW rollback)."""
        s = seeded
        attempt = await _finished_attempt(s, project="manager")
        uid = s["users"]["local_teacher"].id

        class Boom(Exception):
            pass

        with pytest.raises(Boom):
            async with s["uow"]() as u:
                repo = _repo(u)
                await repo.get_or_create_sheet(s["workspace"], s["exams"][0], attempt.id, uid)
                await u.session.flush()
                raise Boom()

        # The sheet must not persist after the rollback.
        async with s["uow"]() as u:
            assert await _repo(u).get_sheet(s["workspace"], s["exams"][0], attempt.id, uid) is None
