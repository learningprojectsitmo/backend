from __future__ import annotations

import asyncio

import pytest
import test_exam_registrations_db as registration_cases
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_exam_registrations_db import NOW, count, reg_service, wait_until_blocked

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam_attempt import AttemptStart
from src.schema.exam_registration import RegistrationCreate
from src.services.exam_attempt_service import ExamAttemptService
from src.services.exam_service import ExamService

pytestmark = pytest.mark.integration

seeded = registration_cases.seeded


def attempt_service(uow, now=NOW):
    return ExamAttemptService(
        ExamAttemptRepository(uow),
        ExamRepository(uow),
        reg_service(uow, now),
        ExamService(ExamRepository(uow), ProjectTypeQuestionRepository(uow)),
        clock=lambda: now,
    )


async def organized(s, *, project="manager", exam=0, now=NOW):
    async with s["uow"]() as u:
        return await reg_service(u, now).create_organized(
            s["workspace"],
            s["exams"][exam],
            RegistrationCreate(project_id=s["projects"][project]),
            s["users"]["teacher"],
        )


async def start(s, registration, *, exam=0, version=1, now=NOW):
    async with s["uow"]() as u:
        return await attempt_service(u, now).start(
            s["workspace"],
            s["exams"][exam],
            AttemptStart(registration_id=registration.id, expected_version=version),
            s["users"]["teacher"],
        )


async def test_start_creates_attempt_with_scoped_links_and_marker(seeded):
    s = seeded
    registration = await organized(s)
    attempt, created = await start(s, registration)

    assert created is True
    assert (attempt.registration_id, attempt.exam_id, attempt.workspace_id) == (
        registration.id,
        s["exams"][0],
        s["workspace"],
    )
    assert (attempt.project_id, attempt.project_type_id) == (
        registration.project_id,
        registration.project_type_id_at_registration,
    )
    assert (attempt.status, attempt.version, attempt.settings_version) == ("speaking", 1, 1)
    assert attempt.started_at == NOW and attempt.phase_started_at == NOW
    assert attempt.phase_deadline.replace(second=0, microsecond=0) == NOW.replace(
        second=0, microsecond=0
    ) + registration_cases.timedelta(minutes=7)
    assert (attempt.paused_at, attempt.paused_seconds, attempt.finished_at, attempt.assessment_window) == (
        None,
        0,
        None,
        None,
    )

    async with s["uow"]() as u:
        registration_row = await u.session.get(registration_cases.ExamRegistration, registration.id)
    assert registration_row.started_at == NOW and registration_row.version == 2
    assert await count(s, "exam_attempt") == 1
    assert await count(s, "attempt_event") == 1
    assert await count(s, "registration_event") == 2


async def test_second_start_returns_same_attempt_without_new_events(seeded):
    s = seeded
    registration = await organized(s)
    first, created = await start(s, registration)
    second, created_again = await start(s, registration, version=1)

    assert created is True and created_again is False
    assert second.id == first.id and second.version == first.version
    assert await count(s, "exam_attempt") == 1
    assert await count(s, "attempt_event") == 1
    assert await count(s, "registration_event") == 2


async def test_start_with_stale_registration_version_after_success_returns_existing(seeded):
    s = seeded
    registration = await organized(s)
    await start(s, registration)
    attempt, created = await start(s, registration, version=9)
    assert created is False
    assert attempt.registration_id == registration.id
    assert await count(s, "exam_attempt") == 1


async def test_start_rejects_running_attempt_in_exam(seeded):
    s = seeded
    first = await organized(s, project="manager")
    second = await organized(s, project="manager2")
    await start(s, first)

    with pytest.raises(BusinessLogicError) as error:
        await start(s, second)
    assert error.value.detail["code"] == "another_defense_active"

    async with s["uow"]() as u:
        row = await u.session.get(registration_cases.ExamRegistration, second.id)
    assert row.started_at is None and row.version == 1
    assert await count(s, "exam_attempt") == 1
    assert await count(s, "attempt_event") == 1
    assert await count(s, "registration_event") == 3


async def test_concurrent_starts_leave_one_running_attempt(seeded):
    s = seeded
    first = await organized(s, project="manager")
    second = await organized(s, project="manager2")
    entered = asyncio.Event()
    other_pid = []

    async def contender():
        try:
            async with s["uow"]() as u:
                other_pid.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                entered.set()
                return await attempt_service(u).start(
                    s["workspace"],
                    s["exams"][0],
                    AttemptStart(registration_id=second.id, expected_version=1),
                    s["users"]["teacher"],
                )
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as session:
        await attempt_service(session).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=1),
            s["users"]["teacher"],
        )
        task = asyncio.create_task(contender())
        await asyncio.wait_for(entered.wait(), 5)
        try:
            await wait_until_blocked(s, other_pid[0])
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == "another_defense_active"
    assert await count(s, "exam_attempt") == 1
    assert await count(s, "attempt_event") == 1
    async with s["uow"]() as u:
        row = await u.session.get(registration_cases.ExamRegistration, second.id)
    assert row.started_at is None


async def test_start_rolls_back_claim_when_attempt_insert_fails(seeded):
    s = seeded
    registration = await organized(s)
    async with s["engine"].begin() as connection:
        await connection.execute(
            text(
                "CREATE FUNCTION fail_attempt_insert() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'attempt boom'; END; $$ LANGUAGE plpgsql"
            )
        )
        await connection.execute(
            text(
                "CREATE TRIGGER fail_attempt_insert BEFORE INSERT ON exam_attempt FOR EACH ROW EXECUTE FUNCTION fail_attempt_insert()"
            )
        )
    with pytest.raises(DBAPIError):
        await start(s, registration)
    async with s["engine"].begin() as connection:
        await connection.execute(text("DROP TRIGGER fail_attempt_insert ON exam_attempt"))
        await connection.execute(text("DROP FUNCTION fail_attempt_insert()"))

    async with s["uow"]() as u:
        row = await u.session.get(registration_cases.ExamRegistration, registration.id)
        events = await u.session.scalar(text("SELECT count(*) FROM registration_event"))
    assert row.started_at is None and row.version == 1
    assert events == 1
    assert await count(s, "exam_attempt") == 0


@pytest.mark.parametrize("actor", ["manager", "member", "outsider"])
async def test_non_organizer_cannot_start(seeded, actor):
    s = seeded
    registration = await organized(s)
    with pytest.raises((PermissionError, NotFoundError)):
        async with s["uow"]() as u:
            await attempt_service(u).start(
                s["workspace"],
                s["exams"][0],
                AttemptStart(registration_id=registration.id, expected_version=1),
                s["users"][actor],
            )
    assert await count(s, "exam_attempt") == 0
