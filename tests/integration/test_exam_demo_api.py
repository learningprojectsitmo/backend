from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx
import pytest
import pytest_asyncio
import test_exam_registrations_db as registration_cases
from fastapi import FastAPI
from sqlalchemy import text

from src.api.v1.routes import routers
from src.core.container import get_uow
from src.core.dependencies import get_current_user
from src.repository.exam_repository import ExamRepository

pytestmark = pytest.mark.integration
seeded = registration_cases.seeded


@pytest_asyncio.fixture
async def api(seeded, monkeypatch):
    s = seeded
    now = [registration_cases.NOW]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now[0].astimezone(tz) if tz else now[0].replace(tzinfo=None)

    for service in ("exam", "exam_registration", "exam_attempt", "exam_queue", "exam_assessment", "exam_result"):
        monkeypatch.setattr(f"src.services.{service}_service.datetime", Clock)
    app = FastAPI()
    app.include_router(routers)

    async def test_uow():
        async with s["uow"]() as uow:
            yield uow

    async def test_user(x_test_actor: str = "teacher"):
        return s["users"][x_test_actor]

    app.dependency_overrides[get_uow] = test_uow
    app.dependency_overrides[get_current_user] = test_user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, f"/v1/workspaces/{s['workspace']}/exams", now


def body(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


async def register(client, path, s, project="manager", **fields):
    return body(await client.post(path + "/registrations", json={"project_id": s["projects"][project], **fields}), 201)


async def begin(client, path, reg):
    return body(
        await client.post(path + "/attempts", json={"registration_id": reg["id"], "expected_version": reg["version"]}),
        201,
    )


async def finish(client, path, attempt):
    return body(
        await client.post(path + f"/attempts/{attempt['id']}/finish", json={"expected_version": attempt["version"]})
    )


async def settings(client, path, current=None, **changes):
    current = current or body(await client.get(path))
    return await client.put(
        path + "/settings",
        json={
            "expected_version": current["current_settings_version"],
            "reason": "Correct the schedule",
            "configuration": {**current["configuration"], **changes},
        },
    )


async def test_exam_remains_listed_through_all_defenses(api, seeded):
    client, base, now = api
    created = body(
        await client.post(
            base,
            json={
                "title": "Earlier exam",
                "starts_at": "2026-11-19T15:30:00+03:00",
                "project_type_ids": [seeded["types"][0]],
            },
        ),
        201,
    )
    eid = created["id"]
    path = f"{base}/{eid}"

    async def check(status):
        for actor in ("teacher", "member"):
            hidden = actor == "member" and status == "draft"
            params = {"x_test_actor": actor}
            response = await client.get(path, params=params)
            detail = None if hidden else body(response)
            if hidden:
                assert response.status_code == 404
            for query in ({}, {"status": status}, {"limit": 1, "offset": 0}):
                items = body(await client.get(base, params={**params, **query}))["items"]
                assert [e for e in items if e["id"] == eid] == ([] if hidden else [detail])
            page = body(await client.get(base, params={**params, "limit": 1, "offset": 1}))
            assert eid not in [e["id"] for e in page["items"]]
        async with seeded["engine"].connect() as db:
            assert await db.scalar(text("SELECT status FROM exam WHERE id=:id"), {"id": eid}) == status

    await check("draft")
    body(await client.post(path + "/publish", json={"expected_version": 1}))
    await check("published")
    first = await register(client, path, seeded)
    second = await register(client, path, seeded, "manager2")
    await finish(client, path, await begin(client, path, first))
    await check("published")
    assert {q["state"] for q in body(await client.get(path + "/queue"))["items"]} == {"finished", "waiting"}
    now[0] += timedelta(minutes=1)
    await finish(client, path, await begin(client, path, second))
    await check("published")


@pytest.mark.parametrize("kind", ["empty_draft", "draft_with_slots", "published"])
async def test_http_reschedule_when_slots_remain_valid(api, seeded, kind):
    client, base, _now = api
    draft = kind != "published"
    path = f"{base}/{seeded['draft'] if draft else seeded['exams'][0]}"
    current = body(await client.get(path))
    slots = []
    registration = None
    if kind != "empty_draft":
        slots = body(
            await client.post(
                path + "/slots",
                json={"slots": [{"starts_at": "2026-11-30T15:30:00+03:00", "ends_at": "2026-11-30T15:45:00+03:00"}]},
            ),
            201,
        )
        if not draft:
            registration = await register(client, path, seeded, slot_id=slots[0]["id"])
        conflict = await settings(client, path, current, starts_at="2026-11-30T16:00:00+03:00")
        assert body(conflict, 409)["detail"]["code"] == "slot_schedule_conflict"
    new = "2026-11-29T00:30:00+03:00"
    updated = body(await settings(client, path, current, starts_at=new))
    assert updated["configuration"]["starts_at"] == "2026-11-28T21:30:00Z"
    assert updated == body(await client.get(path))
    assert updated in body(await client.get(base))["items"]
    assert body(await client.get(path + "/settings/1"))["configuration"] == current["configuration"]
    stale = await settings(client, path, current, starts_at=new)
    assert body(stale, 409)["detail"]["code"] == "settings_version_conflict"
    assert (await settings(client, path, registration_closes_at="2026-11-30T15:30:00+03:00")).status_code == 422
    if registration:
        assert body(await client.get(path + "/registrations"))["items"] == [registration]
        post_slots = body(await client.get(path + "/slots"))["items"]
        assert [(r["id"], r["starts_at"], r["ends_at"]) for r in post_slots] == [
            (r["id"], r["starts_at"], r["ends_at"]) for r in slots
        ]


@pytest.mark.parametrize("explicit", [False, True])
async def test_published_date_cannot_move_once_started(api, seeded, explicit):
    client, base, _now = api
    path = f"{base}/{seeded['exams'][0]}"
    if explicit:
        body(await client.post(path + "/start"))
        attempt = None
    else:
        attempt = await begin(client, path, await register(client, path, seeded))
    before = body(await client.get(path))
    assert before["started_at"] is not None
    conflict = await settings(client, path, before, starts_at="2026-12-01T15:30:00+03:00")
    assert body(conflict, 409)["detail"]["code"] == "published_schedule_locked"
    assert body(await client.get(path)) == before
    if attempt:
        assert body(await client.get(f"{path}/attempts/{attempt['id']}")) == attempt


@pytest.mark.parametrize("transition,gap", [(2, 10), (0, 0)])
async def test_http_slot_gap_and_eta_are_independent_and_times_have_offsets(api, seeded, transition, gap):
    client, base, now = api
    path = f"{base}/{seeded['exams'][0]}"
    updated = body(await settings(client, path, transition_minutes=transition))
    assert updated["configuration"]["transition_minutes"] == transition
    slots = body(
        await client.post(
            path + "/slots",
            json={
                "slots": [
                    {"starts_at": "2026-11-30T14:00:00+03:00", "ends_at": "2026-11-30T14:15:00+03:00"},
                    {"starts_at": f"2026-11-30T14:{15 + gap}:00+03:00", "ends_at": "2026-11-30T14:40:00+03:00"},
                    {"starts_at": "2026-12-01T00:15:00+03:00", "ends_at": "2026-12-01T00:30:00+03:00"},
                    {"starts_at": "2026-12-01T15:30:00+03:00", "ends_at": "2026-12-01T15:45:00+03:00"},
                ]
            },
        ),
        201,
    )
    assert body(await client.get(path + "/slots"))["items"] == slots
    assert datetime.fromisoformat(slots[1]["starts_at"]) - datetime.fromisoformat(slots[0]["ends_at"]) == timedelta(
        minutes=gap
    )
    assert slots[2]["ends_at"] == "2026-11-30T21:30:00Z"
    assert slots[3]["starts_at"] == "2026-12-01T12:30:00Z"
    first = await register(client, path, seeded, slot_id=slots[2]["id"])
    second = await register(client, path, seeded, "manager2", slot_id=slots[3]["id"])
    now[0] = datetime.fromisoformat("2026-11-30T14:00:00+03:00")
    await begin(client, path, first)
    queue = body(await client.get(path + "/queue"))
    assert queue["server_now"] == "2026-11-30T11:00:00Z"
    by_reg = {q["registration_id"]: q for q in queue["items"]}
    assert by_reg[first["id"]]["planned_end_at"] == slots[2]["ends_at"]
    assert by_reg[second["id"]]["planned_start_at"] == slots[3]["starts_at"]
    forecast = queue["eta"]["items"][0]
    assert forecast["registration_id"] == second["id"]
    assert forecast["eta_seconds"] == (7 + 7 + transition) * 60


@pytest.mark.parametrize("admin", ["admin", "local_admin"])
async def test_admin_deletes_only_scoped_empty_draft(api, seeded, admin):
    client, base, _now = api
    path = f"{base}/{seeded['draft']}"
    assert (await client.delete(path, params={"x_test_actor": "member"})).status_code == 404
    assert (await client.delete(path, params={"x_test_actor": "teacher"})).status_code == 403
    foreign = f"/v1/workspaces/{seeded['foreign_workspace']}/exams/{seeded['draft']}"
    assert (await client.delete(foreign, params={"x_test_actor": "admin"})).status_code == 404
    deleted = await client.delete(path, params={"x_test_actor": admin})
    assert deleted.status_code == 204 and deleted.content == b""
    assert (await client.delete(path, params={"x_test_actor": admin})).status_code == 404
    assert (await client.get(path)).status_code == 404
    async with seeded["engine"].connect() as db:
        for table in ("exam_settings_project_type", "exam_settings_revision"):
            assert (
                await db.scalar(text(f"SELECT count(*) FROM {table} WHERE exam_id=:id"), {"id": seeded["draft"]}) == 0
            )


@pytest.mark.parametrize("list_exams", [False, True])
async def test_read_handles_draft_deleted_after_root_query(api, seeded, monkeypatch, list_exams):
    client, base, _now = api
    draft = seeded["draft"]
    path = f"{base}/{draft}"
    selected = asyncio.Event()
    deleted = asyncio.Event()
    original = ExamRepository.revision_configuration

    async def read_configuration(repo, exam_id, version):
        if exam_id == draft:
            selected.set()
            await asyncio.wait_for(deleted.wait(), timeout=5)
        return await original(repo, exam_id, version)

    monkeypatch.setattr(ExamRepository, "revision_configuration", read_configuration)
    read = asyncio.create_task(client.get(base, params={"status": "draft"}) if list_exams else client.get(path))
    try:
        await asyncio.wait_for(selected.wait(), timeout=5)
        assert (await client.delete(path, params={"x_test_actor": "admin"})).status_code == 204
    finally:
        deleted.set()
        response = await read
    if list_exams:
        assert draft not in {item["id"] for item in body(response)["items"]}
    else:
        assert response.status_code == 404


@pytest.mark.parametrize("action", ["archive", "complete"])
async def test_lifecycle_downgrade_preserves_recorded_state(api, seeded, run_migrations, action):
    client, base, _now = api
    path = f"{base}/{seeded['exams'][0]}"
    if action == "archive":
        assert (await client.delete(path, params={"x_test_actor": "admin"})).status_code == 204
    else:
        reg = await register(client, path, seeded)
        await finish(client, path, await begin(client, path, reg))
        body(await client.post(path + "/complete"))
    before = body(await client.get(path))

    with pytest.raises(AssertionError, match="Cannot downgrade while completed or archived exams exist"):
        run_migrations(seeded["url"], "downgrade", "d116a10b20c9")

    assert body(await client.get(path)) == before
    run_migrations(seeded["url"], "check")


async def test_admin_archives_published_exam_with_registrations(api, seeded):
    client, base, _now = api
    path = f"{base}/{seeded['exams'][0]}"
    reg = await register(client, path, seeded)
    assert (await client.delete(path, params={"x_test_actor": "member"})).status_code == 403
    for _ in range(2):
        assert (await client.delete(path, params={"x_test_actor": "admin"})).status_code == 204
    assert body(await client.get(path))["archived_at"] is not None
    assert body(await client.get(path + "/registrations"))["items"] == [reg]
    assert seeded["exams"][0] not in [e["id"] for e in body(await client.get(base))["items"]]
    assert [e["id"] for e in body(await client.get(base, params={"status": "archived"}))["items"]] == [
        seeded["exams"][0]
    ]
    assert body(await client.get(base, params={"status": "archived", "x_test_actor": "member"}))["items"] == []
    new_reg = await client.post(path + "/registrations", json={"project_id": seeded["projects"]["manager2"]})
    assert body(new_reg, 409)["detail"]["code"] == "exam_archived"


async def test_start_is_explicit_idempotent_and_does_not_start_defense(api, seeded):
    client, base, now = api
    path = f"{base}/{seeded['exams'][0]}"
    draft = f"{base}/{seeded['draft']}"
    assert body(await client.get(path))["started_at"] is None
    assert body(await client.post(path + "/complete"), 409)["detail"]["code"] == "exam_not_started"
    assert body(await client.post(draft + "/start"), 409)["detail"]["code"] == "exam_not_published"
    assert (await client.post(path + "/start", params={"x_test_actor": "manager"})).status_code == 403
    assert (await client.post(path + "/start", params={"x_test_actor": "outsider"})).status_code == 404
    registration = await register(client, path, seeded)
    before = body(await client.get(path + "/queue"))
    started = body(await client.post(path + "/start", params={"x_test_actor": "local_teacher"}))
    assert datetime.fromisoformat(started["started_at"]) == now[0]
    assert started["status"] == "published" and started["completed_at"] is None
    assert started == body(await client.get(path))
    assert started in body(await client.get(base, params={"x_test_actor": "member"}))["items"]
    queue = body(await client.get(path + "/queue"))
    assert queue["started_at"] == started["started_at"]
    assert queue["queue_revision"] == before["queue_revision"] + 1
    assert queue["eta"]["items"][0]["eta_seconds"] == 0
    assert queue["items"][0]["registration_id"] == registration["id"]
    assert queue["items"][0]["attempt"] is None and queue["items"][0]["state"] == "waiting"
    assert body(await client.post(path + "/complete"), 409)["detail"]["code"] == "exam_queue_unresolved"

    now[0] += timedelta(minutes=2)
    assert body(await client.post(path + "/start")) == started
    attempt = await begin(client, path, registration)
    assert attempt["started_at"] != started["started_at"]
    assert body(await client.get(path))["started_at"] == started["started_at"]
    await finish(client, path, attempt)
    assert body(await client.post(path + "/complete"))["completed_at"] is not None
    assert body(await client.post(path + "/start"), 409)["detail"]["code"] == "exam_completed"


@pytest.mark.parametrize("legacy_write", [False, True])
async def test_legacy_first_attempt_starts_exam_and_closes_self_service(api, seeded, legacy_write):
    client, base, _now = api
    path = f"{base}/{seeded['exams'][0]}"
    first = await register(client, path, seeded)
    second = await register(client, path, seeded, "manager2")
    attempt = await begin(client, path, first)
    async with seeded["engine"].begin() as conn:
        exam_id = seeded["exams"][0]
        assert await conn.scalar(
            text("SELECT started_at FROM exam WHERE id = :id"), {"id": exam_id}
        ) == datetime.fromisoformat(attempt["started_at"])
        if legacy_write:
            # Simulate an old process writing a defense after the migration, without the new column.
            await conn.execute(text("UPDATE exam SET started_at = NULL WHERE id = :id"), {"id": exam_id})
    assert body(await client.get(path))["started_at"] == attempt["started_at"]
    assert body(await client.get(path + "/queue"))["started_at"] == attempt["started_at"]
    reg_url = f"{path}/registrations/{second['id']}"
    params = {"x_test_actor": "manager2"}
    data = {"expected_version": second["version"], "reason": "Change plans"}
    for suffix, fields in (("/self-cancel", {}), ("/self-move", {"target_exam_id": seeded["exams"][1]})):
        response = await client.post(reg_url + suffix, params=params, json={**data, **fields})
        assert body(response, 409)["detail"]["code"] == "registration_closed"
    assert body(await client.post(reg_url + "/cancel", json=data))["status"] == "cancelled"


async def test_start_closes_self_service_on_both_sides_of_transfer(api, seeded):
    client, base, _now = api
    source, target = (f"{base}/{eid}" for eid in seeded["exams"])
    pending = await register(client, source, seeded)
    body(await client.post(target + "/start"))
    reg_url = f"{source}/registrations/{pending['id']}"
    data = {"expected_version": pending["version"], "reason": "Other exam", "target_exam_id": seeded["exams"][1]}
    assert (
        body(await client.post(reg_url + "/self-move", json=data, params={"x_test_actor": "manager"}), 409)["detail"][
            "code"
        ]
        == "registration_closed"
    )
    assert (
        body(
            await client.post(
                target + "/registrations/self",
                json={"project_id": seeded["projects"]["manager2"]},
                params={"x_test_actor": "manager2"},
            ),
            409,
        )["detail"]["code"]
        == "registration_closed"
    )
    moved = body(await client.post(reg_url + "/move", json=data))
    assert moved["target"]["exam_id"] == seeded["exams"][1]
    assert (
        body(
            await client.post(
                f"{target}/registrations/{moved['target']['id']}/self-cancel",
                json={"expected_version": moved["target"]["version"], "reason": "Change mind"},
                params={"x_test_actor": "manager"},
            ),
            409,
        )["detail"]["code"]
        == "registration_closed"
    )


async def test_start_and_self_cancellation_are_serialized(api, seeded, monkeypatch):
    client, base, _now = api
    path = f"{base}/{seeded['exams'][0]}"
    registration = await register(client, path, seeded)
    held = asyncio.Event()
    release = asyncio.Event()
    cancel_waiting = asyncio.Event()
    original = ExamRepository.bump_queue_revision
    get_scoped = ExamRepository.get_scoped

    async def hold_start(repo, exam_id):
        held.set()
        await asyncio.wait_for(release.wait(), timeout=5)
        return await original(repo, exam_id)

    async def observe_cancel(repo, workspace_id, exam_id, *, lock=False):
        if lock:
            cancel_waiting.set()
        return await get_scoped(repo, workspace_id, exam_id, lock=lock)

    monkeypatch.setattr(ExamRepository, "bump_queue_revision", hold_start)
    start = asyncio.create_task(client.post(path + "/start"))
    try:
        await asyncio.wait_for(held.wait(), timeout=5)
        monkeypatch.setattr(ExamRepository, "get_scoped", observe_cancel)
        cancel = asyncio.create_task(
            client.post(
                f"{path}/registrations/{registration['id']}/self-cancel",
                params={"x_test_actor": "manager"},
                json={"expected_version": registration["version"], "reason": "Race start"},
            )
        )
        await asyncio.wait_for(cancel_waiting.wait(), timeout=5)
        assert not cancel.done()
    finally:
        release.set()
        body(await start)
    assert body(await cancel, 409)["detail"]["code"] == "registration_closed"
    assert body(await client.get(path + "/registrations"))["items"][0]["status"] == "active"


async def test_migration_backfills_legacy_starts(api, seeded, run_migrations):
    client, base, now = api
    attempts_path, completed_path = (f"{base}/{eid}" for eid in seeded["exams"])
    attempt = await begin(client, attempts_path, await register(client, attempts_path, seeded))
    run_migrations(seeded["url"], "downgrade", "d117a11b20a3")
    async with seeded["engine"].begin() as conn:
        await conn.execute(
            text("UPDATE exam SET completed_at = :at WHERE id = :id"),
            {"at": now[0], "id": seeded["exams"][1]},
        )
    run_migrations(seeded["url"], "upgrade", "head")
    assert body(await client.get(attempts_path))["started_at"] == attempt["started_at"]
    previously_completed = body(await client.get(completed_path))
    assert previously_completed["started_at"] == previously_completed["completed_at"]
    run_migrations(seeded["url"], "check")


async def test_migration_downgrade_does_not_erase_explicit_start(api, seeded, run_migrations):
    client, base, _now = api
    path = f"{base}/{seeded['exams'][0]}"
    started = body(await client.post(path + "/start"))
    with pytest.raises(AssertionError, match="Cannot downgrade while explicit exam starts exist"):
        run_migrations(seeded["url"], "downgrade", "d117a11b20a3")
    assert body(await client.get(path)) == started


async def test_complete_explicitly_after_resolving_queue(api, seeded):
    client, base, _now = api
    path = f"{base}/{seeded['exams'][0]}"
    regs = [await register(client, path, seeded, name) for name in ("manager", "manager2")]
    first_attempt = await finish(client, path, await begin(client, path, regs[0]))
    assert body(await client.get(path))["completed_at"] is None
    assert body(await client.post(path + "/complete"), 409)["detail"]["code"] == "exam_queue_unresolved"
    await finish(client, path, await begin(client, path, regs[1]))
    assert body(await client.get(path))["completed_at"] is None
    assert (await client.post(path + "/complete", params={"x_test_actor": "member"})).status_code == 403
    completed = body(await client.post(path + "/complete"))
    assert completed["completed_at"] is not None
    assert body(await client.post(path + "/complete")) == completed
    assert body(await client.get(base, params={"status": "completed"}))["items"] == [completed]
    assert completed in body(await client.get(base, params={"status": "published", "x_test_actor": "member"}))["items"]
    new_reg = await client.post(path + "/registrations", json={"project_id": seeded["projects"]["member"]})
    assert body(new_reg, 409)["detail"]["code"] == "exam_completed"
    assert body(await client.get(path + f"/attempts/{first_attempt['id']}"))["status"] == "finished"


@pytest.mark.parametrize("command", ["register", "start"])
async def test_archive_serializes_with_registration_and_first_attempt(api, seeded, command):
    client, base, _now = api
    path = f"{base}/{seeded['exams'][0]}"
    if command == "register":
        mutation = client.post(path + "/registrations", json={"project_id": seeded["projects"]["manager"]})
    else:
        reg = await register(client, path, seeded)
        mutation = client.post(
            path + "/attempts", json={"registration_id": reg["id"], "expected_version": reg["version"]}
        )
    archived, outcome = await asyncio.gather(client.delete(path, params={"x_test_actor": "admin"}), mutation)
    assert archived.status_code == 204
    assert body(await client.get(path))["archived_at"] is not None
    if outcome.status_code == 409:
        assert body(outcome, 409)["detail"]["code"] == "exam_archived"
    else:
        created = body(outcome, 201)
        if command == "register":
            assert body(await client.get(path + "/registrations"))["items"] == [created]
        else:
            assert (await finish(client, path, created))["status"] == "finished"
    second = await client.post(path + "/registrations", json={"project_id": seeded["projects"]["manager2"]})
    assert body(second, 409)["detail"]["code"] == "exam_archived"


@pytest.mark.parametrize("closed", ["archived", "completed"])
@pytest.mark.parametrize("command", ["cancel", "move"])
async def test_organizer_can_release_unstarted_registration_from_closed_exam(api, seeded, closed, command):
    client, base, _now = api
    source = f"{base}/{seeded['exams'][0]}"
    target = f"{base}/{seeded['exams'][1]}"
    reg = await register(client, source, seeded)
    if closed == "archived":
        assert (await client.delete(source, params={"x_test_actor": "admin"})).status_code == 204
    else:
        body(await client.post(source + "/start"))
        mutation = body(
            await client.post(
                f"{source}/queue/{reg['id']}/no-show",
                json={"expected_version": reg["version"], "reason": "Team did not attend"},
            )
        )
        reg["version"] = mutation["item"]["registration_version"]
        body(await client.post(source + "/complete"))

    url = f"{source}/registrations/{reg['id']}"
    request = {"expected_version": reg["version"], "reason": "Team will attend another exam"}
    if command == "cancel":
        changed = body(await client.post(url + "/cancel", json=request))
        assert changed["status"] == "cancelled"
        added = await register(client, target, seeded)
    else:
        blocked = await client.post(url + "/move", json={**request, "target_exam_id": reg["exam_id"]})
        assert body(blocked, 409)["detail"]["code"] == f"exam_{closed}"
        moved = body(await client.post(url + "/move", json={**request, "target_exam_id": seeded["exams"][1]}))
        changed, added = moved["source"], moved["target"]
        assert changed["status"] == "moved"
    assert changed["id"] == reg["id"] and added["project_id"] == reg["project_id"]
    assert body(await client.get(source + "/registrations"))["items"] == [changed]
    assert body(await client.get(target + "/registrations"))["items"] == [added]

    other = await register(client, target, seeded, "manager2")
    move_in = await client.post(
        f"{target}/registrations/{other['id']}/move",
        json={"expected_version": other["version"], "reason": "Try closed exam", "target_exam_id": reg["exam_id"]},
    )
    assert body(move_in, 409)["detail"]["code"] == f"exam_{closed}"


@pytest.mark.parametrize("restart", [False, True])
async def test_conditional_defense_rejects_reorder_without_attempt_or_registration_version_change(api, seeded, restart):
    client, base, _now = api
    path = f"{base}/{seeded['exams'][0]}"
    first = await register(client, path, seeded)
    second = await register(client, path, seeded, "manager2")
    if restart:
        started = await begin(client, path, first)
        attempt_path = f"{path}/attempts/{started['id']}"
        mutation = body(
            await client.post(
                attempt_path + "/postpone", json={"expected_version": started["version"], "reason": "Pause"}
            )
        )
        snapshot = body(await client.get(path + "/queue"))
        old_first = next(item for item in snapshot["items"] if item["registration_id"] == first["id"])
        body(
            await client.post(
                f"{path}/queue/{first['id']}/place",
                json={"expected_version": old_first["registration_version"], "position": 1},
            )
        )
        request_path = attempt_path + "/restart"
        fields = {"expected_version": mutation["version"]}
    else:
        request_path = path + "/attempts"
        fields = {"registration_id": first["id"], "expected_version": first["version"]}

    before = body(await client.get(path + "/queue"))
    if not restart:
        assert before["items"][0]["registration_version"] == first["version"]
    moved = body(
        await client.post(
            f"{path}/queue/{second['id']}/place",
            json={"expected_version": second["version"], "position": 1},
        )
    )
    assert moved["queue_revision"] > before["queue_revision"]
    stale = {**fields, "expected_queue_revision": before["queue_revision"]}
    denied = await client.post(request_path, json=stale, params={"x_test_actor": "manager"})
    assert denied.status_code == 403
    assert body(await client.post(request_path, json=stale), 409)["detail"]["code"] == "queue_revision_conflict"
    after = body(await client.get(path + "/queue"))
    assert after["eta"]["current"] is None
    assert after["items"][0]["registration_id"] == second["id"]
    assert after["items"][1]["registration_id"] == first["id"]
    assert after["items"][1]["registration_version"] == before["items"][0]["registration_version"]
    if restart:
        assert body(await client.get(attempt_path))["version"] == mutation["version"]
    accepted = body(
        await client.post(request_path, json={**fields, "expected_queue_revision": after["queue_revision"]}),
        200 if restart else 201,
    )
    assert accepted["registration_id"] == first["id"] and accepted["status"] == "speaking"


async def test_conditional_restart_rejects_archived_exam(api, seeded):
    client, base, _now = api
    path = f"{base}/{seeded['exams'][0]}"
    attempt = await begin(client, path, await register(client, path, seeded))
    url = f"{path}/attempts/{attempt['id']}"
    postponed = body(
        await client.post(url + "/postpone", json={"expected_version": attempt["version"], "reason": "Pause"})
    )
    assert (await client.delete(path, params={"x_test_actor": "admin"})).status_code == 204
    queue = body(await client.get(path + "/queue"))
    response = await client.post(
        url + "/restart",
        json={"expected_version": postponed["version"], "expected_queue_revision": queue["queue_revision"]},
    )
    assert body(response, 409)["detail"]["code"] == "exam_archived"
    assert body(await client.get(url))["status"] == "postponed"


async def test_published_registration_can_reopen_before_actual_start(api, seeded):
    client, base, now = api
    path = f"{base}/{seeded['exams'][0]}"
    cutoff = now[0] + timedelta(hours=1)
    initial = body(await settings(client, path, registration_closes_at=cutoff.isoformat()))
    now[0] = cutoff + timedelta(minutes=5)
    registration = {"project_id": seeded["projects"]["manager"]}
    params = {"x_test_actor": "manager"}
    response = await client.post(path + "/registrations/self", json=registration, params=params)
    assert body(response, 409)["detail"]["code"] == "registration_closed"

    new_cutoff = now[0] + timedelta(hours=1)
    reopened = body(
        await settings(
            client,
            path,
            initial,
            registration_opens_at=cutoff.isoformat(),
            registration_closes_at=new_cutoff.isoformat(),
        )
    )
    assert reopened["status"] == "published"
    assert reopened["current_settings_version"] == initial["current_settings_version"] + 1
    assert datetime.fromisoformat(reopened["configuration"]["registration_opens_at"]) == cutoff
    assert datetime.fromisoformat(reopened["configuration"]["registration_closes_at"]) == new_cutoff
    assert (
        body(await client.post(path + "/registrations/self", json=registration, params=params), 201)["status"]
        == "active"
    )
    stale = await settings(client, path, initial, registration_closes_at=None)
    assert body(stale, 409)["detail"]["code"] == "settings_version_conflict"
    reset = body(await settings(client, path, reopened, registration_opens_at=None, registration_closes_at=None))
    assert reset["configuration"]["registration_opens_at"] is None
    assert reset["configuration"]["registration_closes_at"] is None


async def test_overdue_published_exam_can_move_to_future_while_waiting(api, seeded):
    client, base, now = api
    path = f"{base}/{seeded['exams'][0]}"
    before = body(await client.get(path))
    old_start = datetime.fromisoformat(before["configuration"]["starts_at"])
    now[0] = old_start + timedelta(hours=1)
    past = await settings(client, path, before, starts_at=(now[0] - timedelta(minutes=1)).isoformat())
    assert body(past, 409)["detail"]["code"] == "exam_start_must_be_future"
    future = now[0] + timedelta(days=1)
    updated = body(await settings(client, path, before, starts_at=future.isoformat()))
    assert datetime.fromisoformat(updated["configuration"]["starts_at"]) == future
    assert updated["started_at"] is None and updated["status"] == "published"
    response = await client.post(
        path + "/registrations/self",
        params={"x_test_actor": "manager"},
        json={"project_id": seeded["projects"]["manager"]},
    )
    assert body(response, 201)["status"] == "active"


async def test_overdue_reschedule_preserves_saved_slot_conflict(api, seeded):
    client, base, now = api
    path = f"{base}/{seeded['exams'][0]}"
    before = body(await client.get(path))
    old_start = datetime.fromisoformat(before["configuration"]["starts_at"])
    slots = body(
        await client.post(
            path + "/slots",
            json={
                "slots": [
                    {
                        "starts_at": (old_start + timedelta(minutes=15)).isoformat(),
                        "ends_at": (old_start + timedelta(minutes=30)).isoformat(),
                    }
                ]
            },
        ),
        201,
    )
    now[0] = old_start + timedelta(hours=1)
    response = await settings(client, path, before, starts_at=(now[0] + timedelta(days=1)).isoformat())
    assert body(response, 409)["detail"]["code"] == "slot_schedule_conflict"
    assert body(await client.get(path)) == before
    assert body(await client.get(path + "/slots"))["items"][0]["id"] == slots[0]["id"]


@pytest.mark.parametrize("state", ["started", "completed", "archived"])
async def test_published_registration_dates_lock_after_lifecycle_change(api, seeded, state):
    client, base, now = api
    path = f"{base}/{seeded['exams'][0]}"
    invalid = await settings(
        client,
        path,
        registration_opens_at=(now[0] + timedelta(hours=2)).isoformat(),
        registration_closes_at=(now[0] + timedelta(hours=1)).isoformat(),
    )
    assert invalid.status_code == 422
    if state == "archived":
        assert (await client.delete(path, params={"x_test_actor": "admin"})).status_code == 204
        error = "exam_archived"
    else:
        body(await client.post(path + "/start"))
        if state == "completed":
            body(await client.post(path + "/complete"))
        error = "published_schedule_locked"
    before = body(await client.get(path))
    conflict = await settings(client, path, before, registration_closes_at=(now[0] + timedelta(hours=1)).isoformat())
    assert body(conflict, 409)["detail"]["code"] == error
    assert body(await client.get(path)) == before
