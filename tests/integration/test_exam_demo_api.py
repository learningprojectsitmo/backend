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


async def test_published_date_cannot_move_once_first_defense_starts(api, seeded):
    client, base, _now = api
    path = f"{base}/{seeded['exams'][0]}"
    before = body(await client.get(path))
    attempt = await begin(client, path, await register(client, path, seeded))
    conflict = await settings(client, path, before, starts_at="2026-12-01T15:30:00+03:00")
    assert body(conflict, 409)["detail"]["code"] == "published_schedule_locked"
    assert body(await client.get(path)) == before
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
