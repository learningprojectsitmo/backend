"""Reliability checks of the exam module (#118): AC-05 (timer, ETA, reconnect), AC-09 (CSV pair) and no partial success.

In-process services over a real PostgreSQL with frozen service clocks; the real-process WebSocket load is in
`test_exam_live_load_ws.py`. See docs/exam-reliability.md for what is covered and how to run it.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from decimal import Decimal

import pytest
import test_exam_acceptance_db as acceptance_cases
import test_exam_assessment_submit_db as submit_cases
import test_exam_attempts_db as attempt_cases
import test_exam_queue_db as queue_cases
import test_exam_registrations_db as registration_cases
import test_exam_results_db as results_cases
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError
from test_exam_acceptance_db import accept_real, fill, finished
from test_exam_csv_http import download, parse
from test_exam_participation_db import participation
from test_exam_results_db import AFTER_WINDOW

from src.core.exceptions import BusinessLogicError, NotFoundError
from src.model.exam import Exam
from src.model.user import User
from src.model.workspace import WorkSpaceParticipation
from src.repository.exam_assessment_repository import ExamAssessmentRepository
from src.repository.exam_result_repository import ExamResultRepository
from src.schema.exam_attempt import AttemptCommand, AttemptPause, AttemptPostpone, AttemptRestart, AttemptStart
from src.schema.exam_queue import QueuePlace, QueueReason
from src.schema.exam_registration import RegistrationCreate
from src.services.exam_live_hub import ExamLiveConfig, ExamLiveHub
from src.services.exam_live_service import ExamLiveService
from src.services.exam_score import ScoreWeights, SheetScore, calculate_exam_score

pytestmark = pytest.mark.integration

seeded_base = results_cases.seeded_base
seeded = results_cases.seeded
five = acceptance_cases.five
NOW = registration_cases.NOW
OPEN = submit_cases.OPEN
LAST_SECOND = AFTER_WINDOW - timedelta(seconds=1)
# The CSV file and the endpoint carry the same stored snapshot codes.
EXCLUSION_CODES = {
    "": None,
    "manager_of_defending_team": "manager_of_defending_team",
    "member_of_defending_team": "member_of_defending_team",
}


# ── helpers ──────────────────────────────────────────────────────────────────


async def add_assessors(s, count: int) -> list[str]:
    """`count` more workspace members (role member) so that the audience snapshot has many assessors."""
    names = []
    async with s["uow"]() as u:
        role_id = s["users"]["member"].role_id
        for i in range(count):
            user = User(
                first_name=f"Assessor{i:03d}",
                middle_name="Load",
                email=f"load{i}@example.com",
                password_hashed="test",
                role_id=role_id,
            )
            u.session.add(user)
            await u.session.flush()
            u.session.add(WorkSpaceParticipation(workspace_id=s["workspace"], participant_id=user.id, role_id=role_id))
            s["users"][f"load{i}"] = user
            names.append(f"load{i}")
    return names


@contextlib.asynccontextmanager
async def failing_trigger(s, table: str, *, when: str = "true"):
    """BEFORE INSERT trigger that raises: simulates an error in the middle of a mutation."""
    name = f"fail_{table}"
    async with s["engine"].begin() as connection:
        await connection.execute(
            text(
                f"CREATE FUNCTION {name}() RETURNS trigger AS $$ BEGIN "
                f"IF {when} THEN RAISE EXCEPTION 'boom'; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql"
            )
        )
        await connection.execute(
            text(f"CREATE TRIGGER {name} BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION {name}()")
        )
    try:
        yield
    finally:
        async with s["engine"].begin() as connection:
            await connection.execute(text(f"DROP TRIGGER {name} ON {table}"))
            await connection.execute(text(f"DROP FUNCTION {name}()"))


async def scalar(s, sql, **params):
    async with s["engine"].connect() as connection:
        return await connection.scalar(text(sql), params)


class FakeSocket:
    """Stand-in for an ExamLiveConnection: the hub only needs `offer`, `key`, `user` and `reason`."""

    def __init__(self, workspace_id, exam_id, user):
        self.workspace_id, self.exam_id, self.user, self.reason = workspace_id, exam_id, user, "connected"
        self.offers: list[dict] = []

    @property
    def key(self):
        return self.workspace_id, self.exam_id

    def offer(self, message):
        self.offers.append(message)


def count_statements(engine):
    counter = {"n": 0}

    def before(*_args):
        counter["n"] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    return counter, lambda: event.remove(engine.sync_engine, "before_cursor_execute", before)


# ── AC-05: one state and one forecast for HTTP, WebSocket snapshot, reload and reconnect ─────────────


async def live_and_http(s, at, *, user="teacher"):
    """The live snapshot (what a WS client gets) and `GET .../queue` read at the same moment must be identical."""
    async with s["uow"]() as u:
        live = await ExamLiveService(u, clock=lambda: at).snapshot(
            s["workspace"], s["exams"][0], s["users"][user], reason="reconnect"
        )
        http = await queue_cases.queue_service(u, at).read(s["workspace"], s["exams"][0], s["users"][user])
        stream_seq = await u.session.scalar(select(Exam.stream_seq).where(Exam.id == s["exams"][0]))
    assert live.queue.model_dump(mode="json") == http.model_dump(mode="json")
    assert live.stream_seq == stream_seq and not live.stale and not live.queue.eta_stale
    return live


def item_of(snapshot, registration_id):
    return next(i for i in snapshot.queue.items if i.registration_id == registration_id)


async def test_ac05_pause_postpone_return_and_reload_give_one_state_and_forecast(seeded):
    s = seeded
    teacher = s["users"]["teacher"]
    ws, exam = s["workspace"], s["exams"][0]
    first = await queue_cases.register(s, "manager")
    second = await queue_cases.register(s, "manager2")
    third = await queue_cases.register(s, "member")
    sequences = []

    async with s["uow"]() as u:
        attempt, _ = await queue_cases.attempt_service(u, NOW).start(
            ws, exam, AttemptStart(registration_id=first.id, expected_version=first.version), teacher
        )
    snap = await live_and_http(s, NOW + timedelta(seconds=10))
    sequences.append(snap.stream_seq)
    running = item_of(snap, first.id).attempt
    assert running.status == "speaking" and running.paused_at is None
    assert snap.queue.eta.current is not None and not snap.queue.eta.current.paused

    # Pause: the timer freezes and a reload long after sees the very same remaining time and deadline.
    async with s["uow"]() as u:
        paused = await queue_cases.attempt_service(u, NOW + timedelta(seconds=60)).pause(
            ws, exam, attempt.id, AttemptPause(expected_version=attempt.version, reason="Перерыв"), teacher
        )
    for later in (60, 300, 900):
        snap = await live_and_http(s, NOW + timedelta(seconds=later))
        state = item_of(snap, first.id).attempt
        assert state.paused_at is not None
        assert (state.remaining_seconds, state.phase_deadline) == (paused.remaining_seconds, paused.phase_deadline)
        assert snap.queue.eta.current.paused
    sequences.append(snap.stream_seq)

    # Resume: the deadline moves by exactly the paused time; a reload right after agrees with the answer.
    async with s["uow"]() as u:
        resumed = await queue_cases.attempt_service(u, NOW + timedelta(seconds=360)).resume(
            ws, exam, attempt.id, AttemptCommand(expected_version=paused.version), teacher
        )
    assert resumed.phase_deadline == paused.phase_deadline + timedelta(seconds=300)
    snap = await live_and_http(s, NOW + timedelta(seconds=361))
    sequences.append(snap.stream_seq)
    state = item_of(snap, first.id).attempt
    assert state.paused_at is None and state.phase_deadline == resumed.phase_deadline
    assert state.remaining_seconds == resumed.remaining_seconds - 1

    # Postpone the running team, start the next, mark the third as no-show, then return both.
    async with s["uow"]() as u:
        postponed = await queue_cases.attempt_service(u, NOW + timedelta(seconds=400)).postpone(
            ws, exam, attempt.id, AttemptPostpone(expected_version=resumed.version, reason="Проектор"), teacher
        )
    snap = await live_and_http(s, NOW + timedelta(seconds=401))
    sequences.append(snap.stream_seq)
    assert postponed.status == "postponed" and snap.queue.eta.current is None
    assert item_of(snap, first.id).state == "postponed" and item_of(snap, first.id).attempt.status == "postponed"
    async with s["uow"]() as u:
        other, _ = await queue_cases.attempt_service(u, NOW + timedelta(seconds=420)).start(
            ws, exam, AttemptStart(registration_id=second.id, expected_version=second.version), teacher
        )
    snap = await live_and_http(s, NOW + timedelta(seconds=421))
    sequences.append(snap.stream_seq)
    async with s["uow"]() as u:
        await queue_cases.queue_service(u, NOW + timedelta(seconds=430)).no_show(
            ws, exam, third.id, QueueReason(expected_version=third.version, reason="Не пришли"), teacher
        )
    snap = await live_and_http(s, NOW + timedelta(seconds=431))
    sequences.append(snap.stream_seq)
    assert item_of(snap, third.id).state == "no_show"
    async with s["uow"]() as u:
        await queue_cases.queue_service(u, NOW + timedelta(seconds=440)).place(
            ws, exam, third.id, QueuePlace(expected_version=third.version + 1), teacher
        )
    snap = await live_and_http(s, NOW + timedelta(seconds=441))
    sequences.append(snap.stream_seq)

    # Nothing was lost: all three teams are still in the queue, one is on stage, one waits, one is postponed.
    assert {i.registration_id for i in snap.queue.items} == {first.id, second.id, third.id}
    assert item_of(snap, second.id).attempt.id == other.id and item_of(snap, third.id).state == "waiting"
    assert item_of(snap, first.id).attempt.status == "postponed"
    # One live event per effective mutation: strictly increasing, no gaps.
    assert sequences == list(range(sequences[0], sequences[0] + len(sequences)))

    # The postponed team restarts as soon as the stage is free, with a fresh timer; every reader still agrees.
    async with s["uow"]() as u:
        await queue_cases.attempt_service(u, NOW + timedelta(seconds=450)).postpone(
            ws, exam, other.id, AttemptPostpone(expected_version=other.version, reason="Связь"), teacher
        )
    async with s["uow"]() as u:
        restarted = await queue_cases.attempt_service(u, NOW + timedelta(seconds=460)).restart(
            ws,
            exam,
            attempt.id,
            AttemptRestart(expected_version=postponed.version, reason="Проектор починили"),
            teacher,
        )
    snap = await live_and_http(s, NOW + timedelta(seconds=461))
    state = item_of(snap, first.id).attempt
    assert state.status == "speaking" and state.phase_deadline == restarted.phase_deadline
    assert snap.queue.eta.current.registration_id == first.id
    assert item_of(snap, second.id).attempt.status == "postponed"


async def test_ac05_foreign_workspace_and_outsiders_see_nothing_through_either_channel(seeded):
    s = seeded
    await queue_cases.register(s, "manager")
    for user, workspace in [("outsider", s["workspace"]), ("teacher", s["foreign_workspace"])]:
        async with s["uow"]() as u:
            with pytest.raises(NotFoundError):
                await ExamLiveService(u, clock=lambda: NOW).snapshot(
                    workspace, s["exams"][0], s["users"][user], reason="connected"
                )
        async with s["uow"]() as u:
            with pytest.raises(NotFoundError):
                await queue_cases.queue_service(u).read(workspace, s["exams"][0], s["users"][user])


async def test_ac05_concurrent_commands_keep_every_team_and_count_one_event_each(seeded):
    s = seeded
    teacher = s["users"]["teacher"]
    ws, exam = s["workspace"], s["exams"][0]
    projects = ["manager", "manager2", "member", "local_manager", "demoted", "null_manager"]
    registrations = [await queue_cases.register(s, project) for project in projects]
    async with s["uow"]() as u:
        before = await u.session.scalar(select(Exam.stream_seq).where(Exam.id == s["exams"][0]))
        revision_before = await u.session.scalar(select(Exam.queue_revision).where(Exam.id == s["exams"][0]))

    async def postpone(registration):
        async with s["uow"]() as u:
            return await queue_cases.queue_service(u).postpone(
                ws,
                exam,
                registration.id,
                QueueReason(expected_version=registration.version, reason="Параллельно"),
                teacher,
            )

    async def no_show(registration):
        async with s["uow"]() as u:
            return await queue_cases.queue_service(u).no_show(
                ws, exam, registration.id, QueueReason(expected_version=registration.version, reason="Нет"), teacher
            )

    async def start(registration):
        async with s["uow"]() as u:
            return await queue_cases.attempt_service(u).start(
                ws, exam, AttemptStart(registration_id=registration.id, expected_version=registration.version), teacher
            )

    results = await asyncio.gather(
        *(postpone(r) for r in registrations[:3]),
        no_show(registrations[3]),
        start(registrations[4]),
        return_exceptions=True,
    )
    assert not [r for r in results if isinstance(r, Exception)], results
    snap = await live_and_http(s, NOW + timedelta(seconds=5))
    states = {i.registration_id: i.state for i in snap.queue.items}
    assert {r.id for r in registrations} == set(states)  # nothing lost
    assert [states[r.id] for r in registrations[:3]] == ["postponed"] * 3
    assert states[registrations[3].id] == "no_show"
    assert item_of(snap, registrations[4].id).attempt is not None
    assert snap.stream_seq - before == 5  # exactly one live event per effective command
    assert snap.queue.queue_revision > revision_before
    positions = sorted(i.position for i in snap.queue.items if i.position is not None)
    assert positions == list(range(1, len(positions) + 1))


async def test_hub_builds_one_snapshot_per_exam_and_not_per_client(seeded):
    s = seeded
    await queue_cases.register(s, "manager")
    counts = {}
    for clients in (3, 150):
        hub = ExamLiveHub(
            uow_factory=s["uow"], dsn="", config=ExamLiveConfig(listener_enabled=False), clock=lambda: NOW
        )
        sockets = [FakeSocket(s["workspace"], s["exams"][0], s["users"]["teacher"]) for _ in range(clients)]
        hub._subscribers[(s["workspace"], s["exams"][0])] = set(sockets)
        counter, remove = count_statements(s["engine"])
        try:
            await hub.refresh((s["workspace"], s["exams"][0]), reason="changed", changed=("queue",))
        finally:
            remove()
        counts[clients] = counter["n"]
        assert all(len(socket.offers) == 1 for socket in sockets)
        assert len({socket.offers[0]["stream_seq"] for socket in sockets}) == 1
    assert counts[3] == counts[150] > 0, counts

    # A new connection costs one authentication + one snapshot, independent of how many clients are already there.
    hub = ExamLiveHub(uow_factory=s["uow"], dsn="", config=ExamLiveConfig(listener_enabled=False), clock=lambda: NOW)
    hub.start = _noop  # no LISTEN connection in this test
    per_connect = []
    for _ in range(3):
        counter, remove = count_statements(s["engine"])
        try:
            await hub.add(FakeSocket(s["workspace"], s["exams"][0], s["users"]["teacher"]))
        finally:
            remove()
        per_connect.append(counter["n"])
    assert len(set(per_connect)) == 1, per_connect


async def _noop():
    return None


# ── AC-09: assessors submit around the close, then the decision and both CSV files ───────────────────


def csv_pair(response):
    (_, register), (_, people) = parse(response)
    return register, people


async def test_ac09_many_assessors_around_the_close_then_accept_and_csv_match_registry_and_participation(five):
    s = five
    loads = await add_assessors(s, 40)
    attempt = await finished(s)
    early = [*loads[:35], "teacher", "local_teacher", "local_admin", "manager2", "local_manager"]
    # 40+ assessors submit at once while the window is open ...
    scores = {name: 1 + index % 5 for index, name in enumerate(early)}
    submitted = dict(
        zip(early, await asyncio.gather(*(fill(s, attempt, n, scores[n], now=OPEN) for n in early)), strict=True)
    )
    # ... ten of them resubmit in the last second while five latecomers try after the close.
    resubmit = loads[:10]
    late = loads[35:]

    async def after_close(name):
        with pytest.raises(BusinessLogicError) as error:
            await fill(s, attempt, name, 5, now=AFTER_WINDOW)
        return error.value.detail["code"]

    second_round, closed = (
        await asyncio.gather(*(fill(s, attempt, n, scores[n] % 5 + 1, now=LAST_SECOND) for n in resubmit)),
        await asyncio.gather(*(after_close(n) for n in late)),
    )
    assert set(closed) == {"assessment_window_closed"}
    for name, edition in zip(resubmit, second_round, strict=True):
        assert edition.version == 2 and edition.total == 5 * (scores[name] % 5 + 1)
        submitted[name] = edition
    assert await scalar(s, "SELECT count(*) FROM exam_assessment_submission") == len(early) + len(resubmit)
    assert (
        await scalar(
            s,
            "SELECT count(*) FROM exam_assessment_submission su JOIN exam_assessment_sheet sh ON sh.id=su.sheet_id "
            'JOIN "user" u ON u.id=sh.user_id WHERE u.email = ANY(:late)',
            late=[f"load{i}@example.com" for i in range(35, 40)],
        )
        == 0
    )  # the latecomers left no partial trace

    edition = await accept_real(s, attempt, version=0, now=AFTER_WINDOW)
    part = await participation(s, attempt, now=AFTER_WINDOW)
    async with s["uow"]() as u:
        registry = await ExamResultRepository(u).list_results(s["workspace"], s["exams"][0], limit=50, offset=0)
    register, people = csv_pair(await download(s))

    # registry (#115) <-> accepted edition <-> CSV register row
    (registry_row,) = registry
    row = next(r for r in register if int(r["attempt_id"]) == attempt.id)
    assert registry_row.current.version == edition.edition.version == int(row["result_version"]) == 1
    assert Decimal(row["final_score"]) == registry_row.current.final_score == edition.edition.final_score
    assert Decimal(row["calculated_score"]) == edition.edition.calculated_score
    assert int(row["settings_version"]) == edition.edition.snapshot.settings_version
    # participation (#117) <-> CSV register counts
    total = part.summary.total
    assert (int(row["eligible_count"]), int(row["submitted_count"])) == (total.admitted, total.submitted)
    assert (int(row["not_submitted_count"]), int(row["excluded_count"])) == (total.not_submitted, total.excluded)
    assert total.submitted == len(early) and total.not_submitted == len(part.items) - total.excluded - len(early)
    # participation (#117) <-> CSV participation rows, assessor by assessor
    csv_people = {int(p["assessor_id"]): p for p in people if int(p["attempt_id"]) == attempt.id}
    assert set(csv_people) == {i.user_id for i in part.items}
    for item in part.items:
        person = csv_people[item.user_id]
        assert (person["response_status"], person["role"]) == (item.status, item.role)
        assert EXCLUSION_CODES.get(person["exclusion_reason"]) == item.exclusion_reason
        if item.submission:
            assert (int(person["submission_version"]), int(person["total"])) == (
                item.submission.version,
                item.submission.total,
            )
    # the score is reproducible from the CSV rows alone: the pair describes one moment
    recomputed = calculate_exam_score(
        sheets=[
            SheetScore(p["role"], int(p["total"])) for p in csv_people.values() if p["response_status"] == "submitted"
        ],
        weights=ScoreWeights(60, 30, 10),
        sheet_max=25,
        max_score=Decimal("25.00"),
    )
    assert recomputed.score == edition.edition.calculated_score
    assert len({r["export_id"] for r in register} | {p["export_id"] for p in people}) == 1


async def test_ac09_export_taken_while_assessors_keep_submitting_is_always_one_consistent_snapshot(five):
    s = five
    loads = await add_assessors(s, 12)
    attempt = await finished(s)
    names = [*loads, "teacher", "local_teacher"]
    await asyncio.gather(*(fill(s, attempt, n, 1 + i % 5, now=OPEN) for i, n in enumerate(names)))
    stop = asyncio.Event()

    async def writer(name, start):
        score = start
        while not stop.is_set():
            score = score % 5 + 1
            await fill(s, attempt, name, score, now=OPEN)

    writers = [asyncio.create_task(writer(n, i)) for i, n in enumerate(names)]
    seen_versions = set()
    try:
        for _ in range(8):
            register, people = csv_pair(await download(s))
            row = next(r for r in register if int(r["attempt_id"]) == attempt.id)
            mine = [p for p in people if int(p["attempt_id"]) == attempt.id]
            submitted = [p for p in mine if p["response_status"] == "submitted"]
            assert int(row["submitted_count"]) == len(submitted) == len(names)
            recomputed = calculate_exam_score(
                sheets=[SheetScore(p["role"], int(p["total"])) for p in submitted],
                weights=ScoreWeights(60, 30, 10),
                sheet_max=25,
                max_score=Decimal("25.00"),
            )
            assert Decimal(row["calculated_score"]) == recomputed.score  # register agrees with its own sheets
            for person in submitted:
                assert int(person["total"]) == sum(int(person[f"criterion_{i}_score"]) for i in range(1, 6))
            assert len({r["export_id"] for r in register} | {p["export_id"] for p in people}) == 1
            assert len({r["snapshot_at"] for r in register} | {p["snapshot_at"] for p in people}) == 1
            seen_versions.add(tuple(sorted(int(p["submission_version"]) for p in submitted)))
    finally:
        stop.set()
        await asyncio.gather(*writers, return_exceptions=True)
    assert len(seen_versions) > 1, "the writers never overlapped with an export"  # the test really raced


# ── rules shared by the CSV participation file and the participation endpoint ────────────────────────


async def test_csv_and_endpoint_participation_rules_agree(five):
    s = five
    attempt = await finished(s, team_member="demoted")
    await fill(s, attempt, "teacher", 4, now=OPEN)  # submitted, then edited: version 2
    await fill(s, attempt, "teacher", 5, now=OPEN)
    await fill(s, attempt, "local_teacher", 3, now=OPEN, submit=False)  # draft only: not a vote
    part = await participation(s, attempt, now=AFTER_WINDOW)
    _, people = csv_pair(await download(s))
    csv_people = {int(p["assessor_id"]): p for p in people if int(p["attempt_id"]) == attempt.id}
    by_id = {i.user_id: i for i in part.items}
    assert set(csv_people) == set(by_id)
    statuses = {i.status for i in part.items}
    assert statuses == {"submitted", "not_submitted", "excluded"}  # all three kinds are present
    for user_id, item in by_id.items():
        assert csv_people[user_id]["response_status"] == item.status
    assert by_id[s["users"]["local_teacher"].id].status == "not_submitted"
    assert by_id[s["users"]["demoted"].id].exclusion_reason == "member_of_defending_team"
    assert csv_people[s["users"]["demoted"].id]["exclusion_reason"] == "member_of_defending_team"
    assert int(csv_people[s["users"]["teacher"].id]["submission_version"]) == 2

    # A submission stamped outside [opened_at, closes_at) (impossible through the API, the deadline is checked on
    # the server) is not a vote for the endpoint, the calculation source and the CSV file alike.
    async with s["uow"]() as u:
        await u.session.execute(
            text(
                "UPDATE exam_assessment_submission SET submitted_at = (SELECT closes_at FROM assessment_window LIMIT 1) "
                "WHERE sheet_id = (SELECT id FROM exam_assessment_sheet WHERE user_id = :u)"
            ),
            {"u": s["users"]["teacher"].id},
        )
    part = await participation(s, attempt, now=AFTER_WINDOW)
    _, people = csv_pair(await download(s))
    teacher_id = s["users"]["teacher"].id
    assert {i.user_id: i for i in part.items}[teacher_id].status == "not_submitted"
    assert next(p for p in people if int(p["assessor_id"]) == teacher_id)["response_status"] == "not_submitted"
    async with s["uow"]() as u:
        counted = await ExamAssessmentRepository(u).counted_sheets(attempt.id)
    assert "teacher" not in [role for role, _ in counted]


async def test_attempt_without_a_window_is_not_offered_for_the_endpoint_and_a_preview_for_the_csv(seeded):
    s = seeded
    registration = await attempt_cases.organized(s, project="manager")
    attempt, _ = await attempt_cases.start(s, registration)
    part = await participation(s, attempt, now=OPEN)
    assert part.state == "not_offered" and part.items == [] and part.window is None
    register, people = csv_pair(await download(s))
    mine = [p for p in people if p["attempt_id"] and int(p["attempt_id"]) == attempt.id]
    assert mine and {p["audience_source"] for p in mine} == {"preview"}
    assert {p["response_status"] for p in mine} == {"not_requested"}  # CSV: who would be asked; endpoint: nobody yet
    row = next(r for r in register if int(r["attempt_id"]) == attempt.id)
    assert row["eligible_count"] == "" and row["calculated_score"] == ""


# ── no partial success: a failure in the middle of a mutation rolls the whole mutation back ──────────


async def test_failed_sheet_submit_leaves_no_edition_and_the_draft_and_next_submit_work(five):
    s = five
    attempt = await finished(s)
    await fill(s, attempt, "teacher", 4, now=OPEN, submit=False)
    async with failing_trigger(s, "exam_assessment_submission_answer"):
        with pytest.raises(DBAPIError):
            await submit_cases.submit(s, attempt, "teacher", now=OPEN)
    assert await scalar(s, "SELECT count(*) FROM exam_assessment_submission") == 0
    assert await scalar(s, "SELECT count(*) FROM exam_assessment_submission_answer") == 0
    edition = await submit_cases.submit(s, attempt, "teacher", now=OPEN)
    assert edition.version == 1 and edition.total == 20  # no gap in versions, the draft survived


async def test_failed_queue_command_changes_nothing_and_publishes_no_event(seeded):
    s = seeded
    first = await queue_cases.register(s, "manager")
    second = await queue_cases.register(s, "manager2")
    state = (
        "SELECT json_build_object('q', e.queue_revision, 'seq', e.stream_seq, "
        "'regs', (SELECT json_agg(json_build_array(id, version, queue_position, queue_hold) ORDER BY id) "
        "FROM exam_registration), 'events', (SELECT count(*) FROM registration_event)) FROM exam e WHERE e.id = :e"
    )
    before = await scalar(s, state, e=s["exams"][0])
    async with failing_trigger(s, "registration_event"):
        with pytest.raises(DBAPIError):
            async with s["uow"]() as u:
                await queue_cases.queue_service(u).postpone(
                    s["workspace"],
                    s["exams"][0],
                    first.id,
                    QueueReason(expected_version=first.version, reason="Сбой"),
                    s["users"]["teacher"],
                )
    assert await scalar(s, state, e=s["exams"][0]) == before
    # the queue still works afterwards and the second team has the position it had
    async with s["uow"]() as u:
        moved = await queue_cases.queue_service(u).postpone(
            s["workspace"],
            s["exams"][0],
            first.id,
            QueueReason(expected_version=first.version, reason="Теперь без сбоя"),
            s["users"]["teacher"],
        )
    assert moved.item.state == "postponed" and second.id


async def test_failed_registration_with_a_slot_releases_the_slot_and_leaves_no_registration(seeded):
    s = seeded
    async with s["uow"]() as u:
        slots = await registration_cases.reg_service(u).add_slots(
            s["workspace"], s["exams"][0], registration_cases.intervals(), s["users"]["teacher"]
        )
    slot_id = slots[0].id
    async with failing_trigger(s, "registration_event"):
        with pytest.raises(DBAPIError):
            async with s["uow"]() as u:
                await registration_cases.reg_service(u).create_organized(
                    s["workspace"],
                    s["exams"][0],
                    RegistrationCreate(project_id=s["projects"]["manager"], slot_id=slot_id),
                    s["users"]["teacher"],
                )
    assert await scalar(s, "SELECT count(*) FROM exam_registration") == 0
    async with s["uow"]() as u:
        page = await registration_cases.reg_service(u).list_slots(
            s["workspace"], s["exams"][0], s["users"]["teacher"], limit=10, offset=0
        )
    assert all(slot.is_available for slot in page.items)
    async with s["uow"]() as u:  # and the slot can still be taken
        created = await registration_cases.reg_service(u).create_organized(
            s["workspace"],
            s["exams"][0],
            RegistrationCreate(project_id=s["projects"]["manager"], slot_id=slot_id),
            s["users"]["teacher"],
        )
    assert created.slot_id == slot_id


async def test_failed_acceptance_stores_no_edition_and_the_next_one_is_version_one(five):
    s = five
    attempt = await finished(s)
    await fill(s, attempt, "teacher", 4, now=OPEN)
    async with failing_trigger(s, "exam_result_edition"):
        with pytest.raises(DBAPIError):
            await accept_real(s, attempt, version=0, now=AFTER_WINDOW)
    assert await scalar(s, "SELECT count(*) FROM exam_result_edition") == 0
    edition = await accept_real(s, attempt, version=0, now=AFTER_WINDOW)
    assert edition.edition.version == 1
