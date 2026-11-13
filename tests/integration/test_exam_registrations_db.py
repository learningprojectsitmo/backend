from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import null, text
from sqlalchemy.exc import IntegrityError

from src.api.v1.routes import routers
from src.core.container import get_uow
from src.core.dependencies import get_current_user
from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.model.exam_registration import ExamRegistration
from src.model.project import Project, ProjectType
from src.model.user import Role, User
from src.model.workspace import WorkSpace, WorkSpaceParticipation, WorkSpaceStatus
from src.repository.exam_registration_repository import ExamRegistrationRepository
from src.repository.exam_repository import ExamRepository
from src.repository.project_repository import ProjectRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam import ExamCreate, ExamPublish, ExamSettingsReplace
from src.schema.exam_registration import RegistrationCancel, RegistrationCreate, RegistrationMove, SlotBatchCreate
from src.schema.project import ProjectUpdate
from src.schema.project_type_question import QuestionListReplace
from src.services.exam_registration_service import ExamRegistrationService
from src.services.exam_service import ExamService
from src.services.project_service import ProjectService
from src.services.project_type_question_service import ProjectTypeQuestionService
from src.services.question_template_service import QuestionTemplateService

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 20, 10, tzinfo=UTC)
START = datetime(2026, 11, 30, 10, tzinfo=UTC)


def reg_service(uow, now=NOW):
    questions = ProjectTypeQuestionRepository(uow)
    return ExamRegistrationService(
        ExamRegistrationRepository(uow), ExamService(ExamRepository(uow), questions), questions, clock=lambda: now
    )


@pytest_asyncio.fixture(loop_scope="function")
async def seeded(registration_db, monkeypatch):
    class FrozenClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW.replace(tzinfo=None)

    monkeypatch.setattr("src.services.exam_service.datetime", FrozenClock)
    monkeypatch.setattr("src.services.exam_registration_service.datetime", FrozenClock)
    engine, make_uow = registration_db
    async with make_uow() as u:
        roles = {name: Role(name=name) for name in ["admin", "teacher", "manager", "member"]}
        u.session.add_all(roles.values())
        role_by_user = {
            "admin": "admin",
            "teacher": "teacher",
            "manager": "manager",
            "manager2": "manager",
            "member": "member",
            "local_teacher": "member",
            "local_manager": "member",
            "demoted": "manager",
            "null_manager": "manager",
            "outsider": "teacher",
        }
        users = {
            name: User(
                first_name=name,
                middle_name="Test",
                email=f"{name}@example.com",
                password_hashed="test",
                role=roles[role],
            )
            for name, role in role_by_user.items()
        }
        u.session.add_all(users.values())
        status = WorkSpaceStatus(name="test")
        u.session.add(status)
        await u.session.flush()
        spaces = [
            WorkSpace(name="Course", author_id=users["teacher"].id, status_id=status.id),
            WorkSpace(name="Other", author_id=users["outsider"].id, status_id=status.id),
        ]
        u.session.add_all(spaces)
        await u.session.flush()
        for name, local in [
            ("manager", "manager"),
            ("manager2", "manager"),
            ("member", "member"),
            ("local_teacher", "teacher"),
            ("local_manager", "manager"),
            ("demoted", "member"),
            ("null_manager", None),
        ]:
            u.session.add(
                WorkSpaceParticipation(
                    workspace_id=spaces[0].id,
                    participant_id=users[name].id,
                    role_id=roles[local].id if local else null(),
                )
            )
        types = [
            ProjectType(name="Working", workspace_id=spaces[0].id),
            ProjectType(name="Not selected", workspace_id=spaces[0].id),
            ProjectType(name="Foreign", workspace_id=spaces[1].id),
        ]
        u.session.add_all(types)
        await u.session.flush()
        projects = {
            name: Project(
                name=f"Project {name}", author_id=users[name].id, workspace_id=spaces[0].id, project_type_id=types[0].id
            )
            for name in ["manager", "manager2", "member", "local_manager", "demoted", "null_manager"]
        }
        u.session.add_all(projects.values())
        q = ProjectTypeQuestionRepository(u)
        await ProjectTypeQuestionService(q, QuestionTemplateService()).replace_questions(
            spaces[0].id,
            types[0].id,
            QuestionListReplace(
                questions=[
                    {"text": "Criterion", "levels": [{"score": x, "description": f"Level {x}"} for x in range(1, 6)]}
                ]
            ),
            users["teacher"],
        )
        es = ExamService(ExamRepository(u), q)
        exams = []
        for day in [0, 1]:
            exam = await es.create(
                spaces[0].id,
                ExamCreate(title=f"Exam {day}", starts_at=START + timedelta(days=day), project_type_ids=[types[0].id]),
                users["teacher"],
            )
            await es.publish(spaces[0].id, exam.id, ExamPublish(expected_version=1), users["teacher"])
            exams.append(exam)
        draft = await es.create(
            spaces[0].id, ExamCreate(title="Draft", starts_at=START, project_type_ids=[types[0].id]), users["teacher"]
        )
        await u.session.flush()
        ids = {name: p.id for name, p in projects.items()}
    return {
        "engine": engine,
        "uow": make_uow,
        "users": users,
        "workspace": spaces[0].id,
        "foreign_workspace": spaces[1].id,
        "types": [t.id for t in types],
        "projects": ids,
        "exams": [e.id for e in exams],
        "draft": draft.id,
    }


def intervals():
    return SlotBatchCreate(
        slots=[
            {"starts_at": START, "ends_at": START + timedelta(minutes=15)},
            {"starts_at": START + timedelta(minutes=15), "ends_at": START + timedelta(minutes=30)},
        ]
    )


async def count(s, table):
    async with s["engine"].connect() as conn:
        return (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()


async def test_registration_migration_exists_and_can_reverse_preserving_exam(
    seeded, registration_database_url, run_migrations
):
    s = seeded
    async with s["engine"].connect() as conn:
        tables = set((await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).scalars())
    assert {"exam_slot", "exam_registration", "registration_event"} <= tables
    run_migrations(registration_database_url, "check")
    await s["engine"].dispose()
    run_migrations(registration_database_url, "downgrade", "d101a10b20c4")
    run_migrations(registration_database_url, "upgrade", "head")
    assert await count(s, "exam") == 3
    assert await count(s, "project_type_question") == 1


async def test_slots_adjacent_visible_without_project_identity(seeded):
    s = seeded
    async with s["uow"]() as u:
        slots = await reg_service(u).add_slots(s["workspace"], s["exams"][0], intervals(), s["users"]["teacher"])
        assert len(slots) == 2
    async with s["uow"]() as u:
        page = await reg_service(u).list_slots(s["workspace"], s["exams"][0], s["users"]["member"], limit=1, offset=0)
        assert len(page.items) == 1 and page.has_more
        assert page.items[0].is_available
        assert "project_id" not in page.items[0].model_dump()


@pytest.mark.parametrize("actor", ["manager", "member", "outsider"])
async def test_only_scoped_organizer_can_add_slots(seeded, actor):
    s = seeded
    with pytest.raises((PermissionError, NotFoundError)):
        async with s["uow"]() as u:
            await reg_service(u).add_slots(s["workspace"], s["exams"][0], intervals(), s["users"][actor])
    assert await count(s, "exam_slot") == 0


async def test_slot_batch_overlap_rolls_back_whole_batch(seeded):
    s = seeded
    async with s["uow"]() as u:
        await reg_service(u).add_slots(s["workspace"], s["exams"][0], intervals(), s["users"]["teacher"])
    body = SlotBatchCreate(
        slots=[
            {"starts_at": START + timedelta(hours=1), "ends_at": START + timedelta(hours=2)},
            {"starts_at": START + timedelta(minutes=10), "ends_at": START + timedelta(minutes=20)},
        ]
    )
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await reg_service(u).add_slots(s["workspace"], s["exams"][0], body, s["users"]["teacher"])
    assert error.value.detail["code"] == "slot_overlap"
    assert await count(s, "exam_slot") == 2


async def test_draft_slots_hidden_from_member_and_post_start_creation_closed(seeded):
    s = seeded
    with pytest.raises(NotFoundError):
        async with s["uow"]() as u:
            await reg_service(u).list_slots(s["workspace"], s["draft"], s["users"]["member"], limit=50, offset=0)
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await reg_service(u, START).add_slots(s["workspace"], s["exams"][0], intervals(), s["users"]["teacher"])
    assert error.value.detail["code"] == "slot_schedule_closed"


async def test_database_enforces_global_active_project_uniqueness(seeded):
    s = seeded

    def row(exam_id, **extra):
        values = {
            "workspace_id": s["workspace"],
            "exam_id": exam_id,
            "project_id": s["projects"]["manager"],
            "project_type_id_at_registration": s["types"][0],
            "status": "active",
            "version": 1,
            "created_source": "manager",
            "created_by": s["users"]["manager"].id,
            "updated_by": s["users"]["manager"].id,
            "created_at": NOW,
            "updated_at": NOW,
        }
        values.update(extra)
        return ExamRegistration(**values)

    async with s["uow"]() as u:
        u.session.add(row(s["exams"][0]))
    with pytest.raises(IntegrityError):
        async with s["uow"]() as u:
            u.session.add(row(s["exams"][1]))
    assert await count(s, "exam_registration") == 1
    async with s["uow"]() as u:
        await u.session.execute(text("UPDATE exam_registration SET status='cancelled'"))
        u.session.add(row(s["exams"][1]))
    assert await count(s, "exam_registration") == 2
    # Even cancelled history prevents silently switching a slotless exam to slots.
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await reg_service(u).add_slots(s["workspace"], s["exams"][0], intervals(), s["users"]["teacher"])
    assert error.value.detail["code"] == "slot_schedule_locked"


@pytest.mark.parametrize(
    "change", ["foreign_type", "bad_version", "bad_source", "bad_status", "cancelled_started", "foreign_exam"]
)
async def test_database_rejects_invalid_registration_state_and_scope(seeded, change):
    s = seeded
    values = {
        "workspace_id": s["workspace"],
        "exam_id": s["exams"][0],
        "project_id": s["projects"]["manager"],
        "project_type_id_at_registration": s["types"][0],
        "status": "active",
        "version": 1,
        "created_source": "manager",
        "created_by": s["users"]["manager"].id,
        "updated_by": s["users"]["manager"].id,
        "created_at": NOW,
        "updated_at": NOW,
    }
    updates = {
        "foreign_type": {"project_type_id_at_registration": s["types"][2]},
        "bad_version": {"version": 0},
        "bad_source": {"created_source": "client"},
        "bad_status": {"status": "completed"},
        "cancelled_started": {"status": "cancelled", "started_at": NOW},
        "foreign_exam": {"workspace_id": s["foreign_workspace"]},
    }
    values.update(updates[change])
    with pytest.raises(IntegrityError):
        async with s["uow"]() as u:
            u.session.add(ExamRegistration(**values))
    assert await count(s, "exam_registration") == 0


async def self_register(s, *, actor="manager", exam=0, slot_id=None, now=NOW):
    async with s["uow"]() as u:
        return await reg_service(u, now).create_self(
            s["workspace"],
            s["exams"][exam],
            RegistrationCreate(project_id=s["projects"][actor], slot_id=slot_id),
            s["users"][actor],
        )


@pytest.mark.parametrize("actor", ["manager", "local_manager", "null_manager"])
async def test_own_manager_can_register_without_slots_and_read_origin(seeded, actor):
    s = seeded
    saved = await self_register(s, actor=actor)
    assert (saved.status, saved.version, saved.created_source) == ("active", 1, "manager")
    assert saved.created_by == s["users"][actor].id
    assert saved.slot_id is None
    async with s["uow"]() as u:
        own = await reg_service(u).list_self(
            s["workspace"], s["exams"][0], s["users"][actor], project_id=None, status=None, limit=50, offset=0
        )
        assert [r.id for r in own.items] == [saved.id]
        history = await reg_service(u).history(
            s["workspace"], s["exams"][0], saved.id, s["users"][actor], limit=50, offset=0
        )
        assert [e.action for e in history.items] == ["created"]


@pytest.mark.parametrize("actor", ["member", "demoted"])
async def test_member_author_cannot_register_even_with_global_manager_role(seeded, actor):
    with pytest.raises(PermissionError):
        await self_register(seeded, actor=actor)
    assert await count(seeded, "exam_registration") == 0


async def test_manager_cannot_register_another_project_or_see_its_history(seeded):
    s = seeded
    saved = await self_register(s)
    with pytest.raises((PermissionError, NotFoundError)):
        async with s["uow"]() as u:
            await reg_service(u).create_self(
                s["workspace"],
                s["exams"][1],
                RegistrationCreate(project_id=s["projects"]["manager"]),
                s["users"]["manager2"],
            )
    with pytest.raises(NotFoundError):
        async with s["uow"]() as u:
            await reg_service(u).history(
                s["workspace"], s["exams"][0], saved.id, s["users"]["manager2"], limit=50, offset=0
            )


async def test_no_second_active_in_any_exam_and_cancel_allows_new_id(seeded):
    s = seeded
    saved = await self_register(s)
    with pytest.raises(BusinessLogicError) as error:
        await self_register(s, exam=1)
    assert error.value.detail["code"] == "project_already_registered"
    async with s["uow"]() as u:
        cancelled = await reg_service(u).cancel_self(
            s["workspace"],
            s["exams"][0],
            saved.id,
            RegistrationCancel(expected_version=1, reason="Другая дата"),
            s["users"]["manager"],
        )
    assert (cancelled.status, cancelled.version) == ("cancelled", 2)
    new = await self_register(s, exam=1)
    assert new.id != saved.id
    assert await count(s, "registration_event") == 3


async def test_same_exam_slot_transfer_noop_and_stale_version(seeded):
    s = seeded
    async with s["uow"]() as u:
        slots = await reg_service(u).add_slots(s["workspace"], s["exams"][0], intervals(), s["users"]["teacher"])
    with pytest.raises(BusinessLogicError) as error:
        await self_register(s)
    assert error.value.detail["code"] == "slot_required"
    saved = await self_register(s, slot_id=slots[0].id)
    with pytest.raises(BusinessLogicError) as error:
        await self_register(s, actor="manager2", slot_id=slots[0].id)
    assert error.value.detail["code"] == "slot_unavailable"
    async with s["uow"]() as u:
        moved = await reg_service(u).move_self(
            s["workspace"],
            s["exams"][0],
            saved.id,
            RegistrationMove(
                expected_version=1, target_exam_id=s["exams"][0], target_slot_id=slots[1].id, reason="Позже"
            ),
            s["users"]["manager"],
        )
        assert moved.target.id == moved.source.id == saved.id
        assert (moved.target.slot_id, moved.target.version) == (slots[1].id, 2)
    async with s["uow"]() as u:
        noop = await reg_service(u).move_self(
            s["workspace"],
            s["exams"][0],
            saved.id,
            RegistrationMove(
                expected_version=2, target_exam_id=s["exams"][0], target_slot_id=slots[1].id, reason="Повтор"
            ),
            s["users"]["manager"],
        )
        assert noop.target.updated_at == moved.target.updated_at
        assert noop.target.version == 2
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await reg_service(u).cancel_self(
                s["workspace"],
                s["exams"][0],
                saved.id,
                RegistrationCancel(expected_version=1, reason="Устарело"),
                s["users"]["manager"],
            )
    assert error.value.detail["code"] == "registration_version_conflict"
    assert await count(s, "registration_event") == 2


async def test_cross_exam_transfer_preserves_identity_history_and_returns_two_rows(seeded):
    s = seeded
    saved = await self_register(s)
    async with s["uow"]() as u:
        moved = await reg_service(u).move_self(
            s["workspace"],
            s["exams"][0],
            saved.id,
            RegistrationMove(expected_version=1, target_exam_id=s["exams"][1], reason="Другая дата"),
            s["users"]["manager"],
        )
        assert (moved.source.status, moved.source.version) == ("moved", 2)
        assert moved.target.id != saved.id and moved.target.status == "active"
    async with s["uow"]() as u:
        source = await reg_service(u).history(
            s["workspace"], s["exams"][0], saved.id, s["users"]["manager"], limit=50, offset=0
        )
        target = await reg_service(u).history(
            s["workspace"], s["exams"][1], moved.target.id, s["users"]["manager"], limit=50, offset=0
        )
        assert [e.action for e in source.items] == ["created", "moved_out"]
        assert [e.action for e in target.items] == ["moved_in"]
        assert source.items[-1].transfer_id == target.items[0].transfer_id
        assert source.items[-1].related_registration_id == moved.target.id
        assert target.items[0].related_registration_id == saved.id
    # Transfer back is another linked registration, never history deletion.
    async with s["uow"]() as u:
        back = await reg_service(u).move_self(
            s["workspace"],
            s["exams"][1],
            moved.target.id,
            RegistrationMove(expected_version=1, target_exam_id=s["exams"][0], reason="Возврат"),
            s["users"]["manager"],
        )
    assert back.target.id not in {saved.id, moved.target.id}
    assert await count(s, "exam_registration") == 3
    assert await count(s, "registration_event") == 5


async def test_closed_period_draft_and_unselected_type_rejected(seeded):
    s = seeded
    with pytest.raises(BusinessLogicError) as error:
        await self_register(s, now=START)
    assert error.value.detail["code"] == "registration_closed"
    with pytest.raises(NotFoundError):
        async with s["uow"]() as u:
            await reg_service(u).create_self(
                s["workspace"],
                s["draft"],
                RegistrationCreate(project_id=s["projects"]["manager"]),
                s["users"]["manager"],
            )
    async with s["uow"]() as u:
        await u.session.execute(
            text("UPDATE project SET project_type_id=:type WHERE id=:project"),
            {"type": s["types"][1], "project": s["projects"]["manager"]},
        )
    with pytest.raises(BusinessLogicError) as error:
        await self_register(s)
    assert error.value.detail["code"] == "project_type_not_allowed"
    assert await count(s, "exam_registration") == 0


async def test_started_marker_blocks_cancel_before_period_error(seeded):
    s = seeded
    saved = await self_register(s)
    async with s["uow"]() as u:
        await u.session.execute(
            text("UPDATE exam_registration SET started_at=:now WHERE id=:id"), {"now": START, "id": saved.id}
        )
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await reg_service(u, START).cancel_self(
                s["workspace"],
                s["exams"][0],
                saved.id,
                RegistrationCancel(expected_version=1, reason="Поздно"),
                s["users"]["manager"],
            )
    assert error.value.detail["code"] == "defense_already_started"


@pytest.mark.parametrize("field", ["workspace_id", "project_type_id"])
async def test_project_scope_change_blocked_while_registered(seeded, field):
    s = seeded
    await self_register(s)
    value = s["foreign_workspace"] if field == "workspace_id" else s["types"][1]
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await ProjectService(ProjectRepository(u)).update_project(
                s["projects"]["manager"], ProjectUpdate(**{field: value}), s["users"]["manager"].id
            )
    assert error.value.detail["code"] == "project_registration_locked"


async def test_project_history_cannot_be_deleted_and_type_can_change_after_cancellation(seeded):
    s = seeded
    saved = await self_register(s)
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await ProjectService(ProjectRepository(u)).delete_project(s["projects"]["manager"], is_admin=True)
    assert error.value.detail["code"] == "project_has_registrations"
    async with s["uow"]() as u:
        await reg_service(u).cancel_self(
            s["workspace"],
            s["exams"][0],
            saved.id,
            RegistrationCancel(expected_version=1, reason="Другой тип"),
            s["users"]["manager"],
        )
    async with s["uow"]() as u:
        p = await ProjectService(ProjectRepository(u)).update_project(
            s["projects"]["manager"], ProjectUpdate(project_type_id=s["types"][1]), s["users"]["manager"].id
        )
        assert p.project_type_id == s["types"][1]
    assert await count(s, "registration_event") == 2


async def wait_until_blocked(s, pid):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        async with s["engine"].connect() as conn:
            blocked = await conn.scalar(text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": pid})
        if blocked:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Second connection never blocked on the parent/project row")


@pytest.mark.parametrize("different_exam", [False, True])
async def test_competing_manager_creates_leave_one_active_and_one_event(seeded, different_exam):
    s = seeded
    entered = asyncio.Event()
    other_pid = []

    async def contender():
        try:
            async with s["uow"]() as u:
                other_pid.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                entered.set()
                return await reg_service(u).create_self(
                    s["workspace"],
                    s["exams"][int(different_exam)],
                    RegistrationCreate(project_id=s["projects"]["manager"]),
                    s["users"]["manager"],
                )
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as first:
        winner = await reg_service(first).create_self(
            s["workspace"],
            s["exams"][0],
            RegistrationCreate(project_id=s["projects"]["manager"]),
            s["users"]["manager"],
        )
        task = asyncio.create_task(contender())
        await asyncio.wait_for(entered.wait(), 5)
        try:
            await wait_until_blocked(s, other_pid[0])
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == "project_already_registered"
    assert winner.status == "active"
    assert await count(s, "exam_registration") == 1
    assert await count(s, "registration_event") == 1


async def test_waiting_request_rechecks_cutoff(seeded):
    s = seeded
    now = [NOW]
    ready = asyncio.Event()
    pids = []

    async def delayed():
        try:
            async with s["uow"]() as u:
                pids.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                service = reg_service(u)
                service._clock = lambda: now[0]
                ready.set()
                await service.create_self(
                    s["workspace"],
                    s["exams"][0],
                    RegistrationCreate(project_id=s["projects"]["manager"]),
                    s["users"]["manager"],
                )
        except BusinessLogicError as error:
            return error.detail["code"]
        return "unexpected success"

    async with s["uow"]() as first:
        await ExamRepository(first).get_scoped(s["workspace"], s["exams"][0], lock=True)
        task = asyncio.create_task(delayed())
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await wait_until_blocked(s, pids[0])
            now[0] = START
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == "registration_closed"
    assert await count(s, "exam_registration") == 0


@pytest.mark.parametrize("slots_win", [False, True])
async def test_first_slots_and_first_slotless_registration_serialize(seeded, slots_win):
    s = seeded
    ready = asyncio.Event()
    pids = []

    async def register(u):
        return await reg_service(u).create_self(
            s["workspace"],
            s["exams"][0],
            RegistrationCreate(project_id=s["projects"]["manager"]),
            s["users"]["manager"],
        )

    async def add(u):
        return await reg_service(u).add_slots(s["workspace"], s["exams"][0], intervals(), s["users"]["teacher"])

    async def loser():
        try:
            async with s["uow"]() as u:
                pids.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                return await (register(u) if slots_win else add(u))
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as first:
        await (add(first) if slots_win else register(first))
        task = asyncio.create_task(loser())
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await wait_until_blocked(s, pids[0])
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == ("slot_required" if slots_win else "slot_schedule_locked")
    assert await count(s, "exam_slot") == (2 if slots_win else 0)
    assert await count(s, "exam_registration") == (0 if slots_win else 1)


async def test_opposite_transfers_use_sorted_exam_locks(seeded):
    s = seeded
    a = await self_register(s)
    b = await self_register(s, actor="manager2", exam=1)

    async def move(actor, row, source_index, target_index):
        async with s["uow"]() as u:
            await u.session.execute(text("SET LOCAL lock_timeout='5s'"))
            return await reg_service(u).move_self(
                s["workspace"],
                s["exams"][source_index],
                row.id,
                RegistrationMove(expected_version=1, target_exam_id=s["exams"][target_index], reason="Обмен датами"),
                s["users"][actor],
            )

    results = await asyncio.wait_for(asyncio.gather(move("manager", a, 0, 1), move("manager2", b, 1, 0)), 12)
    assert [x.target.exam_id for x in results] == [s["exams"][1], s["exams"][0]]
    assert await count(s, "exam_registration") == 4
    assert await count(s, "registration_event") == 6


@pytest.mark.parametrize("registration_wins", [False, True])
async def test_project_type_change_and_registration_share_project_lock(seeded, registration_wins):
    s = seeded
    ready = asyncio.Event()
    pids = []

    async def register(u):
        return await reg_service(u).create_self(
            s["workspace"],
            s["exams"][0],
            RegistrationCreate(project_id=s["projects"]["manager"]),
            s["users"]["manager"],
        )

    async def change(u):
        return await ProjectService(ProjectRepository(u)).update_project(
            s["projects"]["manager"], ProjectUpdate(project_type_id=s["types"][1]), s["users"]["manager"].id
        )

    async def loser():
        try:
            async with s["uow"]() as u:
                pids.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                return await (change(u) if registration_wins else register(u))
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as first:
        await (register(first) if registration_wins else change(first))
        task = asyncio.create_task(loser())
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await wait_until_blocked(s, pids[0])
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == (
        "project_registration_locked" if registration_wins else "project_type_not_allowed"
    )
    assert await count(s, "exam_registration") == (1 if registration_wins else 0)


async def test_http_self_flow_commits_and_preserves_history(seeded):
    s = seeded
    app = FastAPI()
    app.include_router(routers)

    async def test_uow():
        async with s["uow"]() as u:
            yield u

    app.dependency_overrides[get_uow] = test_uow
    app.dependency_overrides[get_current_user] = lambda: s["users"]["manager"]
    base = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/registrations"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"{base}/self", json={"project_id": s["projects"]["manager"]})
        assert response.status_code == 201
        body = response.json()
        assert body["created_source"] == "manager" and body["version"] == 1
        assert body["created_at"] == "2026-11-20T10:00:00Z"
        own = await client.get(f"{base}/self")
        assert [r["id"] for r in own.json()["items"]] == [body["id"]]
        cancelled = await client.post(
            f"{base}/{body['id']}/self-cancel", json={"expected_version": 1, "reason": "Другая дата"}
        )
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
        history = await client.get(f"{base}/{body['id']}/history")
        assert [e["action"] for e in history.json()["items"]] == ["created", "cancelled"]
    assert await count(s, "exam_registration") == 1
    assert await count(s, "registration_event") == 2


@pytest.mark.parametrize("action", ["created", "moved_in"])
async def test_http_deferred_event_failure_rolls_back_entire_operation(seeded, action):
    s = seeded
    saved = await self_register(s) if action == "moved_in" else None
    async with s["engine"].begin() as connection:
        await connection.execute(
            text(
                """CREATE FUNCTION reject_registration_event() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action=TG_ARGV[0] THEN RAISE EXCEPTION 'test deferred event failure'; END IF; RETURN NEW; END $$"""
            )
        )
        await connection.execute(
            text(
                f"CREATE CONSTRAINT TRIGGER reject_registration_event AFTER INSERT ON registration_event DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_registration_event('{action}')"
            )
        )
    app = FastAPI()
    app.include_router(routers)

    async def test_uow():
        async with s["uow"]() as u:
            yield u

    app.dependency_overrides[get_uow] = test_uow
    app.dependency_overrides[get_current_user] = lambda: s["users"]["manager"]
    base = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/registrations"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        if saved:
            response = await client.post(
                f"{base}/{saved.id}/self-move",
                json={"expected_version": 1, "target_exam_id": s["exams"][1], "reason": "Rollback"},
            )
        else:
            response = await client.post(f"{base}/self", json={"project_id": s["projects"]["manager"]})
    assert response.status_code == 500
    assert await count(s, "exam_registration") == (1 if saved else 0)
    assert await count(s, "registration_event") == (1 if saved else 0)
    if saved:
        async with s["engine"].connect() as conn:
            row = (
                await conn.execute(text("SELECT status,version FROM exam_registration WHERE id=:id"), {"id": saved.id})
            ).one()
            assert tuple(row) == ("active", 1)


async def test_two_projects_compete_for_one_slot(seeded):
    s = seeded
    async with s["uow"]() as u:
        slots = await reg_service(u).add_slots(s["workspace"], s["exams"][0], intervals(), s["users"]["teacher"])
    ready = asyncio.Event()
    pids = []

    async def other():
        try:
            async with s["uow"]() as u:
                pids.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                return await reg_service(u).create_self(
                    s["workspace"],
                    s["exams"][0],
                    RegistrationCreate(project_id=s["projects"]["manager2"], slot_id=slots[0].id),
                    s["users"]["manager2"],
                )
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as first:
        await reg_service(first).create_self(
            s["workspace"],
            s["exams"][0],
            RegistrationCreate(project_id=s["projects"]["manager"], slot_id=slots[0].id),
            s["users"]["manager"],
        )
        task = asyncio.create_task(other())
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await wait_until_blocked(s, pids[0])
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == "slot_unavailable"
    assert await count(s, "exam_registration") == 1


async def test_slot_of_another_exam_hidden_and_closed_target_move_keeps_original(seeded):
    s = seeded
    async with s["uow"]() as u:
        slots = await reg_service(u).add_slots(s["workspace"], s["exams"][0], intervals(), s["users"]["teacher"])
    with pytest.raises(NotFoundError):
        await self_register(s, exam=1, slot_id=slots[0].id)
    saved = await self_register(s, slot_id=slots[0].id)
    async with s["uow"]() as u:
        await u.session.execute(
            text("UPDATE exam_settings_revision SET registration_opens_at=:opens WHERE exam_id=:id"),
            {"opens": NOW + timedelta(hours=1), "id": s["exams"][1]},
        )
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await reg_service(u).move_self(
                s["workspace"],
                s["exams"][0],
                saved.id,
                RegistrationMove(expected_version=1, target_exam_id=s["exams"][1], reason="Пока рано"),
                s["users"]["manager"],
            )
    assert error.value.detail["code"] == "registration_closed"
    assert await count(s, "exam_registration") == 1
    assert await count(s, "registration_event") == 1


async def test_manager_retains_read_access_after_cutoff_and_role_revocation(seeded):
    s = seeded
    saved = await self_register(s)
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await reg_service(u, START).cancel_self(
                s["workspace"],
                s["exams"][0],
                saved.id,
                RegistrationCancel(expected_version=1, reason="После срока"),
                s["users"]["manager"],
            )
    assert error.value.detail["code"] == "registration_closed"
    async with s["uow"]() as u:
        await u.session.execute(
            text(
                "UPDATE workspace_participation SET role_id=(SELECT id FROM role WHERE name='member') WHERE workspace_id=:ws AND participant_id=:user"
            ),
            {"ws": s["workspace"], "user": s["users"]["manager"].id},
        )
    async with s["uow"]() as u:
        own = await reg_service(u, START).list_self(
            s["workspace"], s["exams"][0], s["users"]["manager"], project_id=None, status=None, limit=50, offset=0
        )
        assert [r.id for r in own.items] == [saved.id]
    with pytest.raises(PermissionError):
        async with s["uow"]() as u:
            await reg_service(u).cancel_self(
                s["workspace"],
                s["exams"][0],
                saved.id,
                RegistrationCancel(expected_version=1, reason="Роль отозвана"),
                s["users"]["manager"],
            )


@pytest.mark.parametrize("moving", [False, True])
async def test_slot_row_wait_rechecks_cutoff_and_preserves_original(seeded, moving):
    s = seeded
    async with s["uow"]() as u:
        slots = await reg_service(u).add_slots(s["workspace"], s["exams"][0], intervals(), s["users"]["teacher"])
    saved = await self_register(s, slot_id=slots[0].id) if moving else None
    ready = asyncio.Event()
    pids = []
    now = [NOW]

    async def waiting():
        try:
            async with s["uow"]() as u:
                pids.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                service = reg_service(u)
                service._clock = lambda: now[0]
                ready.set()
                if moving:
                    return await service.move_self(
                        s["workspace"],
                        s["exams"][0],
                        saved.id,
                        RegistrationMove(
                            expected_version=1,
                            target_exam_id=s["exams"][0],
                            target_slot_id=slots[1].id,
                            reason="Ожидание слота",
                        ),
                        s["users"]["manager"],
                    )
                return await service.create_self(
                    s["workspace"],
                    s["exams"][0],
                    RegistrationCreate(project_id=s["projects"]["manager"], slot_id=slots[1].id),
                    s["users"]["manager"],
                )
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as first:
        await first.session.execute(text("SELECT id FROM exam_slot WHERE id=:id FOR UPDATE"), {"id": slots[1].id})
        task = asyncio.create_task(waiting())
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await wait_until_blocked(s, pids[0])
            now[0] = START
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == "registration_closed"
    assert await count(s, "registration_event") == (1 if moving else 0)
    if moving:
        async with s["engine"].connect() as conn:
            row = (
                await conn.execute(text("SELECT slot_id,version FROM exam_registration WHERE id=:id"), {"id": saved.id})
            ).one()
            assert tuple(row) == (slots[0].id, 1)


@pytest.mark.parametrize("slots_win", [False, True])
async def test_draft_schedule_change_and_slot_creation_keep_slot_after_exam(seeded, slots_win):
    s = seeded
    async with s["uow"]() as u:
        exam = await ExamService(ExamRepository(u), ProjectTypeQuestionRepository(u)).get(
            s["workspace"], s["draft"], s["users"]["teacher"]
        )
    config = exam.configuration.model_dump() | {"starts_at": START + timedelta(hours=1)}
    replace = ExamSettingsReplace(expected_version=1, reason="Начало позже", configuration=config)
    ready = asyncio.Event()
    pids = []

    async def add(u):
        return await reg_service(u).add_slots(s["workspace"], s["draft"], intervals(), s["users"]["teacher"])

    async def edit(u):
        return await ExamService(ExamRepository(u), ProjectTypeQuestionRepository(u)).replace_settings(
            s["workspace"], s["draft"], replace, s["users"]["teacher"]
        )

    async def other():
        try:
            async with s["uow"]() as u:
                pids.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                return await (edit(u) if slots_win else add(u))
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as first:
        await (add(first) if slots_win else edit(first))
        task = asyncio.create_task(other())
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await wait_until_blocked(s, pids[0])
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == ("slot_schedule_conflict" if slots_win else "slot_before_exam")


async def test_slot_writer_role_revoked_while_waiting_is_denied(seeded):
    s = seeded
    ready = asyncio.Event()
    pids = []

    async def other():
        try:
            async with s["uow"]() as u:
                pids.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                return await reg_service(u).add_slots(
                    s["workspace"], s["exams"][0], intervals(), s["users"]["local_teacher"]
                )
        except PermissionError:
            return "forbidden"

    async with s["uow"]() as first:
        await ExamRepository(first).get_scoped(s["workspace"], s["exams"][0], lock=True)
        task = asyncio.create_task(other())
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await wait_until_blocked(s, pids[0])
            await first.session.execute(
                text(
                    "UPDATE workspace_participation SET role_id=(SELECT id FROM role WHERE name='member') WHERE workspace_id=:ws AND participant_id=:user"
                ),
                {"ws": s["workspace"], "user": s["users"]["local_teacher"].id},
            )
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == "forbidden"
    assert await count(s, "exam_slot") == 0


@pytest.mark.parametrize("actor", ["teacher", "admin", "null_manager"])
async def test_global_role_revoked_while_waiting_is_denied(seeded, actor):
    s = seeded
    ready = asyncio.Event()
    pids = []

    async def waiting():
        try:
            async with s["uow"]() as u:
                pids.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                if actor == "null_manager":
                    return await reg_service(u).create_self(
                        s["workspace"],
                        s["exams"][0],
                        RegistrationCreate(project_id=s["projects"][actor]),
                        s["users"][actor],
                    )
                return await reg_service(u).add_slots(s["workspace"], s["exams"][0], intervals(), s["users"][actor])
        except (PermissionError, NotFoundError):
            return "forbidden"

    async with s["uow"]() as first:
        await ExamRepository(first).get_scoped(s["workspace"], s["exams"][0], lock=True)
        task = asyncio.create_task(waiting())
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await wait_until_blocked(s, pids[0])
            await first.session.execute(
                text("UPDATE public.user SET role_id=(SELECT id FROM role WHERE name='member') WHERE id=:id"),
                {"id": s["users"][actor].id},
            )
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == "forbidden"
    assert await count(s, "exam_slot") == 0
    assert await count(s, "exam_registration") == 0
    assert await count(s, "registration_event") == 0


async def profile_update(s, actor, body, *, ready=None, pids=None):
    app = FastAPI()
    app.include_router(routers)

    async def test_uow():
        async with s["uow"]() as u:
            if ready is not None:
                pids.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
            yield u

    app.dependency_overrides[get_uow] = test_uow
    app.dependency_overrides[get_current_user] = lambda: s["users"][actor]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.put(f"/v1/users/{s['users'][actor].id}", json=body)


async def saved_role(s, actor):
    async with s["engine"].connect() as conn:
        return await conn.scalar(text("SELECT role_id FROM public.user WHERE id=:id"), {"id": s["users"][actor].id})


@pytest.mark.parametrize("actor", ["member", "manager", "teacher"])
async def test_profile_cannot_promote_own_global_role(seeded, actor):
    s = seeded
    original = s["users"][actor].role_id
    response = await profile_update(s, actor, {"role_id": s["users"]["admin"].role_id})
    assert response.status_code == 403
    assert await saved_role(s, actor) == original


async def test_profile_allows_unchanged_role_echo_and_personal_fields(seeded):
    s = seeded
    response = await profile_update(s, "manager", {"role_id": s["users"]["manager"].role_id, "first_name": "Фёдор"})
    assert response.status_code == 200
    assert response.json()["first_name"] == "Фёдор"
    assert await saved_role(s, "manager") == s["users"]["manager"].role_id


async def test_profile_current_admin_can_change_role(seeded):
    s = seeded
    teacher_role = s["users"]["teacher"].role_id
    response = await profile_update(s, "admin", {"role_id": teacher_role})
    assert response.status_code == 200
    assert await saved_role(s, "admin") == teacher_role


async def test_profile_cached_admin_cannot_restore_revoked_role(seeded):
    s = seeded
    member_role = s["users"]["member"].role_id
    async with s["uow"]() as u:
        await u.session.execute(
            text("UPDATE public.user SET role_id=:role WHERE id=:id"),
            {"role": member_role, "id": s["users"]["admin"].id},
        )
    response = await profile_update(s, "admin", {"role_id": s["users"]["admin"].role_id})
    assert response.status_code == 403
    assert await saved_role(s, "admin") == member_role


async def test_profile_admin_revoked_while_waiting_cannot_restore_role(seeded):
    s = seeded
    ready = asyncio.Event()
    pids = []
    admin = s["users"]["admin"]
    async with s["uow"]() as first:
        await first.session.execute(text("SELECT id FROM public.user WHERE id=:id FOR UPDATE"), {"id": admin.id})
        task = asyncio.create_task(profile_update(s, "admin", {"role_id": admin.role_id}, ready=ready, pids=pids))
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await wait_until_blocked(s, pids[0])
            await first.session.execute(
                text("UPDATE public.user SET role_id=:role WHERE id=:id"),
                {"role": s["users"]["member"].role_id, "id": admin.id},
            )
        except BaseException:
            task.cancel()
            raise
    response = await asyncio.wait_for(task, 10)
    assert response.status_code == 403
    assert await saved_role(s, "admin") == s["users"]["member"].role_id
