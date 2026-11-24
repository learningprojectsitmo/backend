from __future__ import annotations

import asyncio
from datetime import timedelta

import httpx
import pytest
import test_exam_registrations_db as registration_cases
from fastapi import FastAPI
from sqlalchemy import text
from test_exam_eta_db import read_eta, start
from test_exam_queue_db import register

from src.api.v1.routes import routers
from src.core.container import get_uow
from src.core.dependencies import get_current_user
from src.core.exceptions import BusinessLogicError, NotFoundError
from src.schema.exam_registration import RegistrationCreate, SlotBatchCreate, SlotScheduleReplace

pytestmark = pytest.mark.integration
seeded = registration_cases.seeded
START = registration_cases.START
reg_service = registration_cases.reg_service
self_register = registration_cases.self_register


def interval(start, minutes=15, **fields):
    return {
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(minutes=minutes)).isoformat(),
        "kind": "defense",
        **fields,
    }


def snapshot(rows):
    return [{name: row[name] for name in ("id", "starts_at", "ends_at", "kind")} for row in rows]


def client_for(s, actor="teacher"):
    async def test_uow():
        async with s["uow"]() as uow:
            yield uow

    app = FastAPI()
    app.include_router(routers)
    app.dependency_overrides[get_uow] = test_uow
    app.dependency_overrides[get_current_user] = lambda: s["users"][actor]
    base = f"http://test/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/"
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=base)


async def save_schedule(client, expected, proposed):
    return await client.put("slots", json={"expected_slots": expected, "slots": proposed})


@pytest.mark.parametrize("delete", [False, True])
async def test_schedule_reflows_with_stable_ids(seeded, delete):
    s = seeded
    day = START.replace(hour=14)
    async with client_for(s) as client:
        created = await client.post(
            "slots",
            json={
                "slots": [
                    {"starts_at": row["starts_at"], "ends_at": row["ends_at"]}
                    for row in (interval(day + timedelta(minutes=15 * index)) for index in range(25))
                ]
            },
        )
        assert created.status_code == 201
        before = snapshot(created.json())
        await self_register(s, slot_id=before[9]["id"])
        start = day.replace(hour=16, minute=0 if delete else 5)
        tail = before[9 if delete else 8 :]
        proposed = before[:8] + [
            interval(start + timedelta(minutes=15 * index), id=row["id"]) for index, row in enumerate(tail)
        ]
        saved = await save_schedule(client, before, proposed)
        assert saved.status_code == 200
        after = snapshot(saved.json())
        assert after[:8] == before[:8]
        assert after[8 if delete else 9]["starts_at"] == ("2026-11-30T16:00:00Z" if delete else "2026-11-30T16:20:00Z")
        assert after[-1]["ends_at"] == ("2026-11-30T20:00:00Z" if delete else "2026-11-30T20:20:00Z")
        assert [row["id"] for row in after[8:]] == [row["id"] for row in tail]
        assert (await client.get("slots")).json()["items"] == saved.json()
        registrations = (await client.get("registrations")).json()["items"]
        assert [row["slot_id"] for row in registrations] == [before[9]["id"]]
        assert (await save_schedule(client, before, proposed)).status_code == 409


async def test_break_is_visible_across_midnight_and_cannot_be_booked(seeded):
    s = seeded
    midnight = START.replace(hour=23, minute=55)
    async with client_for(s) as client:
        saved = await save_schedule(
            client,
            [],
            [
                interval(midnight - timedelta(minutes=15)),
                interval(midnight, 10, kind="break"),
                interval(midnight + timedelta(minutes=10)),
            ],
        )
        assert saved.status_code == 200
        first, pause, second = saved.json()
        assert pause["ends_at"] == "2026-12-01T00:05:00Z"
        assert pause["kind"] == "break"
        assert pause["is_available"] is False
        assert pause["can_edit"] and pause["can_delete"]
        with pytest.raises(BusinessLogicError) as error:
            await self_register(s, slot_id=pause["id"])
        assert error.value.detail["code"] == "slot_is_break"
        await self_register(s, slot_id=first["id"])
        assert second["is_available"]


async def test_break_counts_once_in_queue_forecast(seeded):
    s = seeded
    async with client_for(s) as client:
        saved = await save_schedule(
            client,
            [],
            [
                interval(START),
                interval(START + timedelta(minutes=15), 10, kind="break"),
                interval(START + timedelta(minutes=25)),
                interval(START + timedelta(minutes=40)),
            ],
        )
        assert saved.status_code == 200
        a, _, b, c = saved.json()
    await register(s, "manager", slot_id=a["id"])
    await register(s, "manager2", slot_id=b["id"])
    await register(s, "member", slot_id=c["id"])
    state = await read_eta(s)
    assert [item.eta_seconds for item in state.eta.items] == [0, 1500, 2400]


async def test_overlap_leaves_all_original_intervals_intact(seeded):
    s = seeded
    async with client_for(s) as client:
        first = await save_schedule(client, [], [interval(START), interval(START + timedelta(minutes=15))])
        assert first.status_code == 200
        before = snapshot(first.json())
        proposed = [interval(START, id=before[0]["id"]), interval(START + timedelta(minutes=10), id=before[1]["id"])]
        rejected = await save_schedule(client, before, proposed)
        assert rejected.status_code == 409
        assert snapshot((await client.get("slots")).json()["items"]) == before


async def test_early_started_defense_protects_even_future_slot(seeded):
    s = seeded
    async with client_for(s) as client:
        first = await save_schedule(client, [], [interval(START)])
        assert first.status_code == 200
        before = snapshot(first.json())
        registration = await register(s, "manager", slot_id=before[0]["id"])
        await start(s, registration, START - timedelta(minutes=5))
        fresh = (await client.get("slots")).json()["items"]
        assert not fresh[0]["can_edit"] and not fresh[0]["can_delete"]
        moved = await save_schedule(client, before, [interval(START + timedelta(minutes=5), id=before[0]["id"])])
        assert moved.status_code == 409
        assert snapshot((await client.get("slots")).json()["items"]) == before


@pytest.mark.parametrize("booking_wins", [True, False])
async def test_removal_and_booking_serialize_on_exam_lock(seeded, booking_wins):
    s = seeded
    args = s["workspace"], s["exams"][0]
    async with s["uow"]() as uow:
        original = await reg_service(uow).add_slots(
            *args,
            SlotBatchCreate(slots=[{"starts_at": START, "ends_at": START + timedelta(minutes=15)}]),
            s["users"]["teacher"],
        )
    slot = original[0]
    before = snapshot([slot.model_dump(mode="json")])
    entered = asyncio.Event()
    pids = []

    async def edit(uow):
        return await reg_service(uow).replace_slots(
            *args, SlotScheduleReplace(expected_slots=before, slots=[]), s["users"]["teacher"]
        )

    async def book(uow):
        return await reg_service(uow).create_self(
            *args, RegistrationCreate(project_id=s["projects"]["manager"], slot_id=slot.id), s["users"]["manager"]
        )

    async def second():
        try:
            async with s["uow"]() as uow:
                pids.append(await uow.session.scalar(text("SELECT pg_backend_pid()")))
                entered.set()
                return await (edit(uow) if booking_wins else book(uow))
        except BusinessLogicError as error:
            return error.detail["code"]
        except NotFoundError:
            return "slot_not_found"

    async with s["uow"]() as uow:
        await (book(uow) if booking_wins else edit(uow))
        task = asyncio.create_task(second())
        await asyncio.wait_for(entered.wait(), 5)
        try:
            await registration_cases.wait_until_blocked(s, pids[0])
        except BaseException:
            task.cancel()
            raise
    assert await asyncio.wait_for(task, 10) == ("slot_has_registrations" if booking_wins else "slot_not_found")
    assert await registration_cases.count(s, "exam_registration") == int(booking_wins)
    assert await registration_cases.count(s, "exam_slot") == int(booking_wins)


async def test_moving_and_removing_break_recomputes_forecast(seeded):
    s = seeded
    async with client_for(s) as client:
        created = await save_schedule(
            client,
            [],
            [
                interval(START),
                interval(START + timedelta(minutes=15), 10, kind="break"),
                interval(START + timedelta(minutes=25)),
            ],
        )
        assert created.status_code == 200
        a, pause, b = snapshot(created.json())
        await register(s, "manager", slot_id=a["id"])
        await register(s, "manager2", slot_id=b["id"])
        initial = await read_eta(s)
        assert [item.eta_seconds for item in initial.eta.items] == [0, 1500]

        moved = await save_schedule(
            client,
            [a, pause, b],
            [
                a,
                interval(START + timedelta(minutes=15), id=b["id"]),
                interval(START + timedelta(minutes=30), 10, id=pause["id"], kind="break"),
            ],
        )
        assert moved.status_code == 200
        after_move = await read_eta(s)
        assert [item.eta_seconds for item in after_move.eta.items] == [0, 900]
        assert after_move.queue_revision == initial.queue_revision + 1

        removed = await save_schedule(client, snapshot(moved.json()), snapshot(moved.json()[:2]))
        assert removed.status_code == 200
        assert [row["kind"] for row in removed.json()] == ["defense", "defense"]
        after_remove = await read_eta(s)
        assert [item.eta_seconds for item in after_remove.eta.items] == [0, 900]
        assert after_remove.queue_revision == after_move.queue_revision + 1


async def test_break_only_schedule_allows_slotless_registration(seeded):
    s = seeded
    async with client_for(s) as client:
        created = await save_schedule(client, [], [interval(START, 10, kind="break")])
        assert created.status_code == 200
        manager = await self_register(s)
        assert manager.slot_id is None
    during_break = await read_eta(s, START + timedelta(minutes=3))
    assert [item.eta_seconds for item in during_break.eta.items] == [420]
    after_break = await read_eta(s, START + timedelta(minutes=10))
    assert [item.eta_seconds for item in after_break.eta.items] == [0]


async def test_schedule_row_with_registration_event_cannot_be_removed_after_team_moves(seeded):
    s = seeded
    async with client_for(s) as client:
        created = await save_schedule(client, [], [interval(START), interval(START + timedelta(minutes=15))])
        assert created.status_code == 200
        before = snapshot(created.json())
        registration = await self_register(s, slot_id=before[0]["id"])
        response = await client.post(
            f"registrations/{registration.id}/move",
            json={
                "target_exam_id": s["exams"][0],
                "target_slot_id": before[1]["id"],
                "expected_version": registration.version,
                "reason": "Перенос",
            },
        )
        assert response.status_code == 200
        slots = (await client.get("slots")).json()["items"]
        assert slots[0]["is_available"] and slots[0]["can_edit"] and not slots[0]["can_delete"]
        rejected = await save_schedule(client, before, before[1:])
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "slot_has_registrations"


async def test_manager_cannot_replace_schedule(seeded):
    async with client_for(seeded, actor="manager") as client:
        response = await save_schedule(client, [], [interval(START)])
    assert response.status_code == 403


async def test_changing_team_slot_across_break_revises_forecast(seeded):
    s = seeded
    async with client_for(s) as client:
        response = await save_schedule(
            client,
            [],
            [
                interval(START),
                interval(START + timedelta(minutes=15)),
                interval(START + timedelta(minutes=30), 10, kind="break"),
                interval(START + timedelta(minutes=40)),
            ],
        )
        assert response.status_code == 200
        a, b, _, c = response.json()
        await register(s, "manager", slot_id=a["id"])
        team = await register(s, "manager2", slot_id=c["id"])
        before = await read_eta(s)
        assert [item.eta_seconds for item in before.eta.items] == [0, 1500]
        moved = await client.post(
            f"registrations/{team.id}/move",
            json={
                "target_exam_id": s["exams"][0],
                "target_slot_id": b["id"],
                "expected_version": team.version,
                "reason": "До перерыва",
            },
        )
        assert moved.status_code == 200
        after = await read_eta(s)
        assert [item.eta_seconds for item in after.eta.items] == [0, 900]
        assert after.queue_revision == before.queue_revision + 1


async def test_schedule_migration_preserves_legacy_booking(seeded, run_migrations):
    s = seeded
    async with client_for(s) as client:
        created = await save_schedule(client, [], [interval(START)])
        assert created.status_code == 200
        slot_id = created.json()[0]["id"]
        booking = await self_register(s, slot_id=slot_id)

        await s["engine"].dispose()
        run_migrations(s["url"], "downgrade", "d117a11b20a2")
        run_migrations(s["url"], "upgrade", "head")

        slots = (await client.get("slots")).json()["items"]
        assert [(slot["id"], slot["kind"], slot["is_available"]) for slot in slots] == [(slot_id, "defense", False)]
        registrations = (await client.get("registrations")).json()["items"]
        assert [(row["id"], row["slot_id"]) for row in registrations] == [(booking.id, slot_id)]


@pytest.mark.parametrize("move", [False, True])
async def test_stale_slot_time_cannot_book_retained_slot_id(seeded, move):
    s = seeded
    async with client_for(s) as organizer:
        initial = await save_schedule(organizer, [], [interval(START), interval(START + timedelta(minutes=15))])
        assert initial.status_code == 200
        first, target = snapshot(initial.json())
        old_interval = {key: target[key] for key in ("starts_at", "ends_at")}
        original_booking = await self_register(s, slot_id=first["id"]) if move else None
        moved = await save_schedule(
            organizer, [first, target], [first, interval(START + timedelta(minutes=20), id=target["id"])]
        )
        assert moved.status_code == 200

    if original_booking is not None:
        url = f"registrations/{original_booking.id}/self-move"
        body = {
            "expected_version": original_booking.version,
            "reason": "New time",
            "target_exam_id": s["exams"][0],
            "target_slot_id": target["id"],
        }
    else:
        url = "registrations/self"
        body = {"project_id": s["projects"]["manager"], "slot_id": target["id"]}
    async with client_for(s, actor="manager") as manager:
        rejected = await manager.post(url, json={**body, "expected_slot": old_interval})
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "slot_time_changed"
        fresh = moved.json()[1]
        assert fresh["id"] == target["id"]
        updated_interval = {key: fresh[key] for key in ("starts_at", "ends_at")}
        result = await manager.post(url, json={**body, "expected_slot": updated_interval})
        assert result.status_code == (200 if move else 201)
        data = result.json()["target"] if move else result.json()
        assert data["slot_id"] == target["id"]
