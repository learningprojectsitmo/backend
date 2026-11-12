from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx
import pytest
import test_exam_registrations_db as registration_cases
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_exam_registrations_db import NOW, count, reg_service, wait_until_blocked

from src.api.v1.routes import routers
from src.core.container import get_uow
from src.core.dependencies import get_current_user
from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.model.exam_attempt import ExamAttempt
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam import ExamSettingsReplace
from src.schema.exam_attempt import AttemptCommand, AttemptPause, AttemptStart
from src.schema.exam_registration import RegistrationCreate
from src.services.exam_attempt_service import ExamAttemptService
from src.services.exam_service import ExamService

pytestmark = pytest.mark.integration

seeded = registration_cases.seeded


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def attempt_service(uow, now=NOW):
    clock = now if callable(now) else (lambda: now)
    return ExamAttemptService(
        ExamAttemptRepository(uow),
        ExamRepository(uow),
        reg_service(uow),
        ExamService(ExamRepository(uow), ProjectTypeQuestionRepository(uow)),
        clock=clock,
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


async def test_start_sets_presentation_deadline_and_questions_from_start_revision(seeded):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    assert attempt.phase_deadline == NOW + timedelta(minutes=7)
    assert attempt.remaining_seconds == 420

    clock = Clock(NOW + timedelta(minutes=2))
    async with s["uow"]() as u:
        after = await attempt_service(u, clock).questions(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=1), s["users"]["teacher"]
        )
    assert (after.status, after.version) == ("questions", 2)
    assert after.phase_started_at == NOW + timedelta(minutes=2)
    assert after.phase_deadline == NOW + timedelta(minutes=9)
    assert after.remaining_seconds == 420
    assert await count(s, "attempt_event") == 2


async def test_pause_resume_shifts_deadline_and_survives_reload(seeded):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)

    async with s["uow"]() as u:
        await attempt_service(u, Clock(NOW + timedelta(minutes=2))).questions(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=1), s["users"]["teacher"]
        )
    paused = Clock(NOW + timedelta(minutes=3))
    async with s["uow"]() as u:
        after_pause = await attempt_service(u, paused).pause(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPause(expected_version=2, reason="Проектор"),
            s["users"]["teacher"],
        )
    assert after_pause.paused_at == NOW + timedelta(minutes=3)
    assert after_pause.phase_deadline == NOW + timedelta(minutes=9)

    reload = Clock(NOW + timedelta(minutes=5))
    async with s["uow"]() as u:
        reloaded = await attempt_service(u, reload).current(s["workspace"], s["exams"][0], s["users"]["member"])
    assert reloaded.attempt is not None
    assert (reloaded.attempt.version, reloaded.attempt.paused_seconds) == (3, 0)
    assert reloaded.attempt.remaining_seconds == 360
    assert reloaded.attempt.paused_at == NOW + timedelta(minutes=3)

    async with s["uow"]() as u:
        resumed = await attempt_service(u, reload).resume(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=3), s["users"]["teacher"]
        )
    assert resumed.paused_at is None
    assert resumed.phase_deadline == NOW + timedelta(minutes=11)
    assert resumed.paused_seconds == 120
    assert resumed.version == 4

    later = Clock(NOW + timedelta(minutes=6))
    async with s["uow"]() as u:
        state = await attempt_service(u, later).get(s["workspace"], s["exams"][0], attempt.id, s["users"]["member"])
    assert state.remaining_seconds == 300
    assert await count(s, "attempt_event") == 4


async def test_zero_questions_and_overrun_do_not_change_phase(seeded):
    s = seeded
    async with s["uow"]() as u:
        exams = ExamService(ExamRepository(u), ProjectTypeQuestionRepository(u))
        current = await exams.get(s["workspace"], s["exams"][0], s["users"]["teacher"])
        await exams.replace_settings(
            s["workspace"],
            s["exams"][0],
            ExamSettingsReplace(
                expected_version=current.current_settings_version,
                reason="Вопросы отключены",
                configuration=current.configuration.model_copy(update={"questions_minutes": 0}),
            ),
            s["users"]["teacher"],
        )
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    async with s["uow"]() as u:
        questions = await attempt_service(u, Clock(NOW + timedelta(minutes=1))).questions(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=1), s["users"]["teacher"]
        )
    assert questions.phase_deadline == questions.phase_started_at == NOW + timedelta(minutes=1)

    async with s["uow"]() as u:
        late = await attempt_service(u, Clock(NOW + timedelta(minutes=5))).current(
            s["workspace"], s["exams"][0], s["users"]["teacher"]
        )
    assert late.attempt is not None
    assert late.attempt.status == "questions"
    assert late.attempt.remaining_seconds == -240


async def test_repeat_pause_resume_and_questions_are_noop(seeded):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    clock = Clock(NOW + timedelta(minutes=1))
    async with s["uow"]() as u:
        first = await attempt_service(u, clock).questions(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=1), s["users"]["teacher"]
        )
        repeated = await attempt_service(u, clock).questions(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=1), s["users"]["teacher"]
        )
    assert (repeated.version, repeated.phase_deadline) == (first.version, first.phase_deadline)

    clock.now = NOW + timedelta(minutes=2)
    async with s["uow"]() as u:
        paused = await attempt_service(u, clock).pause(
            s["workspace"], s["exams"][0], attempt.id, AttemptPause(expected_version=2), s["users"]["teacher"]
        )
        paused_again = await attempt_service(u, clock).pause(
            s["workspace"], s["exams"][0], attempt.id, AttemptPause(expected_version=2), s["users"]["teacher"]
        )
    assert (paused_again.version, paused_again.paused_at) == (paused.version, paused.paused_at)

    clock.now = NOW + timedelta(minutes=3)
    async with s["uow"]() as u:
        resumed = await attempt_service(u, clock).resume(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=3), s["users"]["teacher"]
        )
        resumed_again = await attempt_service(u, clock).resume(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=3), s["users"]["teacher"]
        )
    assert (resumed_again.version, resumed_again.paused_seconds) == (resumed.version, resumed.paused_seconds)
    assert await count(s, "attempt_event") == 4


async def test_stale_version_on_real_transition_conflicts(seeded):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await attempt_service(u, Clock(NOW + timedelta(minutes=1))).questions(
                s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=9), s["users"]["teacher"]
            )
    assert error.value.detail["code"] == "attempt_version_conflict"
    async with s["uow"]() as u:
        row = await u.session.get(ExamAttempt, attempt.id)
    assert (row.status, row.version) == ("speaking", 1)


async def test_questions_while_paused_conflicts(seeded):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    async with s["uow"]() as u:
        paused = await attempt_service(u, Clock(NOW + timedelta(minutes=1))).pause(
            s["workspace"], s["exams"][0], attempt.id, AttemptPause(expected_version=1), s["users"]["teacher"]
        )
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await attempt_service(u, Clock(NOW + timedelta(minutes=2))).questions(
                s["workspace"],
                s["exams"][0],
                attempt.id,
                AttemptCommand(expected_version=paused.version),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "attempt_paused"


@pytest.mark.parametrize("actor", ["manager", "member", "outsider"])
async def test_non_organizer_cannot_change_phase(seeded, actor):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    for call in (
        lambda svc: svc.questions(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=1), s["users"][actor]
        ),
        lambda svc: svc.pause(
            s["workspace"], s["exams"][0], attempt.id, AttemptPause(expected_version=1), s["users"][actor]
        ),
        lambda svc: svc.resume(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=1), s["users"][actor]
        ),
    ):
        with pytest.raises((PermissionError, NotFoundError)):
            async with s["uow"]() as u:
                await call(attempt_service(u))
    async with s["uow"]() as u:
        row = await u.session.get(ExamAttempt, attempt.id)
    assert (row.status, row.version) == ("speaking", 1)


async def finish(s, attempt, *, version=1, now=NOW, actor="teacher"):
    async with s["uow"]() as u:
        return await attempt_service(u, now).finish(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=version), s["users"][actor]
        )


async def set_window_minutes(s, minutes, *, expected_version=1):
    async with s["uow"]() as u:
        exams = ExamService(ExamRepository(u), ProjectTypeQuestionRepository(u))
        current = await exams.get(s["workspace"], s["exams"][0], s["users"]["teacher"])
        await exams.replace_settings(
            s["workspace"],
            s["exams"][0],
            ExamSettingsReplace(
                expected_version=expected_version,
                reason="Новый срок оценивания",
                configuration=current.configuration.model_copy(update={"assessment_window_minutes": minutes}),
            ),
            s["users"]["teacher"],
        )


async def test_finish_persists_window_with_configured_minutes_and_locks_questions(seeded):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    finished = await finish(s, attempt, now=NOW + timedelta(minutes=10))

    assert (finished.status, finished.version, finished.finished_at) == ("finished", 2, NOW + timedelta(minutes=10))
    assert finished.remaining_seconds == 0
    assert finished.assessment_window is not None
    window = finished.assessment_window
    assert (window.opened_at, window.closes_at) == (NOW + timedelta(minutes=10), NOW + timedelta(minutes=13))
    assert (window.settings_version, window.project_type_id) == (1, attempt.project_type_id)
    assert await count(s, "assessment_window") == 1
    assert await count(s, "attempt_event") == 2
    async with s["engine"].connect() as connection:
        locked = await connection.scalar(text("SELECT count(*) FROM project_type_question_lock"))
    assert locked == 1


async def test_finish_uses_current_settings_and_keeps_phase_deadlines(seeded):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    await set_window_minutes(s, 5)
    finished = await finish(s, attempt, now=NOW + timedelta(minutes=10))

    assert finished.settings_version == 1
    assert finished.phase_deadline == NOW + timedelta(minutes=7)
    assert finished.assessment_window is not None
    assert finished.assessment_window.settings_version == 2
    assert finished.assessment_window.closes_at == NOW + timedelta(minutes=15)


async def test_finish_from_paused_ends_pause(seeded):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    async with s["uow"]() as u:
        paused = await attempt_service(u, Clock(NOW + timedelta(minutes=3))).pause(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPause(expected_version=1, reason="Перерыв"),
            s["users"]["teacher"],
        )
    finished = await finish(s, attempt, version=paused.version, now=NOW + timedelta(minutes=5))
    assert finished.status == "finished"
    assert finished.paused_at is None
    assert finished.finished_at == NOW + timedelta(minutes=5)


async def test_repeat_finish_returns_same_window_after_settings_change(seeded):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    first = await finish(s, attempt, now=NOW + timedelta(minutes=10))
    await set_window_minutes(s, 10)
    repeated = await finish(s, attempt, version=1, now=NOW + timedelta(minutes=20))

    assert repeated.id == first.id and repeated.version == first.version
    assert repeated.assessment_window is not None and first.assessment_window is not None
    assert repeated.assessment_window.closes_at == first.assessment_window.closes_at
    assert await count(s, "assessment_window") == 1
    assert await count(s, "attempt_event") == 2


async def test_concurrent_finish_creates_one_window(seeded):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    entered = asyncio.Event()
    other_pid = []

    async def contender():
        try:
            async with s["uow"]() as u:
                other_pid.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                entered.set()
                return await attempt_service(u, Clock(NOW + timedelta(minutes=10))).finish(
                    s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=1), s["users"]["teacher"]
                )
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as session:
        await attempt_service(session, Clock(NOW + timedelta(minutes=10))).finish(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=1), s["users"]["teacher"]
        )
        task = asyncio.create_task(contender())
        await asyncio.wait_for(entered.wait(), 5)
        try:
            await wait_until_blocked(s, other_pid[0])
        except BaseException:
            task.cancel()
            raise
    result = await asyncio.wait_for(task, 10)
    assert getattr(result, "status", None) == "finished"
    assert await count(s, "assessment_window") == 1
    assert await count(s, "attempt_event") == 2


async def test_finish_failure_rolls_back_window_and_question_lock(seeded):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    async with s["engine"].begin() as connection:
        await connection.execute(
            text(
                "CREATE FUNCTION fail_window_insert() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'window boom'; END; $$ LANGUAGE plpgsql"
            )
        )
        await connection.execute(
            text(
                "CREATE TRIGGER fail_window_insert BEFORE INSERT ON assessment_window FOR EACH ROW EXECUTE FUNCTION fail_window_insert()"
            )
        )
    with pytest.raises(DBAPIError):
        await finish(s, attempt, now=NOW + timedelta(minutes=10))
    async with s["engine"].begin() as connection:
        await connection.execute(text("DROP TRIGGER fail_window_insert ON assessment_window"))
        await connection.execute(text("DROP FUNCTION fail_window_insert()"))

    async with s["uow"]() as u:
        row = await u.session.get(ExamAttempt, attempt.id)
    async with s["engine"].connect() as connection:
        locked = await connection.scalar(text("SELECT count(*) FROM project_type_question_lock"))
        finished_events = await connection.scalar(text("SELECT count(*) FROM attempt_event WHERE action='finished'"))
    assert (row.status, row.version, row.finished_at) == ("speaking", 1, None)
    assert locked == 0
    assert finished_events == 0
    assert await count(s, "assessment_window") == 0


async def test_commands_after_finish_conflict(seeded):
    s = seeded
    registration = await organized(s)
    attempt, _ = await start(s, registration)
    await finish(s, attempt, now=NOW + timedelta(minutes=10))
    for call in (
        lambda svc: svc.questions(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=2), s["users"]["teacher"]
        ),
        lambda svc: svc.pause(
            s["workspace"], s["exams"][0], attempt.id, AttemptPause(expected_version=2), s["users"]["teacher"]
        ),
        lambda svc: svc.resume(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=2), s["users"]["teacher"]
        ),
    ):
        with pytest.raises(BusinessLogicError) as error:
            async with s["uow"]() as u:
                await call(attempt_service(u))
        assert error.value.detail["code"] == "attempt_finished"


async def test_http_full_attempt_cycle_reports_server_state(seeded):
    s = seeded
    registration = await organized(s)
    app = FastAPI()
    app.include_router(routers)

    async def test_uow():
        async with s["uow"]() as u:
            yield u

    app.dependency_overrides[get_uow] = test_uow
    actor = {"user": s["users"]["teacher"]}
    app.dependency_overrides[get_current_user] = lambda: actor["user"]
    base = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post(base, json={"registration_id": registration.id, "expected_version": 1})
        assert started.status_code == 201
        body = started.json()
        assert body["status"] == "speaking" and body["version"] == 1
        assert 0 < body["remaining_seconds"] <= 420
        assert body["phase_deadline"] > body["server_now"]

        repeated = await client.post(base, json={"registration_id": registration.id, "expected_version": 1})
        assert repeated.status_code == 200 and repeated.json()["id"] == body["id"]

        questions = await client.post(f"{base}/{body['id']}/questions", json={"expected_version": 1})
        assert questions.status_code == 200 and questions.json()["status"] == "questions"

        actor["user"] = s["users"]["member"]
        reloaded = await client.get(f"{base}/current")
        assert reloaded.status_code == 200
        assert reloaded.json()["attempt"]["status"] == "questions"
        assert reloaded.json()["attempt"]["phase_deadline"] == questions.json()["phase_deadline"]

        denied = await client.post(f"{base}/{body['id']}/finish", json={"expected_version": 2})
        assert denied.status_code == 403

        actor["user"] = s["users"]["teacher"]
        finished = await client.post(f"{base}/{body['id']}/finish", json={"expected_version": 2})
        assert finished.status_code == 200
        result = finished.json()
        assert result["status"] == "finished" and result["remaining_seconds"] == 0
        window = result["assessment_window"]
        opened = datetime.fromisoformat(window["opened_at"])
        closes = datetime.fromisoformat(window["closes_at"])
        assert closes - opened == timedelta(minutes=3)

        second_finish = await client.post(f"{base}/{body['id']}/finish", json={"expected_version": 2})
        assert second_finish.status_code == 200
        assert second_finish.json()["assessment_window"]["closes_at"] == window["closes_at"]


ATTEMPT_COLUMNS = (
    "workspace_id, exam_id, registration_id, project_id, project_type_id, status, version, settings_version, "
    "started_at, phase_started_at, phase_deadline, paused_at, paused_seconds, finished_at, created_by, created_at, updated_at"
)


async def test_database_constraints_backstop_one_attempt_and_one_running(seeded):
    s = seeded
    first = await organized(s)
    second = await organized(s, project="manager2")
    await start(s, first)
    values = dict(  # noqa: C408
        workspace_id=s["workspace"],
        exam_id=s["exams"][0],
        registration_id=first.id,
        project_id=first.project_id,
        project_type_id=first.project_type_id_at_registration,
        status="speaking",
        version=1,
        settings_version=1,
        started_at=NOW,
        phase_started_at=NOW,
        phase_deadline=NOW + timedelta(minutes=7),
        paused_at=None,
        paused_seconds=0,
        finished_at=None,
        created_by=s["users"]["teacher"].id,
        created_at=NOW,
        updated_at=NOW,
    )
    with pytest.raises(IntegrityError):
        async with s["engine"].begin() as connection:
            await connection.execute(
                text(
                    f"INSERT INTO exam_attempt ({ATTEMPT_COLUMNS}) VALUES (:workspace_id, :exam_id, :registration_id, :project_id, :project_type_id, :status, :version, :settings_version, :started_at, :phase_started_at, :phase_deadline, :paused_at, :paused_seconds, :finished_at, :created_by, :created_at, :updated_at)"
                ),
                values,
            )
    with pytest.raises(IntegrityError):
        async with s["engine"].begin() as connection:
            await connection.execute(
                text(
                    f"INSERT INTO exam_attempt ({ATTEMPT_COLUMNS}) VALUES (:workspace_id, :exam_id, :registration_id, :project_id, :project_type_id, :status, :version, :settings_version, :started_at, :phase_started_at, :phase_deadline, :paused_at, :paused_seconds, :finished_at, :created_by, :created_at, :updated_at)"
                ),
                {**values, "registration_id": second.id, "project_id": second.project_id},
            )
    assert await count(s, "exam_attempt") == 1


async def test_database_constraints_require_finished_timestamp(seeded):
    s = seeded
    registration = await organized(s)
    values = dict(  # noqa: C408
        workspace_id=s["workspace"],
        exam_id=s["exams"][0],
        registration_id=registration.id,
        project_id=registration.project_id,
        project_type_id=registration.project_type_id_at_registration,
        status="finished",
        version=1,
        settings_version=1,
        started_at=NOW,
        phase_started_at=NOW,
        phase_deadline=NOW + timedelta(minutes=7),
        paused_at=None,
        paused_seconds=0,
        finished_at=None,
        created_by=s["users"]["teacher"].id,
        created_at=NOW,
        updated_at=NOW,
    )
    with pytest.raises(IntegrityError):
        async with s["engine"].begin() as connection:
            await connection.execute(
                text(
                    f"INSERT INTO exam_attempt ({ATTEMPT_COLUMNS}) VALUES (:workspace_id, :exam_id, :registration_id, :project_id, :project_type_id, :status, :version, :settings_version, :started_at, :phase_started_at, :phase_deadline, :paused_at, :paused_seconds, :finished_at, :created_by, :created_at, :updated_at)"
                ),
                values,
            )
