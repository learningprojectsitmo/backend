from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
import test_exam_manual_result_db as manual_cases
import test_exam_results_db as results_cases
from sqlalchemy import event, text
from test_exam_attempts_db import NOW, attempt_service, organized, set_settings, start
from test_exam_results_db import AFTER_WINDOW, accept, finished_attempt, publish, result_service, set_participation

from src.core.exceptions import NotFoundError, PermissionError
from src.repository.exam_result_repository import ExamResultRepository
from src.schema.exam import ExamWeights
from src.schema.exam_attempt import AttemptCommand

pytestmark = pytest.mark.integration

# Fixtures are shared with the result tests.
seeded_base = results_cases.seeded_base
seeded = results_cases.seeded


async def registry(s, *, actor="teacher", exam=0, q=None, state=None, limit=50, offset=0, workspace=None):
    async with s["uow"]() as u:
        return await result_service(u).registry(
            s["workspace"] if workspace is None else workspace,
            s["exams"][exam],
            s["users"][actor],
            q=q,
            state=state,
            limit=limit,
            offset=offset,
        )


def names(page):
    return [item.project_name for item in page.items]


async def finish_in_exam(s, attempt, exam):
    async with s["uow"]() as u:
        await attempt_service(u, NOW + timedelta(minutes=10)).finish(
            s["workspace"], s["exams"][exam], attempt.id, AttemptCommand(expected_version=1), s["users"]["teacher"]
        )


async def test_rows_cover_states_versions_and_previous_values(seeded):
    s = seeded
    undecided = await finished_attempt(s, project="manager")
    calculated = await finished_attempt(s, project="manager2")
    manual = await finished_attempt(s, project="member")
    published = await finished_attempt(s, project="local_manager")
    await accept(s, calculated)
    await accept(s, manual)
    await manual_cases.manual(s, manual, "17.5", version=1)
    await accept(s, published)
    await publish(s, published)

    page = await registry(s)
    by_project = {item.project_name: item for item in page.items}
    assert (page.limit, page.offset, page.has_more) == (50, 0, False)
    assert [item.attempt_id for item in page.items] == [undecided.id, calculated.id, manual.id, published.id]

    first = by_project["Project manager"]
    assert (first.state, first.editions_count, first.current, first.previous_final_score) == (
        "undecided",
        0,
        None,
        None,
    )
    assert first.settings_outdated is False

    second = by_project["Project manager2"]
    assert (second.state, second.editions_count, second.previous_final_score) == ("accepted", 1, None)
    assert second.current.kind == "calculated" and second.current.final_score == Decimal("19.00")
    assert second.current.decided_by_id == s["users"]["teacher"].id and second.current.decided_by_name == "teacher"
    assert second.current.max_score == Decimal("25.00") and second.current.published_at is None

    third = by_project["Project member"]
    assert (third.state, third.editions_count) == ("accepted", 2)
    assert third.current.version == 2 and third.current.kind == "manual"
    assert third.current.final_score == Decimal("17.50") and third.current.calculated_score == Decimal("19.00")
    assert third.current.reason == "Устная защита" and third.previous_final_score == Decimal("19.00")

    fourth = by_project["Project local_manager"]
    assert fourth.state == "published" and fourth.current.published_by_id == s["users"]["teacher"].id
    assert fourth.current.published_at == AFTER_WINDOW


async def test_unfinished_attempts_and_registrations_are_not_listed(seeded):
    s = seeded
    done = await finished_attempt(s, project="manager")
    running_registration = await organized(s, project="manager2")
    await start(s, running_registration)
    await organized(s, project="member")  # registration without an attempt
    page = await registry(s)
    assert [item.attempt_id for item in page.items] == [done.id]


async def test_search_is_case_insensitive_literal_and_handles_cyrillic_and_wildcards(seeded):
    s = seeded
    for project in ["manager", "manager2", "member"]:
        await finished_attempt(s, project=project)
    async with s["uow"]() as u:
        for name, project in [("Алгоритмы 100%", "manager"), ("Data_Team", "manager2"), ("DataXTeam", "member")]:
            await u.session.execute(
                text("UPDATE project SET name = :n WHERE id = :i"), {"n": name, "i": s["projects"][project]}
            )
    assert names(await registry(s, q="алгоритмы")) == ["Алгоритмы 100%"]
    assert names(await registry(s, q="АЛГОР")) == ["Алгоритмы 100%"]
    assert names(await registry(s, q="100%")) == ["Алгоритмы 100%"]
    assert names(await registry(s, q="%")) == ["Алгоритмы 100%"]  # '%' is literal, not a wildcard
    assert names(await registry(s, q="data_team")) == ["Data_Team"]  # '_' does not match 'X'
    assert sorted(names(await registry(s, q="DATA"))) == ["DataXTeam", "Data_Team"]
    assert names(await registry(s, q="нет такого")) == []
    assert len((await registry(s, q="   ")).items) == 3  # blank search is no filter
    assert names(await registry(s, q="\\")) == []


async def test_state_filters(seeded):
    s = seeded
    undecided = await finished_attempt(s, project="manager")
    accepted = await finished_attempt(s, project="manager2")
    published = await finished_attempt(s, project="member")
    await accept(s, accepted)
    await accept(s, published)
    await publish(s, published)
    assert [i.attempt_id for i in (await registry(s, state="undecided")).items] == [undecided.id]
    assert [i.attempt_id for i in (await registry(s, state="accepted")).items] == [accepted.id]
    assert [i.attempt_id for i in (await registry(s, state="published")).items] == [published.id]
    both = await registry(s, state="accepted", q="manager2")
    assert [i.attempt_id for i in both.items] == [accepted.id]
    assert (await registry(s, state="published", q="manager2")).items == []


async def test_pagination_has_more_and_deterministic_order(seeded):
    s = seeded
    attempts = [await finished_attempt(s, project=p) for p in ["manager", "manager2", "member", "local_manager"]]
    ids = [a.id for a in attempts]
    first = await registry(s, limit=3)
    assert [i.attempt_id for i in first.items] == ids[:3] and first.has_more is True
    rest = await registry(s, limit=3, offset=3)
    assert [i.attempt_id for i in rest.items] == ids[3:] and rest.has_more is False
    exact = await registry(s, limit=4)
    assert len(exact.items) == 4 and exact.has_more is False
    assert (await registry(s, limit=2, offset=10)).items == []
    # started_at is the primary key of the order, the id only breaks ties.
    async with s["uow"]() as u:
        await u.session.execute(
            text("UPDATE exam_attempt SET started_at = started_at - interval '1 hour' WHERE id = :i"), {"i": ids[-1]}
        )
    assert [i.attempt_id for i in (await registry(s)).items] == [ids[-1], *ids[:-1]]


async def test_isolation_by_exam_and_workspace(seeded):
    s = seeded
    mine = await finished_attempt(s, project="manager")
    other_registration = await organized(s, project="manager2", exam=1)
    other, _ = await start(s, other_registration, exam=1)
    await finish_in_exam(s, other, 1)
    await accept(s, mine)
    first = await registry(s, exam=0)
    second = await registry(s, exam=1)
    assert [i.attempt_id for i in first.items] == [mine.id]
    assert [i.attempt_id for i in second.items] == [other.id]
    assert second.items[0].state == "undecided"
    async with s["uow"]() as u:
        rows = await ExamResultRepository(u).list_results(s["foreign_workspace"], s["exams"][0], limit=10, offset=0)
    assert rows == []


async def test_settings_outdated_follows_current_settings_revision(seeded):
    s = seeded
    attempt = await finished_attempt(s, project="manager")
    other = await finished_attempt(s, project="manager2")
    await accept(s, attempt)
    assert [i.settings_outdated for i in (await registry(s)).items] == [False, False]
    await set_settings(s, weights=ExamWeights(teacher=20, manager=40, member=40))
    page = await registry(s)
    assert [i.settings_outdated for i in page.items] == [True, False]  # undecided is never outdated
    await accept(s, attempt, version=1, reason="Новые веса")
    assert (await registry(s)).items[0].settings_outdated is False
    await set_settings(s, expected_version=2, max_score=Decimal("50.00"))
    assert (await registry(s)).items[0].settings_outdated is True
    assert other.id == (await registry(s)).items[1].attempt_id


async def test_roles_are_checked_through_workspace_teacher(seeded):
    s = seeded
    await finished_attempt(s, project="manager")
    assert len((await registry(s, actor="teacher")).items) == 1
    assert len((await registry(s, actor="local_teacher")).items) == 1
    assert len((await registry(s, actor="local_admin")).items) == 1
    for actor in ["manager", "member", "local_manager", "demoted"]:
        with pytest.raises(PermissionError):
            await registry(s, actor=actor)
    with pytest.raises(PermissionError):
        await registry(s, actor="admin")  # global admin who does not participate in the workspace
    with pytest.raises(NotFoundError):
        await registry(s, actor="outsider")  # no access to the workspace at all: 404 before the role check
    await set_participation(s, "teacher", local="member")  # local member overrides the global teacher role
    with pytest.raises(PermissionError):
        await registry(s)


async def test_query_count_does_not_grow_with_attempts(seeded):
    s = seeded
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    async def measure() -> tuple[int, int]:
        statements.clear()
        async with s["uow"]() as u:
            rows = await ExamResultRepository(u).list_results(s["workspace"], s["exams"][0], limit=50, offset=0)
        return len(statements), len(rows)

    event.listen(s["engine"].sync_engine, "before_cursor_execute", record)
    try:
        for project in ["manager", "manager2"]:
            attempt = await finished_attempt(s, project=project)
            await accept(s, attempt)
        small_queries, small_rows = await measure()
        for project in ["member", "local_manager", "demoted"]:
            attempt = await finished_attempt(s, project=project)
            await accept(s, attempt)
        large_queries, large_rows = await measure()
    finally:
        event.remove(s["engine"].sync_engine, "before_cursor_execute", record)
    assert (small_rows, large_rows) == (2, 5)
    assert small_queries == large_queries == 1
