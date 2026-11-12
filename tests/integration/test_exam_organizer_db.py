from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import test_exam_registrations_db as registration_cases
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_exam_registrations_db import NOW, START, count, intervals, reg_service, self_register, wait_until_blocked

from src.api.v1.routes import routers
from src.core.container import get_uow
from src.core.dependencies import get_current_user
from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.schema.exam_registration import RegistrationCancel, RegistrationCreate, RegistrationMove

seeded = registration_cases.seeded

pytestmark = pytest.mark.integration


async def organized(s, *, actor="teacher", project="manager", exam=0, slot_id=None, now=NOW):
    async with s["uow"]() as u:
        return await reg_service(u, now).create_organized(
            s["workspace"],
            s["exams"][exam],
            RegistrationCreate(project_id=s["projects"][project], slot_id=slot_id),
            s["users"][actor],
        )


@pytest.mark.parametrize("actor", ["admin", "teacher", "local_teacher", "local_admin"])
@pytest.mark.parametrize("after_cutoff", [False, True])
async def test_scoped_organizer_assigns_before_and_after_registration_cutoff(seeded, actor, after_cutoff):
    s = seeded
    saved = await organized(s, actor=actor, project="member", now=START + timedelta(days=2) if after_cutoff else NOW)
    assert (saved.created_source, saved.created_by, saved.status) == ("organizer", s["users"][actor].id, "active")
    async with s["uow"]() as u:
        page = await reg_service(u).list_organized(
            s["workspace"], s["exams"][0], s["users"][actor], project_id=None, status=None, limit=50, offset=0
        )
        assert [row.id for row in page.items] == [saved.id]


@pytest.mark.parametrize("actor", ["manager", "member", "demoted", "null_manager", "outsider"])
async def test_organizer_routes_do_not_promote_manager_member_or_foreign_teacher(seeded, actor):
    with pytest.raises((PermissionError, NotFoundError)):
        await organized(seeded, actor=actor)
    assert await count(seeded, "exam_registration") == 0


async def test_workspace_authorship_does_not_grant_organizer_role(seeded):
    s = seeded
    async with s["uow"]() as u:
        await u.session.execute(
            text("UPDATE workspace SET author_id=:id WHERE id=:ws"),
            {"id": s["users"]["member"].id, "ws": s["workspace"]},
        )
    with pytest.raises(PermissionError):
        await organized(s, actor="member")


async def test_organizer_uses_same_published_type_scope_slot_and_global_uniqueness_rules(seeded):
    s = seeded
    async with s["uow"]() as u:
        slots = await reg_service(u).add_slots(s["workspace"], s["exams"][0], intervals(), s["users"]["teacher"])
    with pytest.raises(BusinessLogicError) as error:
        await organized(s)
    assert error.value.detail["code"] == "slot_required"
    await organized(s, slot_id=slots[0].id)
    with pytest.raises(BusinessLogicError) as error:
        await organized(s, project="manager2", slot_id=slots[0].id)
    assert error.value.detail["code"] == "slot_unavailable"
    with pytest.raises(BusinessLogicError) as error:
        await organized(s, exam=1)
    assert error.value.detail["code"] == "project_already_registered"
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await reg_service(u).create_organized(
                s["workspace"],
                s["draft"],
                RegistrationCreate(project_id=s["projects"]["manager2"]),
                s["users"]["teacher"],
            )
    assert error.value.detail["code"] == "exam_not_published"
    async with s["uow"]() as u:
        await u.session.execute(
            text("UPDATE project SET project_type_id=:type WHERE id=:id"),
            {"type": s["types"][1], "id": s["projects"]["manager2"]},
        )
    with pytest.raises(BusinessLogicError) as error:
        await organized(s, project="manager2", exam=1)
    assert error.value.detail["code"] == "project_type_not_allowed"
    with pytest.raises(NotFoundError):
        async with s["uow"]() as u:
            await reg_service(u).create_organized(
                s["foreign_workspace"],
                s["exams"][0],
                RegistrationCreate(project_id=s["projects"]["manager"]),
                s["users"]["admin"],
            )


async def test_organizer_transfer_and_cancel_after_cutoff_preserve_manager_origin(seeded):
    s = seeded
    saved = await self_register(s)
    late = START + timedelta(days=2)
    async with s["uow"]() as u:
        moved = await reg_service(u, late).move_organized(
            s["workspace"],
            s["exams"][0],
            saved.id,
            RegistrationMove(expected_version=1, target_exam_id=s["exams"][1], reason="Перенёс преподаватель"),
            s["users"]["teacher"],
        )
        assert moved.source.created_source == "manager" and moved.source.created_by == s["users"]["manager"].id
        assert moved.target.created_source == "organizer" and moved.target.created_by == s["users"]["teacher"].id
    async with s["uow"]() as u:
        await reg_service(u, late).cancel_organized(
            s["workspace"],
            s["exams"][1],
            moved.target.id,
            RegistrationCancel(expected_version=1, reason="Отмена преподавателем"),
            s["users"]["teacher"],
        )
        source = await reg_service(u).history(
            s["workspace"], s["exams"][0], saved.id, s["users"]["teacher"], limit=50, offset=0
        )
        assert [(e.action, e.source) for e in source.items] == [("created", "manager"), ("moved_out", "organizer")]
        assert source.items[-1].actor_id == s["users"]["teacher"].id
    assert await count(s, "registration_event") == 4


async def test_claim_returns_immutable_binding_and_permanently_blocks_changes(seeded):
    s = seeded
    saved = await self_register(s)
    async with s["uow"]() as u:
        binding = await reg_service(u).claim_for_attempt(
            s["workspace"],
            s["exams"][0],
            saved.id,
            expected_version=1,
            actor=s["users"]["teacher"],
            started_at=START.astimezone(timezone(timedelta(hours=3))),
        )
        assert (binding.registration_id, binding.exam_id, binding.project_id, binding.project_type_id) == (
            saved.id,
            s["exams"][0],
            s["projects"]["manager"],
            s["types"][0],
        )
        assert binding.started_at == START and binding.started_at.utcoffset() == timedelta(0)
        with pytest.raises(ValidationError):
            binding.exam_id = s["exams"][1]
    for method in ["cancel_organized", "move_organized"]:
        with pytest.raises(BusinessLogicError) as error:
            async with s["uow"]() as u:
                data = (
                    RegistrationCancel(expected_version=2, reason="Нельзя")
                    if method == "cancel_organized"
                    else RegistrationMove(expected_version=2, target_exam_id=s["exams"][1], reason="Нельзя")
                )
                await getattr(reg_service(u, START + timedelta(days=10)), method)(
                    s["workspace"], s["exams"][0], saved.id, data, s["users"]["teacher"]
                )
        assert error.value.detail["code"] == "defense_already_started"
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await reg_service(u).claim_for_attempt(
                s["workspace"],
                s["exams"][0],
                saved.id,
                expected_version=2,
                actor=s["users"]["teacher"],
                started_at=START,
            )
    assert error.value.detail["code"] == "defense_already_started"
    assert await count(s, "registration_event") == 2


@pytest.mark.parametrize("actor", ["manager", "member", "outsider"])
async def test_claim_requires_real_scoped_organizer(seeded, actor):
    s = seeded
    saved = await self_register(s)
    with pytest.raises((PermissionError, NotFoundError)):
        async with s["uow"]() as u:
            await reg_service(u).claim_for_attempt(
                s["workspace"], s["exams"][0], saved.id, expected_version=1, actor=s["users"][actor], started_at=START
            )
    assert await count(s, "registration_event") == 1


async def test_attempt_insert_and_claim_commit_or_rollback_together(seeded):
    s = seeded
    saved = await self_register(s)
    async with s["engine"].begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE test_attempt (registration_id INTEGER PRIMARY KEY, exam_id INTEGER NOT NULL, workspace_id INTEGER NOT NULL, project_id INTEGER NOT NULL, FOREIGN KEY (registration_id,exam_id,workspace_id) REFERENCES exam_registration(id,exam_id,workspace_id) DEFERRABLE INITIALLY DEFERRED)"
            )
        )
    with pytest.raises(IntegrityError):
        async with s["uow"]() as u:
            binding = await reg_service(u).claim_for_attempt(
                s["workspace"],
                s["exams"][0],
                saved.id,
                expected_version=1,
                actor=s["users"]["teacher"],
                started_at=START,
            )
            await u.session.execute(
                text("INSERT INTO test_attempt VALUES (:reg,:exam,-999,:project)"),
                {"reg": binding.registration_id, "exam": binding.exam_id, "project": binding.project_id},
            )
    async with s["engine"].connect() as conn:
        row = (
            await conn.execute(text("SELECT started_at,version FROM exam_registration WHERE id=:id"), {"id": saved.id})
        ).one()
        assert tuple(row) == (None, 1)
    assert await count(s, "registration_event") == 1 and await count(s, "test_attempt") == 0
    async with s["uow"]() as u:
        binding = await reg_service(u).claim_for_attempt(
            s["workspace"], s["exams"][0], saved.id, expected_version=1, actor=s["users"]["teacher"], started_at=START
        )
        await u.session.execute(
            text("INSERT INTO test_attempt VALUES (:reg,:exam,:ws,:project)"),
            {
                "reg": binding.registration_id,
                "exam": binding.exam_id,
                "ws": binding.workspace_id,
                "project": binding.project_id,
            },
        )
    assert await count(s, "test_attempt") == 1 and await count(s, "registration_event") == 2


@pytest.mark.parametrize("manager_first", [False, True])
@pytest.mark.parametrize("different_exam", [False, True])
async def test_manager_and_organizer_compete_for_same_project(seeded, manager_first, different_exam):
    s = seeded
    ready = asyncio.Event()
    pids = []

    async def create(u, manager, exam):
        service = reg_service(u)
        body = RegistrationCreate(project_id=s["projects"]["manager"])
        if manager:
            return await service.create_self(s["workspace"], s["exams"][exam], body, s["users"]["manager"])
        return await service.create_organized(s["workspace"], s["exams"][exam], body, s["users"]["teacher"])

    async def second():
        try:
            async with s["uow"]() as u:
                pids.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                return await create(u, not manager_first, int(different_exam))
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as first:
        winner = await create(first, manager_first, 0)
        task = asyncio.create_task(second())
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await wait_until_blocked(s, pids[0])
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == "project_already_registered"
    assert winner.created_source == ("manager" if manager_first else "organizer")
    assert await count(s, "exam_registration") == 1 and await count(s, "registration_event") == 1


@pytest.mark.parametrize("manager_first", [False, True])
async def test_manager_and_organizer_compete_for_one_slot(seeded, manager_first):
    s = seeded
    async with s["uow"]() as u:
        slots = await reg_service(u).add_slots(s["workspace"], s["exams"][0], intervals(), s["users"]["teacher"])
    ready = asyncio.Event()
    pids = []

    async def create(u, manager):
        service = reg_service(u)
        body = RegistrationCreate(project_id=s["projects"]["manager" if manager else "manager2"], slot_id=slots[0].id)
        if manager:
            return await service.create_self(s["workspace"], s["exams"][0], body, s["users"]["manager"])
        return await service.create_organized(s["workspace"], s["exams"][0], body, s["users"]["teacher"])

    async def second():
        try:
            async with s["uow"]() as u:
                pids.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                return await create(u, not manager_first)
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as first:
        await create(first, manager_first)
        task = asyncio.create_task(second())
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await wait_until_blocked(s, pids[0])
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == "slot_unavailable"
    assert await count(s, "exam_registration") == 1


@pytest.mark.parametrize("action", ["cancel", "move"])
@pytest.mark.parametrize("claim_first", [False, True])
async def test_attempt_start_and_change_serialize_in_both_orders(seeded, action, claim_first):
    s = seeded
    saved = await self_register(s)
    ready = asyncio.Event()
    pids = []

    async def act(u, claim):
        service = reg_service(u, START + timedelta(days=2))
        if claim:
            return await service.claim_for_attempt(
                s["workspace"],
                s["exams"][0],
                saved.id,
                expected_version=1,
                actor=s["users"]["teacher"],
                started_at=START,
            )
        if action == "cancel":
            return await service.cancel_organized(
                s["workspace"],
                s["exams"][0],
                saved.id,
                RegistrationCancel(expected_version=1, reason="Отмена"),
                s["users"]["teacher"],
            )
        return await service.move_organized(
            s["workspace"],
            s["exams"][0],
            saved.id,
            RegistrationMove(expected_version=1, target_exam_id=s["exams"][1], reason="Перенос"),
            s["users"]["teacher"],
        )

    async def second():
        try:
            async with s["uow"]() as u:
                pids.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                return await act(u, not claim_first)
        except BusinessLogicError as error:
            return error.detail["code"]

    async with s["uow"]() as first:
        await act(first, claim_first)
        task = asyncio.create_task(second())
        await asyncio.wait_for(ready.wait(), 5)
        try:
            await wait_until_blocked(s, pids[0])
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == (
        "defense_already_started" if claim_first else "registration_version_conflict"
    )
    assert await count(s, "registration_event") == (2 if claim_first or action == "cancel" else 3)


@pytest.mark.parametrize("value", [0, -1, True, "1", 2**65])
async def test_trusted_claim_rejects_invalid_expected_version(seeded, value):
    s = seeded
    saved = await self_register(s)
    with pytest.raises(ValidationError):
        async with s["uow"]() as u:
            await reg_service(u).claim_for_attempt(
                s["workspace"],
                s["exams"][0],
                saved.id,
                expected_version=value,
                actor=s["users"]["teacher"],
                started_at=START,
            )
    assert await count(s, "registration_event") == 1


async def test_claim_rejects_naive_and_overflowing_utc_time(seeded):
    s = seeded
    saved = await self_register(s)
    for value in [START.replace(tzinfo=None), datetime.max.replace(tzinfo=timezone(timedelta(hours=-14)))]:
        with pytest.raises(ValueError):
            async with s["uow"]() as u:
                await reg_service(u).claim_for_attempt(
                    s["workspace"],
                    s["exams"][0],
                    saved.id,
                    expected_version=1,
                    actor=s["users"]["teacher"],
                    started_at=value,
                )
    assert await count(s, "registration_event") == 1


async def test_http_organizer_manages_after_cutoff_but_manager_has_no_organizer_access(seeded, monkeypatch):
    s = seeded
    initial = await self_register(s)

    class LateClock(datetime):
        @classmethod
        def now(cls, tz=None):
            late = START + timedelta(days=2)
            return late.astimezone(tz) if tz else late.replace(tzinfo=None)

    monkeypatch.setattr("src.services.exam_registration_service.datetime", LateClock)
    app = FastAPI()
    app.include_router(routers)
    actor = [s["users"]["teacher"]]

    async def test_uow():
        async with s["uow"]() as u:
            yield u

    app.dependency_overrides[get_uow] = test_uow
    app.dependency_overrides[get_current_user] = lambda: actor[0]
    base = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/registrations"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assigned = await client.post(base, json={"project_id": s["projects"]["member"]})
        assert assigned.status_code == 201 and assigned.json()["created_source"] == "organizer"
        listed = await client.get(base)
        assert {r["project_id"] for r in listed.json()["items"]} == {s["projects"]["manager"], s["projects"]["member"]}
        cancelled = await client.post(
            f"{base}/{assigned.json()['id']}/cancel", json={"expected_version": 1, "reason": "Отмена после cutoff"}
        )
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
        moved = await client.post(
            f"{base}/{initial.id}/move",
            json={"expected_version": 1, "target_exam_id": s["exams"][1], "reason": "Перенос после cutoff"},
        )
        assert moved.status_code == 200 and moved.json()["source"]["created_source"] == "manager"
        actor[0] = s["users"]["manager"]
        forbidden = await client.get(base)
        assert forbidden.status_code == 403
        own = await client.get(base + "/self")
        assert own.status_code == 200 and [r["id"] for r in own.json()["items"]] == [initial.id]


async def test_claim_after_local_teacher_revocation_while_waiting_is_denied(seeded):
    s = seeded
    saved = await self_register(s)
    ready = asyncio.Event()
    pids = []

    async def other():
        try:
            async with s["uow"]() as u:
                pids.append(await u.session.scalar(text("SELECT pg_backend_pid()")))
                ready.set()
                return await reg_service(u).claim_for_attempt(
                    s["workspace"],
                    s["exams"][0],
                    saved.id,
                    expected_version=1,
                    actor=s["users"]["local_teacher"],
                    started_at=START,
                )
        except PermissionError:
            return "forbidden"

    async with s["uow"]() as first:
        await first.session.execute(text("SELECT id FROM exam WHERE id=:id FOR UPDATE"), {"id": s["exams"][0]})
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
    assert await count(s, "registration_event") == 1


@pytest.mark.parametrize("draft", [False, True])
async def test_claim_rejects_inactive_registration_and_unpublished_exam(seeded, draft):
    s = seeded
    saved = await self_register(s)
    if draft:
        async with s["uow"]() as u:
            await u.session.execute(
                text("UPDATE exam SET status='draft',published_at=NULL,published_by=NULL WHERE id=:id"),
                {"id": s["exams"][0]},
            )
        expected_version = 1
    else:
        async with s["uow"]() as u:
            await reg_service(u).cancel_organized(
                s["workspace"],
                s["exams"][0],
                saved.id,
                RegistrationCancel(expected_version=1, reason="Отмена"),
                s["users"]["teacher"],
            )
        expected_version = 2
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await reg_service(u).claim_for_attempt(
                s["workspace"],
                s["exams"][0],
                saved.id,
                expected_version=expected_version,
                actor=s["users"]["teacher"],
                started_at=START,
            )
    assert error.value.detail["code"] == ("exam_not_published" if draft else "registration_not_active")
