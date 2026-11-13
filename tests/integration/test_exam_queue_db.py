from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx
import pytest
import test_exam_attempts_db as attempt_cases
import test_exam_registrations_db as registration_cases
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from test_exam_registrations_db import NOW, START, count, reg_service, wait_until_blocked

from src.api.v1.routes import routers
from src.core.container import get_uow
from src.core.dependencies import get_current_user
from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.model.exam import Exam
from src.model.exam_attempt import AttemptEvent, ExamAttempt
from src.model.exam_registration import RegistrationEvent
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_registration_repository import ExamRegistrationRepository
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam_attempt import AttemptCommand, AttemptPause, AttemptPostpone, AttemptRestart, AttemptStart
from src.schema.exam_queue import QueueCommand, QueuePlace, QueueReason
from src.schema.exam_registration import (
    RegistrationCancel,
    RegistrationCreate,
    RegistrationMove,
    SlotBatchCreate,
)
from src.services.exam_attempt_service import ExamAttemptService
from src.services.exam_queue_service import ExamQueueService
from src.services.exam_service import ExamService

pytestmark = pytest.mark.integration

seeded = registration_cases.seeded


def queue_service(uow, now=NOW):
    exam_service = ExamService(ExamRepository(uow), ProjectTypeQuestionRepository(uow))
    return ExamQueueService(
        ExamRegistrationRepository(uow),
        ExamAttemptRepository(uow),
        ExamRepository(uow),
        exam_service,
        clock=lambda: now,
    )


def attempt_service(uow, now=NOW):
    exam_service = ExamService(ExamRepository(uow), ProjectTypeQuestionRepository(uow))
    queue = queue_service(uow, now)
    return ExamAttemptService(
        ExamAttemptRepository(uow),
        ExamRepository(uow),
        reg_service(uow, now),
        exam_service,
        queue,
        ExamRegistrationRepository(uow),
        clock=lambda: now,
    )


async def register(s, project="manager", exam=0, slot_id=None):
    async with s["uow"]() as u:
        return await reg_service(u).create_organized(
            s["workspace"],
            s["exams"][exam],
            RegistrationCreate(project_id=s["projects"][project], slot_id=slot_id),
            s["users"]["teacher"],
        )


async def read_queue(s, exam=0):
    async with s["uow"]() as u:
        return await queue_service(u).read(s["workspace"], s["exams"][exam], s["users"]["teacher"])


async def read_registration(s, registration_id, exam=0):
    async with s["uow"]() as u:
        return await ExamRegistrationRepository(u).registration(s["workspace"], s["exams"][exam], registration_id)


async def revision(s, exam=0):
    async with s["uow"]() as u:
        return await u.session.scalar(select(Exam.queue_revision).where(Exam.id == s["exams"][exam]))


async def test_initial_order_and_place_next(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    third = await register(s, "member")
    before = await read_queue(s)
    assert [item.registration_id for item in before.items] == [first.id, second.id, third.id]
    assert [item.position for item in before.items] == [1, 2, 3]
    assert all(item.state == "waiting" for item in before.items)
    revision_before = before.queue_revision

    async with s["uow"]() as u:
        placed = await queue_service(u).next(
            s["workspace"],
            s["exams"][0],
            third.id,
            QueueCommand(expected_version=third.version),
            s["users"]["teacher"],
        )
    assert placed.item.position == 1
    assert placed.item.registration_version == third.version + 1
    assert placed.queue_revision == revision_before + 1
    after = await read_queue(s)
    assert [item.registration_id for item in after.items] == [third.id, first.id, second.id]
    assert [item.position for item in after.items] == [1, 2, 3]

    async with s["uow"]() as u:
        repeated = await queue_service(u).next(
            s["workspace"],
            s["exams"][0],
            third.id,
            QueueCommand(expected_version=third.version),
            s["users"]["teacher"],
        )
    assert repeated.item.registration_version == third.version + 1
    assert repeated.queue_revision == revision_before + 1
    async with s["uow"]() as u:
        events = (
            await u.session.scalars(select(RegistrationEvent).where(RegistrationEvent.registration_id == third.id))
        ).all()
    assert [event.action for event in events] == ["created", "queue_changed"]
    assert events[-1].from_position == 3
    assert events[-1].to_position == 1
    assert events[-1].actor_id == s["users"]["teacher"].id


async def test_slot_order_and_place_out_of_range(seeded):
    s = seeded
    async with s["uow"]() as u:
        await reg_service(u).add_slots(
            s["workspace"],
            s["exams"][0],
            registration_cases.intervals(),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        slots = await ExamRegistrationRepository(u).all_slots(s["exams"][0])
    later = await register(s, "manager", slot_id=slots[1].id)
    earlier = await register(s, "manager2", slot_id=slots[0].id)
    state = await read_queue(s)
    assert [item.registration_id for item in state.items] == [earlier.id, later.id]
    assert [item.position for item in state.items] == [1, 2]
    assert state.items[0].planned_start_at == slots[0].starts_at

    async with s["uow"]() as u:
        with pytest.raises(BusinessLogicError) as error:
            await queue_service(u).place(
                s["workspace"],
                s["exams"][0],
                later.id,
                QueuePlace(expected_version=later.version, position=4),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "queue_position_out_of_range"


async def test_postpone_queue_and_return(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    async with s["uow"]() as u:
        postponed = await queue_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueueReason(expected_version=first.version, reason="Проектор"),
            s["users"]["teacher"],
        )
    assert postponed.item.state == "postponed"
    assert postponed.item.position is None
    assert postponed.item.attempt is None
    assert postponed.queue_revision >= 1
    state = await read_queue(s)
    assert [item.registration_id for item in state.items] == [second.id, first.id]
    assert state.items[0].position == 1
    assert state.items[1].state == "postponed"
    assert await count(s, "assessment_window") == 0
    assert await count(s, "project_type_question_lock") == 0

    async with s["uow"]() as u:
        returned = await queue_service(u).place(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueuePlace(expected_version=first.version + 1),
            s["users"]["teacher"],
        )
    assert returned.item.state == "waiting"
    assert returned.item.position == 2
    async with s["uow"]() as u:
        events = (
            await u.session.scalars(select(RegistrationEvent).where(RegistrationEvent.registration_id == first.id))
        ).all()
    assert [event.action for event in events] == ["created", "postponed", "returned"]
    assert events[1].reason == "Проектор"
    assert events[1].occurred_at == NOW
    assert events[2].from_position is None
    assert events[2].to_position == 2


async def test_postpone_running_releases_mic_and_restart_resets_timer(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    async with s["uow"]() as u:
        attempt, created = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=first.version),
            s["users"]["teacher"],
        )
    assert created is True
    assert attempt.status == "speaking"
    async with s["uow"]() as u:
        paused = await attempt_service(u, NOW + timedelta(minutes=2)).pause(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPause(expected_version=attempt.version, reason="Перерыв"),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        postponed = await attempt_service(u, NOW + timedelta(minutes=4)).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=paused.version, reason="Проектор"),
            s["users"]["teacher"],
        )
    assert postponed.status == "postponed"
    assert postponed.paused_seconds == 120
    assert postponed.postponed_at == NOW + timedelta(minutes=4)
    assert await count(s, "assessment_window") == 0
    assert await count(s, "project_type_question_lock") == 0

    async with s["uow"]() as u:
        other, created_other = await attempt_service(u, NOW + timedelta(minutes=5)).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=second.id, expected_version=second.version),
            s["users"]["teacher"],
        )
    assert created_other is True
    assert other.status == "speaking"

    async with s["uow"]() as u:
        with pytest.raises(BusinessLogicError) as error:
            await attempt_service(u).restart(
                s["workspace"],
                s["exams"][0],
                attempt.id,
                AttemptRestart(expected_version=postponed.version),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "another_defense_active"

    async with s["uow"]() as u:
        await attempt_service(u, NOW + timedelta(minutes=8)).finish(
            s["workspace"],
            s["exams"][0],
            other.id,
            AttemptCommand(expected_version=other.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        restarted = await attempt_service(u, NOW + timedelta(minutes=20)).restart(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptRestart(expected_version=postponed.version),
            s["users"]["teacher"],
        )
    assert restarted.id == attempt.id
    assert restarted.status == "speaking"
    assert restarted.postponed_at is None
    assert restarted.phase_started_at == NOW + timedelta(minutes=20)
    assert restarted.phase_deadline == NOW + timedelta(minutes=27)
    assert restarted.version == postponed.version + 1
    async with s["uow"]() as u:
        events = (
            await u.session.scalars(
                select(AttemptEvent).where(AttemptEvent.attempt_id == attempt.id).order_by(AttemptEvent.version)
            )
        ).all()
    assert [event.action for event in events] == ["started", "paused", "postponed", "restarted"]
    assert events[2].occurred_at == NOW + timedelta(minutes=4)
    assert events[3].occurred_at == NOW + timedelta(minutes=20)


async def test_no_show_is_separate_and_return_works(seeded):
    s = seeded
    first = await register(s, "manager")
    async with s["uow"]() as u:
        marked = await queue_service(u).no_show(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueueReason(expected_version=first.version, reason="Не пришла"),
            s["users"]["teacher"],
        )
    assert marked.item.state == "no_show"
    assert marked.item.position is None
    assert await count(s, "exam_attempt") == 0
    assert await count(s, "assessment_window") == 0

    async with s["uow"]() as u:
        returned = await queue_service(u).place(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueuePlace(expected_version=first.version + 1),
            s["users"]["teacher"],
        )
    assert returned.item.state == "waiting"
    async with s["uow"]() as u:
        started, created = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=returned.item.registration_version),
            s["users"]["teacher"],
        )
    assert created is True
    assert started.status == "speaking"


async def test_finished_defense_is_preserved(seeded):
    s = seeded
    first = await register(s, "manager")
    async with s["uow"]() as u:
        attempt, _ = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=first.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        finished = await attempt_service(u, NOW + timedelta(minutes=7)).finish(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptCommand(expected_version=attempt.version),
            s["users"]["teacher"],
        )
    assert finished.status == "finished"
    async with s["uow"]() as u:
        registration = await ExamRegistrationRepository(u).registration(s["workspace"], s["exams"][0], first.id)
        with pytest.raises(BusinessLogicError) as error:
            await queue_service(u).postpone(
                s["workspace"],
                s["exams"][0],
                first.id,
                QueueReason(expected_version=registration.version, reason="Поздно"),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "defense_already_started"
    async with s["uow"]() as u:
        with pytest.raises(BusinessLogicError) as no_show_error:
            await queue_service(u).no_show(
                s["workspace"],
                s["exams"][0],
                first.id,
                QueueReason(expected_version=registration.version, reason="Не пришла"),
                s["users"]["teacher"],
            )
    assert no_show_error.value.detail["code"] == "defense_already_started"
    async with s["uow"]() as u:
        with pytest.raises(BusinessLogicError) as error:
            await attempt_service(u).restart(
                s["workspace"],
                s["exams"][0],
                attempt.id,
                AttemptRestart(expected_version=finished.version),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "attempt_finished"
    assert await count(s, "assessment_window") == 1
    async with s["uow"]() as u:
        window = await u.session.scalar(select(ExamAttempt).where(ExamAttempt.id == attempt.id))
    assert window.status == "finished"


async def test_start_requires_queue_and_postponed_attempt_conflicts(seeded):
    s = seeded
    first = await register(s, "manager")
    async with s["uow"]() as u:
        await queue_service(u).no_show(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueueReason(expected_version=first.version, reason="Не пришла"),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        with pytest.raises(BusinessLogicError) as error:
            await attempt_service(u).start(
                s["workspace"],
                s["exams"][0],
                AttemptStart(registration_id=first.id, expected_version=first.version + 1),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "registration_not_queued"

    async with s["uow"]() as u:
        returned = await queue_service(u).place(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueuePlace(expected_version=first.version + 1),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        attempt, created = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=returned.item.registration_version),
            s["users"]["teacher"],
        )
    assert created is True
    async with s["uow"]() as u:
        postponed = await attempt_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=attempt.version, reason="Проектор"),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        with pytest.raises(BusinessLogicError) as error:
            await attempt_service(u).start(
                s["workspace"],
                s["exams"][0],
                AttemptStart(registration_id=first.id, expected_version=returned.item.registration_version + 1),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "attempt_postponed"
    assert postponed.status == "postponed"


async def test_postpone_repeat_is_noop_and_finish_from_postponed_opens_window(seeded):
    s = seeded
    first = await register(s, "manager")
    async with s["uow"]() as u:
        attempt, _ = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=first.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        postponed = await attempt_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=attempt.version, reason="Проектор"),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        repeated = await attempt_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=attempt.version, reason="Ещё раз"),
            s["users"]["teacher"],
        )
    assert repeated.version == postponed.version
    assert repeated.status == "postponed"
    async with s["uow"]() as u:
        events = (
            await u.session.scalars(
                select(AttemptEvent).where(AttemptEvent.attempt_id == attempt.id).order_by(AttemptEvent.version)
            )
        ).all()
    assert [event.action for event in events] == ["started", "postponed"]

    async with s["uow"]() as u:
        finished = await attempt_service(u, NOW + timedelta(minutes=10)).finish(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptCommand(expected_version=postponed.version),
            s["users"]["teacher"],
        )
    assert finished.status == "finished"
    assert finished.assessment_window is not None
    assert await count(s, "assessment_window") == 1
    async with s["uow"]() as u:
        repeated_finish = await attempt_service(u, NOW + timedelta(minutes=12)).finish(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptCommand(expected_version=finished.version),
            s["users"]["teacher"],
        )
    assert repeated_finish.assessment_window.closes_at == finished.assessment_window.closes_at
    assert await count(s, "assessment_window") == 1


async def test_place_guards_for_running_and_finished(seeded):
    s = seeded
    first = await register(s, "manager")
    async with s["uow"]() as u:
        attempt, _ = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=first.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        registration = await ExamRegistrationRepository(u).registration(s["workspace"], s["exams"][0], first.id)
        with pytest.raises(BusinessLogicError) as error:
            await queue_service(u).place(
                s["workspace"],
                s["exams"][0],
                first.id,
                QueuePlace(expected_version=registration.version),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "attempt_running"
    async with s["uow"]() as u:
        finished = await attempt_service(u, NOW + timedelta(minutes=7)).finish(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptCommand(expected_version=attempt.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        registration = await ExamRegistrationRepository(u).registration(s["workspace"], s["exams"][0], first.id)
        with pytest.raises(BusinessLogicError) as error:
            await queue_service(u).place(
                s["workspace"],
                s["exams"][0],
                first.id,
                QueuePlace(expected_version=registration.version),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "attempt_finished"
    assert finished.status == "finished"


async def test_no_show_from_postponed_and_read_order(seeded):
    s = seeded
    waiting = await register(s, "manager")
    postponed = await register(s, "manager2")
    absent = await register(s, "member")
    finished = await register(s, "local_manager")
    async with s["uow"]() as u:
        await queue_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            postponed.id,
            QueueReason(expected_version=postponed.version, reason="Проектор"),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        await queue_service(u).no_show(
            s["workspace"],
            s["exams"][0],
            absent.id,
            QueueReason(expected_version=absent.version, reason="Не пришла"),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        await queue_service(u).no_show(
            s["workspace"],
            s["exams"][0],
            postponed.id,
            QueueReason(expected_version=postponed.version + 1, reason="Передумали ждать"),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        attempt, _ = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=finished.id, expected_version=finished.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        await attempt_service(u, NOW + timedelta(minutes=7)).finish(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptCommand(expected_version=attempt.version),
            s["users"]["teacher"],
        )
    state = await read_queue(s)
    assert [item.state for item in state.items] == ["waiting", "no_show", "no_show", "finished"]
    assert state.items[0].registration_id == waiting.id
    assert state.items[-1].registration_id == finished.id
    assert state.items[0].position == 1


async def test_slot_change_does_not_move_queue_and_revision_tracks_membership(seeded):
    s = seeded
    async with s["uow"]() as u:
        await reg_service(u).add_slots(
            s["workspace"], s["exams"][0], registration_cases.intervals(), s["users"]["teacher"]
        )
    async with s["uow"]() as u:
        slots = await ExamRegistrationRepository(u).all_slots(s["exams"][0])
    first = await register(s, "manager", slot_id=slots[0].id)
    revision_after_create = await revision(s)
    async with s["uow"]() as u:
        moved = await reg_service(u).move_self(
            s["workspace"],
            s["exams"][0],
            first.id,
            RegistrationMove(
                expected_version=first.version, target_exam_id=s["exams"][0], target_slot_id=slots[1].id, reason="Слот"
            ),
            s["users"]["manager"],
        )
    assert moved.source.slot_id == slots[1].id
    assert moved.source.queue_position == 1
    assert await revision(s) == revision_after_create

    await register(s, "manager2", slot_id=slots[0].id)
    assert await revision(s) == revision_after_create + 1
    async with s["uow"]() as u:
        current = await ExamRegistrationRepository(u).registration(s["workspace"], s["exams"][0], first.id)
        await reg_service(u).cancel_organized(
            s["workspace"],
            s["exams"][0],
            first.id,
            RegistrationCancel(expected_version=current.version, reason="Передумали"),
            s["users"]["teacher"],
        )
    assert await revision(s) == revision_after_create + 2
    remaining = await read_registration(s, (await read_queue(s)).items[0].registration_id)
    assert remaining.queue_position == 1


async def test_queue_access_control(seeded):
    s = seeded
    first = await register(s, "manager")
    async with s["uow"]() as u:
        await queue_service(u).read(s["workspace"], s["exams"][0], s["users"]["member"])
    async with s["uow"]() as u:
        with pytest.raises(PermissionError):
            await queue_service(u).place(
                s["workspace"],
                s["exams"][0],
                first.id,
                QueuePlace(expected_version=first.version),
                s["users"]["manager"],
            )
    async with s["uow"]() as u:
        with pytest.raises(NotFoundError):
            await queue_service(u).read(s["foreign_workspace"], s["exams"][0], s["users"]["teacher"])
    async with s["uow"]() as u:
        with pytest.raises(NotFoundError):
            await queue_service(u).read(s["workspace"], s["draft"], s["users"]["member"])


async def test_concurrent_place_commands_serialize(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    third = await register(s, "member")
    base_revision = await revision(s)
    entered = asyncio.Event()
    other_pid = []

    async def contender():
        try:
            async with s["uow"]() as u:
                other_pid.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                entered.set()
                return await queue_service(u).next(
                    s["workspace"],
                    s["exams"][0],
                    second.id,
                    QueueCommand(expected_version=second.version),
                    s["users"]["teacher"],
                )
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as holder:
        await queue_service(holder).next(
            s["workspace"],
            s["exams"][0],
            third.id,
            QueueCommand(expected_version=third.version),
            s["users"]["teacher"],
        )
        task = asyncio.create_task(contender())
        await entered.wait()
        await wait_until_blocked(s, other_pid[0])
    result = await asyncio.wait_for(task, 10)
    assert not isinstance(result, str)
    assert await revision(s) == base_revision + 2
    state = await read_queue(s)
    assert [item.registration_id for item in state.items] == [second.id, third.id, first.id]
    assert [item.position for item in state.items] == [1, 2, 3]


async def test_concurrent_place_and_start_are_serialized(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
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
                    AttemptStart(registration_id=second.id, expected_version=second.version),
                    s["users"]["teacher"],
                )
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as holder:
        await queue_service(holder).next(
            s["workspace"],
            s["exams"][0],
            second.id,
            QueueCommand(expected_version=second.version),
            s["users"]["teacher"],
        )
        task = asyncio.create_task(contender())
        await entered.wait()
        await wait_until_blocked(s, other_pid[0])
    assert await asyncio.wait_for(task, 10) == "registration_version_conflict"
    assert await count(s, "exam_attempt") == 0
    state = await read_queue(s)
    assert [item.registration_id for item in state.items] == [second.id, first.id]
    assert [item.position for item in state.items] == [1, 2]
    fresh = await read_registration(s, second.id)
    async with s["uow"]() as u:
        attempt, created = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=second.id, expected_version=fresh.version),
            s["users"]["teacher"],
        )
    assert created is True
    assert attempt.status == "speaking"
    state = await read_queue(s)
    assert state.items[0].registration_id == second.id
    assert state.items[0].state == "running"
    assert state.items[1].registration_id == first.id
    assert state.items[1].position == 1
    assert await count(s, "exam_attempt") == 1


async def test_concurrent_postpone_and_finish_are_serialized(seeded):
    s = seeded
    first = await register(s, "manager")
    async with s["uow"]() as u:
        attempt, _ = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=first.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        postponed = await attempt_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=attempt.version, reason="Проектор"),
            s["users"]["teacher"],
        )
    entered = asyncio.Event()
    other_pid = []

    async def contender():
        try:
            async with s["uow"]() as u:
                other_pid.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                entered.set()
                return await attempt_service(u).finish(
                    s["workspace"],
                    s["exams"][0],
                    attempt.id,
                    AttemptCommand(expected_version=postponed.version),
                    s["users"]["teacher"],
                )
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as holder:
        await attempt_service(holder).restart(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptRestart(expected_version=postponed.version),
            s["users"]["teacher"],
        )
        task = asyncio.create_task(contender())
        await entered.wait()
        await wait_until_blocked(s, other_pid[0])
    assert await asyncio.wait_for(task, 10) == "attempt_version_conflict"
    async with s["uow"]() as u:
        fresh = await attempt_service(u).get(s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"])
    assert fresh.status == "speaking"
    async with s["uow"]() as u:
        finished = await attempt_service(u).finish(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptCommand(expected_version=fresh.version),
            s["users"]["teacher"],
        )
    assert finished.status == "finished"
    assert await count(s, "assessment_window") == 1


async def test_concurrent_restart_and_start_leave_one_running(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    async with s["uow"]() as u:
        attempt, _ = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=first.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        postponed = await attempt_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=attempt.version, reason="Проектор"),
            s["users"]["teacher"],
        )
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
                    AttemptStart(registration_id=second.id, expected_version=second.version),
                    s["users"]["teacher"],
                )
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as holder:
        await attempt_service(holder).restart(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptRestart(expected_version=postponed.version),
            s["users"]["teacher"],
        )
        task = asyncio.create_task(contender())
        await entered.wait()
        await wait_until_blocked(s, other_pid[0])
    result = await asyncio.wait_for(task, 10)
    assert result == "another_defense_active"
    async with s["uow"]() as u:
        running = await ExamAttemptRepository(u).running(s["exams"][0])
    assert running is not None and running.id == attempt.id


async def test_deferred_queue_event_failure_rolls_back(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    async with s["engine"].begin() as connection:
        await connection.execute(
            text(
                """CREATE FUNCTION reject_queue_event() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='postponed' THEN RAISE EXCEPTION 'test deferred queue failure'; END IF; RETURN NEW; END $$"""
            )
        )
        await connection.execute(
            text(
                "CREATE CONSTRAINT TRIGGER reject_queue_event AFTER INSERT ON registration_event DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_queue_event()"
            )
        )
    with pytest.raises(DBAPIError):
        async with s["uow"]() as u:
            await queue_service(u).postpone(
                s["workspace"],
                s["exams"][0],
                first.id,
                QueueReason(expected_version=first.version, reason="Проектор"),
                s["users"]["teacher"],
            )
    state = await read_queue(s)
    assert [item.registration_id for item in state.items] == [first.id, second.id]
    assert [item.position for item in state.items] == [1, 2]
    assert await count(s, "registration_event") == 2


async def test_reload_returns_same_server_deadlines(seeded):
    s = seeded
    first = await register(s, "manager")
    async with s["uow"]() as u:
        attempt, _ = await attempt_service(u, NOW + timedelta(minutes=2)).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=first.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        postponed = await attempt_service(u, NOW + timedelta(minutes=4)).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=attempt.version, reason="Проектор"),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        current = await attempt_service(u, NOW + timedelta(minutes=6)).current(
            s["workspace"], s["exams"][0], s["users"]["teacher"]
        )
        state = await queue_service(u, NOW + timedelta(minutes=6)).read(
            s["workspace"], s["exams"][0], s["users"]["teacher"]
        )
    assert current.attempt.id == attempt.id
    assert current.attempt.status == "postponed"
    item = state.items[0]
    assert item.attempt.phase_deadline == postponed.phase_deadline
    assert item.attempt.remaining_seconds == postponed.remaining_seconds
    assert item.attempt.server_now == NOW + timedelta(minutes=6)

    async with s["uow"]() as u:
        restarted = await attempt_service(u, NOW + timedelta(minutes=20)).restart(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptRestart(expected_version=postponed.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        reloaded = await attempt_service(u, NOW + timedelta(minutes=21)).get(
            s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"]
        )
    assert reloaded.phase_deadline == restarted.phase_deadline
    assert reloaded.phase_started_at == NOW + timedelta(minutes=20)


async def test_http_queue_and_attempt_flow(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    app = FastAPI()
    app.include_router(routers)

    async def test_uow():
        async with s["uow"]() as u:
            yield u

    app.dependency_overrides[get_uow] = test_uow
    app.dependency_overrides[get_current_user] = lambda: s["users"]["teacher"]
    base = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/queue"
    attempts = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        snapshot = await client.get(base)
        assert snapshot.status_code == 200
        assert [item["registration_id"] for item in snapshot.json()["items"]] == [first.id, second.id]
        next_response = await client.post(f"{base}/{second.id}/next", json={"expected_version": second.version})
        assert next_response.status_code == 200
        assert next_response.json()["item"]["position"] == 1
        postponed = await client.post(
            f"{base}/{first.id}/postpone", json={"expected_version": first.version, "reason": "Проектор"}
        )
        assert postponed.status_code == 200
        assert postponed.json()["item"]["state"] == "postponed"
        no_show = await client.post(
            f"{base}/{second.id}/no-show", json={"expected_version": second.version + 1, "reason": "Не пришла"}
        )
        assert no_show.status_code == 200
        assert no_show.json()["item"]["state"] == "no_show"
        returned = await client.post(f"{base}/{first.id}/place", json={"expected_version": first.version + 1})
        assert returned.status_code == 200
        assert returned.json()["item"]["state"] == "waiting"
        started = await client.post(
            attempts,
            json={"registration_id": first.id, "expected_version": returned.json()["item"]["registration_version"]},
        )
        assert started.status_code == 201
        body = started.json()
        attempt_id = body["id"]
        resumed = await client.post(f"{attempts}/{attempt_id}/postpone", json={"expected_version": 1, "reason": "Сбой"})
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "postponed"
        current = await client.get(f"{attempts}/current")
        assert current.status_code == 200
        assert current.json()["attempt"]["status"] == "postponed"
        restarted = await client.post(
            f"{attempts}/{attempt_id}/restart", json={"expected_version": resumed.json()["version"]}
        )
        assert restarted.status_code == 200
        assert restarted.json()["status"] == "speaking"
        finished = await client.post(
            f"{attempts}/{attempt_id}/finish", json={"expected_version": restarted.json()["version"]}
        )
        assert finished.status_code == 200
        assert finished.json()["assessment_window"] is not None
    assert await count(s, "assessment_window") == 1


async def test_http_queue_mutations_require_organizer(seeded):
    s = seeded
    first = await register(s, "manager")
    app = FastAPI()
    app.include_router(routers)

    async def test_uow():
        async with s["uow"]() as u:
            yield u

    app.dependency_overrides[get_uow] = test_uow
    app.dependency_overrides[get_current_user] = lambda: s["users"]["member"]
    base = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/queue"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        assert (await client.get(base)).status_code == 200
        assert (
            await client.post(f"{base}/{first.id}/place", json={"expected_version": first.version})
        ).status_code == 403


async def test_migration_backfills_slot_and_slotless_order(seeded, run_migrations):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    async with s["uow"]() as u:
        await queue_service(u).next(
            s["workspace"],
            s["exams"][0],
            second.id,
            QueueCommand(expected_version=second.version),
            s["users"]["teacher"],
        )
    day = START + timedelta(days=1)
    async with s["uow"]() as u:
        await reg_service(u).add_slots(
            s["workspace"],
            s["exams"][1],
            SlotBatchCreate(
                slots=[
                    {"starts_at": day, "ends_at": day + timedelta(minutes=15)},
                    {"starts_at": day + timedelta(minutes=15), "ends_at": day + timedelta(minutes=30)},
                ]
            ),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        slots = await ExamRegistrationRepository(u).all_slots(s["exams"][1])
    later = await register(s, "member", exam=1, slot_id=slots[1].id)
    earlier = await register(s, "local_manager", exam=1, slot_id=slots[0].id)
    async with s["uow"]() as u:
        await queue_service(u).next(
            s["workspace"], s["exams"][1], later.id, QueueCommand(expected_version=later.version), s["users"]["teacher"]
        )
    started_registration = await register(s, "demoted")
    async with s["uow"]() as u:
        await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=started_registration.id, expected_version=started_registration.version),
            s["users"]["teacher"],
        )
    cancelled = await register(s, "null_manager")
    async with s["uow"]() as u:
        await reg_service(u).cancel_organized(
            s["workspace"],
            s["exams"][0],
            cancelled.id,
            RegistrationCancel(expected_version=cancelled.version, reason="Передумали"),
            s["users"]["teacher"],
        )
    await s["engine"].dispose()
    run_migrations(s["url"], "downgrade", "d107a10b20c6")
    run_migrations(s["url"], "upgrade", "head")
    slotless = await read_queue(s, 0)
    by_id = {item.registration_id: item for item in slotless.items}
    assert set(by_id) == {first.id, second.id, started_registration.id}
    assert by_id[first.id].position == 1
    assert by_id[second.id].position == 2
    assert by_id[started_registration.id].position is None
    slotted = await read_queue(s, 1)
    assert [item.registration_id for item in slotted.items] == [earlier.id, later.id]
    assert [item.position for item in slotted.items] == [1, 2]
    assert (await read_registration(s, started_registration.id, 0)).queue_position is None
    async with s["uow"]() as u:
        cancelled_position = await u.session.scalar(
            text("SELECT queue_position FROM exam_registration WHERE id=:id"), {"id": cancelled.id}
        )
    assert cancelled_position is None
    assert await revision(s, 0) == 0


async def test_queue_and_attempt_constraints(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    with pytest.raises(IntegrityError):
        async with s["uow"]() as u:
            await u.session.execute(
                text("UPDATE exam_registration SET queue_position=1 WHERE id=:id"), {"id": second.id}
            )
    with pytest.raises(IntegrityError):
        async with s["uow"]() as u:
            await u.session.execute(
                text("UPDATE exam_registration SET queue_hold='postponed' WHERE id=:id"), {"id": first.id}
            )
    async with s["uow"]() as u:
        attempt, _ = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=first.version),
            s["users"]["teacher"],
        )
    with pytest.raises(IntegrityError):
        async with s["uow"]() as u:
            await u.session.execute(text("UPDATE exam_attempt SET status='postponed' WHERE id=:id"), {"id": attempt.id})
    with pytest.raises(IntegrityError):
        async with s["uow"]() as u:
            await u.session.execute(
                text(
                    "UPDATE exam_attempt SET status='postponed', postponed_at=now(), "
                    "postponed_phase='speaking', paused_at=now() WHERE id=:id"
                ),
                {"id": attempt.id},
            )


async def test_postpone_from_questions_and_no_show_guard(seeded):
    s = seeded
    first = await register(s, "manager")
    async with s["uow"]() as u:
        attempt, _ = await attempt_service(u, NOW).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=first.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        questions = await attempt_service(u, NOW + timedelta(minutes=7)).questions(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptCommand(expected_version=attempt.version),
            s["users"]["teacher"],
        )
    assert questions.status == "questions"
    async with s["uow"]() as u:
        postponed = await attempt_service(u, NOW + timedelta(minutes=9)).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=questions.version, reason="Сбой на вопросах"),
            s["users"]["teacher"],
        )
    assert postponed.status == "postponed"
    assert postponed.postponed_phase == "questions"
    async with s["uow"]() as u:
        restarted = await attempt_service(u, NOW + timedelta(minutes=30)).restart(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptRestart(expected_version=postponed.version),
            s["users"]["teacher"],
        )
    assert restarted.status == "questions"
    assert restarted.phase_deadline == NOW + timedelta(minutes=37)
    async with s["uow"]() as u:
        registration = await ExamRegistrationRepository(u).registration(s["workspace"], s["exams"][0], first.id)
        with pytest.raises(BusinessLogicError) as error:
            await queue_service(u).no_show(
                s["workspace"],
                s["exams"][0],
                first.id,
                QueueReason(expected_version=registration.version, reason="Не пришла"),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "defense_already_started"


async def test_restart_uses_settings_revision_from_start(seeded):
    s = seeded
    first = await register(s, "manager")
    async with s["uow"]() as u:
        attempt, _ = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=first.version),
            s["users"]["teacher"],
        )
    await attempt_cases.set_settings(s, expected_version=1, presentation_minutes=10)
    async with s["uow"]() as u:
        postponed = await attempt_service(u, NOW + timedelta(minutes=3)).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=attempt.version, reason="Проектор"),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        restarted = await attempt_service(u, NOW + timedelta(minutes=10)).restart(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptRestart(expected_version=postponed.version),
            s["users"]["teacher"],
        )
    assert restarted.settings_version == 1
    assert restarted.phase_deadline == NOW + timedelta(minutes=17)


async def test_cross_exam_move_releases_and_assigns_queue_positions(seeded):
    s = seeded
    first = await register(s, "manager")
    moving = await register(s, "member")
    async with s["uow"]() as u:
        target_exam = s["exams"][1]
        source_before = await ExamRepository(u).get_scoped(s["workspace"], s["exams"][0])
        target_before = await ExamRepository(u).get_scoped(s["workspace"], target_exam)
        moved = await reg_service(u).move_organized(
            s["workspace"],
            s["exams"][0],
            moving.id,
            RegistrationMove(
                expected_version=moving.version, target_exam_id=target_exam, target_slot_id=None, reason="Другая дата"
            ),
            s["users"]["teacher"],
        )
    source = await read_queue(s, 0)
    assert [item.registration_id for item in source.items] == [first.id]
    assert source.items[0].position == 1
    target = await read_queue(s, 1)
    assert [item.registration_id for item in target.items] == [moved.target.id]
    assert target.items[0].position == 1
    async with s["uow"]() as u:
        assert (
            await ExamRepository(u).get_scoped(s["workspace"], target_exam)
        ).queue_revision == target_before.queue_revision + 1
        assert (
            await ExamRepository(u).get_scoped(s["workspace"], s["exams"][0])
        ).queue_revision == source_before.queue_revision + 1


async def test_downgrade_finishes_postponed_attempt_without_window(seeded, run_migrations):
    s = seeded
    first = await register(s, "manager")
    async with s["uow"]() as u:
        attempt, _ = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=first.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        await attempt_service(u, NOW + timedelta(minutes=2)).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=attempt.version, reason="Проектор"),
            s["users"]["teacher"],
        )
    await s["engine"].dispose()
    run_migrations(s["url"], "downgrade", "d107a10b20c6")
    async with s["uow"]() as u:
        status, finished_at = (
            await u.session.execute(
                text("SELECT status, finished_at FROM exam_attempt WHERE id=:id"), {"id": attempt.id}
            )
        ).one()
        windows = await u.session.scalar(text("SELECT count(*) FROM assessment_window"))
    assert status == "finished"
    assert finished_at is not None
    assert windows == 0
    run_migrations(s["url"], "upgrade", "head")


async def test_postponed_attempt_rejects_phase_and_pause_commands(seeded):
    s = seeded
    first = await register(s, "manager")
    async with s["uow"]() as u:
        attempt, _ = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=first.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        postponed = await attempt_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=attempt.version, reason="Проектор"),
            s["users"]["teacher"],
        )
    for call in ("questions", "pause", "resume"):
        async with s["uow"]() as u:
            with pytest.raises(BusinessLogicError) as error:
                await getattr(attempt_service(u), call)(
                    s["workspace"],
                    s["exams"][0],
                    attempt.id,
                    AttemptCommand(expected_version=postponed.version),
                    s["users"]["teacher"],
                )
        assert error.value.detail["code"] == "attempt_postponed"


async def test_repeat_postpone_and_no_show_are_noops(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    async with s["uow"]() as u:
        postponed = await queue_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueueReason(expected_version=first.version, reason="Проектор"),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        repeated = await queue_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueueReason(expected_version=first.version, reason="Ещё раз"),
            s["users"]["teacher"],
        )
    assert repeated.item.registration_version == postponed.item.registration_version
    async with s["uow"]() as u:
        marked = await queue_service(u).no_show(
            s["workspace"],
            s["exams"][0],
            second.id,
            QueueReason(expected_version=second.version, reason="Не пришла"),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        repeated_no_show = await queue_service(u).no_show(
            s["workspace"],
            s["exams"][0],
            second.id,
            QueueReason(expected_version=second.version, reason="Не пришла"),
            s["users"]["teacher"],
        )
    assert repeated_no_show.item.registration_version == marked.item.registration_version
    assert await count(s, "registration_event") == 4


async def test_full_technical_delay_scenario(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    async with s["uow"]() as u:
        broken, _ = await attempt_service(u, NOW).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=first.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        postponed = await attempt_service(u, NOW + timedelta(minutes=3)).postpone(
            s["workspace"],
            s["exams"][0],
            broken.id,
            AttemptPostpone(expected_version=broken.version, reason="Не запускается презентация"),
            s["users"]["teacher"],
        )
    assert postponed.status == "postponed"
    assert await count(s, "assessment_window") == 0

    async with s["uow"]() as u:
        other, _ = await attempt_service(u, NOW + timedelta(minutes=4)).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=second.id, expected_version=second.version),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        await attempt_service(u, NOW + timedelta(minutes=11)).finish(
            s["workspace"],
            s["exams"][0],
            other.id,
            AttemptCommand(expected_version=other.version),
            s["users"]["teacher"],
        )
    registration = await read_registration(s, first.id)
    async with s["uow"]() as u:
        returned = await queue_service(u).next(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueueCommand(expected_version=registration.version),
            s["users"]["teacher"],
        )
    assert returned.item.state == "postponed"
    assert returned.item.position == 1
    async with s["uow"]() as u:
        restarted = await attempt_service(u, NOW + timedelta(minutes=15)).restart(
            s["workspace"],
            s["exams"][0],
            broken.id,
            AttemptRestart(expected_version=postponed.version),
            s["users"]["teacher"],
        )
    assert restarted.id == broken.id
    assert restarted.status == "speaking"
    async with s["uow"]() as u:
        await attempt_service(u, NOW + timedelta(minutes=22)).finish(
            s["workspace"],
            s["exams"][0],
            broken.id,
            AttemptCommand(expected_version=restarted.version),
            s["users"]["teacher"],
        )
    assert await count(s, "assessment_window") == 2
    assert await count(s, "exam_attempt") == 2


async def test_queue_mutations_reject_stale_versions(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    revision_before = await revision(s)
    stale = first.version + 5
    async with s["uow"]() as u:
        with pytest.raises(BusinessLogicError) as error:
            await queue_service(u).place(
                s["workspace"],
                s["exams"][0],
                first.id,
                QueuePlace(expected_version=stale, position=2),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "registration_version_conflict"
    async with s["uow"]() as u:
        with pytest.raises(BusinessLogicError) as error:
            await queue_service(u).postpone(
                s["workspace"],
                s["exams"][0],
                first.id,
                QueueReason(expected_version=stale, reason="Проектор"),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "registration_version_conflict"
    async with s["uow"]() as u:
        with pytest.raises(BusinessLogicError) as error:
            await queue_service(u).no_show(
                s["workspace"],
                s["exams"][0],
                first.id,
                QueueReason(expected_version=stale, reason="Не пришла"),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "registration_version_conflict"
    assert await revision(s) == revision_before
    assert await count(s, "registration_event") == 2
    state = await read_queue(s)
    assert [item.registration_id for item in state.items] == [first.id, second.id]
    assert [item.position for item in state.items] == [1, 2]

    # No-op by target state still wins over a stale expected_version.
    async with s["uow"]() as u:
        noop = await queue_service(u).place(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueuePlace(expected_version=stale, position=1),
            s["users"]["teacher"],
        )
    assert noop.item.position == 1
    async with s["uow"]() as u:
        postponed = await queue_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueueReason(expected_version=first.version, reason="Проектор"),
            s["users"]["teacher"],
        )
    async with s["uow"]() as u:
        repeated = await queue_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueueReason(expected_version=stale, reason="Ещё раз"),
            s["users"]["teacher"],
        )
    assert repeated.item.registration_version == postponed.item.registration_version


@pytest.mark.parametrize("action", ["started", "queue_changed", "restarted"])
async def test_commit_failure_rolls_back_queue_changes(seeded, action):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    revision_before = await revision(s)
    attempt = None
    if action == "restarted":
        async with s["uow"]() as u:
            started, _ = await attempt_service(u).start(
                s["workspace"],
                s["exams"][0],
                AttemptStart(registration_id=first.id, expected_version=first.version),
                s["users"]["teacher"],
            )
        async with s["uow"]() as u:
            await attempt_service(u).postpone(
                s["workspace"],
                s["exams"][0],
                started.id,
                AttemptPostpone(expected_version=started.version, reason="Проектор"),
                s["users"]["teacher"],
            )
        async with s["uow"]() as u:
            attempt = await attempt_service(u).get(s["workspace"], s["exams"][0], started.id, s["users"]["teacher"])
        revision_before = await revision(s)
    async with s["engine"].begin() as connection:
        await connection.execute(
            text(
                f"""CREATE FUNCTION reject_queue_commit_{action}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='{action}' THEN RAISE EXCEPTION 'test deferred queue failure'; END IF; RETURN NEW; END $$"""
            )
        )
        await connection.execute(
            text(
                f"CREATE CONSTRAINT TRIGGER reject_queue_commit_{action} AFTER INSERT ON attempt_event DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_queue_commit_{action}()"
            )
        )
        if action == "queue_changed":
            await connection.execute(text("DROP TRIGGER reject_queue_commit_queue_changed ON attempt_event"))
            await connection.execute(
                text(
                    "CREATE CONSTRAINT TRIGGER reject_queue_commit_queue_changed AFTER INSERT ON registration_event DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_queue_commit_queue_changed()"
                )
            )
    with pytest.raises(DBAPIError):
        async with s["uow"]() as u:
            if action == "started":
                await attempt_service(u).start(
                    s["workspace"],
                    s["exams"][0],
                    AttemptStart(registration_id=first.id, expected_version=first.version),
                    s["users"]["teacher"],
                )
            elif action == "restarted":
                await attempt_service(u).restart(
                    s["workspace"],
                    s["exams"][0],
                    attempt.id,
                    AttemptRestart(expected_version=attempt.version),
                    s["users"]["teacher"],
                )
            else:
                await queue_service(u).place(
                    s["workspace"],
                    s["exams"][0],
                    second.id,
                    QueuePlace(expected_version=second.version, position=1),
                    s["users"]["teacher"],
                )
    assert await revision(s) == revision_before
    if action == "started":
        assert await count(s, "exam_attempt") == 0
        fresh = await read_registration(s, first.id)
        assert fresh.queue_position == 1
        assert fresh.started_at is None
        assert await count(s, "registration_event") == 2
    elif action == "restarted":
        assert await count(s, "attempt_event") == 2
        fresh = await attempt_service_read(s, attempt.id)
        assert fresh.status == "postponed"
        assert fresh.phase_deadline == attempt.phase_deadline
    else:
        state = await read_queue(s)
        assert [item.registration_id for item in state.items] == [first.id, second.id]
        assert [item.position for item in state.items] == [1, 2]
        assert await count(s, "registration_event") == 2


async def attempt_service_read(s, attempt_id):
    async with s["uow"]() as u:
        return await attempt_service(u).get(s["workspace"], s["exams"][0], attempt_id, s["users"]["teacher"])


async def test_concurrent_no_show_then_return_retry(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    entered = asyncio.Event()
    other_pid = []

    async def contender():
        try:
            async with s["uow"]() as u:
                other_pid.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                entered.set()
                return await queue_service(u).place(
                    s["workspace"],
                    s["exams"][0],
                    first.id,
                    QueuePlace(expected_version=first.version),
                    s["users"]["teacher"],
                )
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as holder:
        await queue_service(holder).no_show(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueueReason(expected_version=first.version, reason="Не пришла"),
            s["users"]["teacher"],
        )
        task = asyncio.create_task(contender())
        await entered.wait()
        await wait_until_blocked(s, other_pid[0])
    assert await asyncio.wait_for(task, 10) == "registration_version_conflict"
    fresh = await read_registration(s, first.id)
    async with s["uow"]() as u:
        returned = await queue_service(u).place(
            s["workspace"], s["exams"][0], first.id, QueuePlace(expected_version=fresh.version), s["users"]["teacher"]
        )
    assert returned.item.state == "waiting"
    assert returned.item.position == 2
    state = await read_queue(s)
    assert [item.registration_id for item in state.items] == [second.id, first.id]


async def test_http_history_exposes_queue_and_attempt_actions(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    app = FastAPI()
    app.include_router(routers)

    async def test_uow():
        async with s["uow"]() as u:
            yield u

    app.dependency_overrides[get_uow] = test_uow
    app.dependency_overrides[get_current_user] = lambda: s["users"]["teacher"]
    queue_base = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/queue"
    registrations = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/registrations"
    attempts = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        postponed = await client.post(
            f"{queue_base}/{first.id}/postpone", json={"expected_version": first.version, "reason": "Проектор"}
        )
        assert postponed.status_code == 200
        returned = await client.post(
            f"{queue_base}/{first.id}/place",
            json={"expected_version": postponed.json()["item"]["registration_version"]},
        )
        assert returned.status_code == 200
        no_show = await client.post(
            f"{queue_base}/{second.id}/no-show", json={"expected_version": second.version, "reason": "Не пришла"}
        )
        assert no_show.status_code == 200
        history = await client.get(f"{registrations}/{first.id}/history")
        assert [item["action"] for item in history.json()["items"]] == ["created", "postponed", "returned"]
        assert history.json()["items"][1]["reason"] == "Проектор"
        assert history.json()["items"][1]["actor_id"] == s["users"]["teacher"].id
        assert history.json()["items"][2]["from_position"] is None
        absent_history = await client.get(f"{registrations}/{second.id}/history")
        assert [item["action"] for item in absent_history.json()["items"]] == ["created", "no_show"]
        started = await client.post(
            attempts,
            json={
                "registration_id": first.id,
                "expected_version": returned.json()["item"]["registration_version"],
            },
        )
        assert started.status_code == 201
        attempt_id = started.json()["id"]
        attempt_postponed = await client.post(
            f"{attempts}/{attempt_id}/postpone", json={"expected_version": 1, "reason": "Сбой"}
        )
        attempt_restarted = await client.post(
            f"{attempts}/{attempt_id}/restart", json={"expected_version": attempt_postponed.json()["version"]}
        )
        assert attempt_restarted.status_code == 200
        events = await client.get(f"{attempts}/{attempt_id}/events")
        assert [item["action"] for item in events.json()["items"]] == ["started", "postponed", "restarted"]
        assert events.json()["items"][1]["reason"] == "Сбой"
        assert events.json()["items"][1]["actor_id"] == s["users"]["teacher"].id
        for item in events.json()["items"]:
            assert datetime.fromisoformat(item["occurred_at"]).tzinfo is not None


async def test_queue_revision_bumps_once_per_action(seeded):
    s = seeded
    first = await register(s, "manager")
    second = await register(s, "manager2")
    current = await revision(s)
    async with s["uow"]() as u:
        postponed = await queue_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueueReason(expected_version=first.version, reason="Проектор"),
            s["users"]["teacher"],
        )
    assert await revision(s) == current + 1
    async with s["uow"]() as u:
        returned = await queue_service(u).place(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueuePlace(expected_version=postponed.item.registration_version),
            s["users"]["teacher"],
        )
    assert await revision(s) == current + 2
    async with s["uow"]() as u:
        attempt, _ = await attempt_service(u).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=first.id, expected_version=returned.item.registration_version),
            s["users"]["teacher"],
        )
    assert await revision(s) == current + 3
    async with s["uow"]() as u:
        attempt_postponed = await attempt_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=attempt.version, reason="Сбой"),
            s["users"]["teacher"],
        )
    assert await revision(s) == current + 4
    async with s["uow"]() as u:
        restarted = await attempt_service(u).restart(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptRestart(expected_version=attempt_postponed.version),
            s["users"]["teacher"],
        )
    assert await revision(s) == current + 5
    async with s["uow"]() as u:
        await attempt_service(u).finish(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptCommand(expected_version=restarted.version),
            s["users"]["teacher"],
        )
    assert await revision(s) == current + 6
    async with s["uow"]() as u:
        await queue_service(u).no_show(
            s["workspace"],
            s["exams"][0],
            second.id,
            QueueReason(expected_version=second.version, reason="Не пришла"),
            s["users"]["teacher"],
        )
    assert await revision(s) == current + 7


async def test_place_rejects_started_registration_without_attempt(seeded):
    s = seeded
    first = await register(s, "manager")
    async with s["uow"]() as u:
        await u.session.execute(
            text("UPDATE exam_registration SET started_at=:now WHERE id=:id"), {"now": NOW, "id": first.id}
        )
    async with s["uow"]() as u:
        with pytest.raises(BusinessLogicError) as error:
            await queue_service(u).place(
                s["workspace"],
                s["exams"][0],
                first.id,
                QueuePlace(expected_version=first.version),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "defense_already_started"
