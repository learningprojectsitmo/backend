from __future__ import annotations

from datetime import timedelta

import pytest
import test_exam_registrations_db as registration_cases
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from test_exam_registrations_db import NOW, count, reg_service

from src.model.exam_attempt import AssessmentWindowAudience
from src.model.project import Project, ProjectParticipation
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_registration_repository import ExamRegistrationRepository
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam_attempt import AttemptCommand, AttemptStart
from src.schema.exam_registration import RegistrationCreate
from src.services.exam_attempt_service import ExamAttemptService
from src.services.exam_queue_service import ExamQueueService
from src.services.exam_service import ExamService

pytestmark = pytest.mark.integration
seeded = registration_cases.seeded


async def _organized(s, project="manager", now=NOW):
    async with s["uow"]() as u:
        return await reg_service(u, now).create_organized(
            s["workspace"],
            s["exams"][0],
            RegistrationCreate(project_id=s["projects"][project]),
            s["users"]["teacher"],
        )


async def _start(s, registration, now=NOW):
    async with s["uow"]() as u:
        exam_service = ExamService(ExamRepository(u), ProjectTypeQuestionRepository(u))

        def clock():
            return now

        queue = ExamQueueService(
            ExamRegistrationRepository(u), ExamAttemptRepository(u), ExamRepository(u), exam_service, clock=clock
        )
        svc = ExamAttemptService(
            ExamAttemptRepository(u),
            ExamRepository(u),
            reg_service(u, now),
            exam_service,
            queue,
            ExamRegistrationRepository(u),
            clock=clock,
        )
        return await svc.start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=registration.id, expected_version=1),
            s["users"]["teacher"],
        )


async def _finish_attempt(s, attempt_id, now=None):
    if now is None:
        now = NOW
    async with s["uow"]() as u:
        repo = ExamAttemptRepository(u)
        attempt = await repo.get(s["workspace"], s["exams"][0], attempt_id)
        assert attempt is not None, f"Attempt {attempt_id} not found"

        exam_service = ExamService(ExamRepository(u), ProjectTypeQuestionRepository(u))

        def clock():
            return now

        queue = ExamQueueService(
            ExamRegistrationRepository(u), ExamAttemptRepository(u), ExamRepository(u), exam_service, clock=clock
        )
        svc = ExamAttemptService(
            repo,
            ExamRepository(u),
            reg_service(u, now),
            exam_service,
            queue,
            ExamRegistrationRepository(u),
            clock=clock,
        )
        return await svc.finish(
            attempt.workspace_id,
            attempt.exam_id,
            attempt.id,
            AttemptCommand(expected_version=attempt.version),
            s["users"]["teacher"],
        )


async def _start_and_finish(s, project="manager"):
    reg = await _organized(s, project=project)
    result = await _start(s, reg, now=NOW)
    attempt_read, _created = result
    finished = await _finish_attempt(s, attempt_read.id, now=NOW + timedelta(minutes=10))
    async with s["engine"].connect() as conn:
        window_id = (
            await conn.execute(
                text("SELECT id FROM assessment_window WHERE attempt_id = :aid"),
                {"aid": attempt_read.id},
            )
        ).scalar_one()
    return reg, finished, window_id


class TestAudienceOnFinish:
    async def test_creates_audience_on_first_finish(self, seeded):
        s = seeded
        _reg, _finished, window_id = await _start_and_finish(s, project="manager")
        assert window_id is not None

        async with s["engine"].connect() as conn:
            count = (
                await conn.execute(
                    text("SELECT count(*) FROM assessment_window_audience WHERE window_id = :wid"),
                    {"wid": window_id},
                )
            ).scalar_one()
        assert count > 0

    async def test_audience_has_correct_roles(self, seeded):
        s = seeded
        _reg, _finished, window_id = await _start_and_finish(s, project="manager")

        async with s["engine"].connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT user_id, role, admitted, exclusion_reason "
                        "FROM assessment_window_audience WHERE window_id = :wid ORDER BY user_id"
                    ),
                    {"wid": window_id},
                )
            ).fetchall()

        roles_by_user = {row.user_id: row for row in rows}

        local_teacher = roles_by_user.get(s["users"]["local_teacher"].id)
        assert local_teacher is not None, "local_teacher should be in audience"
        assert local_teacher.role == "teacher"
        assert local_teacher.admitted is True
        assert local_teacher.exclusion_reason is None

        admin_row = roles_by_user.get(s["users"]["local_admin"].id)
        assert admin_row is not None, "local_admin should be in audience"
        assert admin_row.role == "teacher"

        # Local NULL role falls back to the global role.
        null_manager = roles_by_user.get(s["users"]["null_manager"].id)
        assert null_manager is not None, "null_manager should be in audience"
        assert null_manager.role == "manager"

        # Global teacher without workspace participation is not part of the audience.
        async with s["engine"].connect() as conn:
            outsider_in_audience = (
                await conn.execute(
                    text("SELECT count(*) FROM assessment_window_audience WHERE window_id = :wid AND user_id = :uid"),
                    {"wid": window_id, "uid": s["users"]["outsider"].id},
                )
            ).scalar_one()
        assert outsider_in_audience == 0

        valid_roles = {"teacher", "manager", "member"}
        for row in rows:
            assert row.role in valid_roles, f"Invalid role {row.role} for user {row.user_id}"

    async def test_excludes_manager_of_defending_team(self, seeded):
        s = seeded
        _reg, _finished, window_id = await _start_and_finish(s, project="manager")

        async with s["engine"].connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT admitted, exclusion_reason FROM assessment_window_audience "
                        "WHERE window_id = :wid AND user_id = :uid"
                    ),
                    {"wid": window_id, "uid": s["users"]["manager"].id},
                )
            ).fetchone()

        assert row is not None, "manager user should be in audience"
        assert row.admitted is False
        assert row.exclusion_reason == "manager_of_defending_team"

    async def test_author_of_other_project_is_admitted(self, seeded):
        s = seeded
        _reg, _finished, window_id = await _start_and_finish(s, project="manager")

        async with s["engine"].connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT admitted, exclusion_reason FROM assessment_window_audience "
                        "WHERE window_id = :wid AND user_id = :uid"
                    ),
                    {"wid": window_id, "uid": s["users"]["member"].id},
                )
            ).fetchone()

        if row is not None:
            assert row.admitted is True
            assert row.exclusion_reason is None

    async def test_teachers_are_never_excluded(self, seeded):
        s = seeded
        _reg, _finished, window_id = await _start_and_finish(s, project="manager")

        async with s["engine"].connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT user_id, admitted, exclusion_reason FROM assessment_window_audience "
                        "WHERE window_id = :wid AND role = 'teacher'"
                    ),
                    {"wid": window_id},
                )
            ).fetchall()

        for row in rows:
            assert row.admitted is True, f"user {row.user_id}: teacher excluded unexpectedly"
            assert row.exclusion_reason is None

    async def test_own_project_ids_include_authored_projects(self, seeded):
        s = seeded
        _reg, _finished, window_id = await _start_and_finish(s, project="manager")

        async with s["engine"].connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT own_project_ids FROM assessment_window_audience "
                        "WHERE window_id = :wid AND user_id = :uid"
                    ),
                    {"wid": window_id, "uid": s["users"]["manager"].id},
                )
            ).fetchone()

        assert row is not None
        manager_project_id = s["projects"]["manager"]
        assert manager_project_id in (row.own_project_ids or [])

    async def test_idempotent_finish_does_not_duplicate_audience(self, seeded):
        s = seeded
        _reg, finished, window_id = await _start_and_finish(s, project="manager")

        async with s["engine"].connect() as conn:
            count1 = (
                await conn.execute(
                    text("SELECT count(*) FROM assessment_window_audience WHERE window_id = :wid"),
                    {"wid": window_id},
                )
            ).scalar_one()

        await _finish_attempt(s, finished.id, now=NOW + timedelta(minutes=15))

        async with s["engine"].connect() as conn:
            count2 = (
                await conn.execute(
                    text("SELECT count(*) FROM assessment_window_audience WHERE window_id = :wid"),
                    {"wid": window_id},
                )
            ).scalar_one()

        assert count1 == count2
        assert count1 > 0

    async def test_manager_is_excluded_with_correct_role(self, seeded):
        s = seeded
        _reg, _finished, window_id = await _start_and_finish(s, project="manager")

        async with s["engine"].connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT role, admitted, exclusion_reason FROM assessment_window_audience "
                        "WHERE window_id = :wid AND user_id = :uid"
                    ),
                    {"wid": window_id, "uid": s["users"]["manager"].id},
                )
            ).fetchone()

        assert row is not None
        assert row.role == "manager"
        assert row.admitted is False
        assert row.exclusion_reason == "manager_of_defending_team"

    async def test_excludes_participant_of_defending_team(self, seeded):
        s = seeded
        # A workspace member joins the defending project before the defense starts.
        async with s["uow"]() as u:
            u.session.add(
                ProjectParticipation(project_id=s["projects"]["manager"], participant_id=s["users"]["member"].id)
            )
            await u.session.flush()

        _reg, _finished, window_id = await _start_and_finish(s, project="manager")

        async with s["engine"].connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT role, admitted, exclusion_reason, own_project_ids "
                        "FROM assessment_window_audience WHERE window_id = :wid AND user_id = :uid"
                    ),
                    {"wid": window_id, "uid": s["users"]["member"].id},
                )
            ).fetchone()

        assert row is not None, "participant should be in audience"
        assert row.role == "member"
        assert row.admitted is False
        assert row.exclusion_reason == "member_of_defending_team"
        # own_project_ids holds both the authored project and the participation.
        assert set(row.own_project_ids) == {s["projects"]["manager"], s["projects"]["member"]}

    async def test_member_reason_wins_over_manager_reason(self, seeded):
        s = seeded
        # The manager (author) also appears in project_participation of the defending team:
        # member_of_defending_team is the stronger reason.
        async with s["uow"]() as u:
            u.session.add(
                ProjectParticipation(project_id=s["projects"]["manager"], participant_id=s["users"]["manager"].id)
            )
            await u.session.flush()

        _reg, _finished, window_id = await _start_and_finish(s, project="manager")

        async with s["engine"].connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT admitted, exclusion_reason FROM assessment_window_audience "
                        "WHERE window_id = :wid AND user_id = :uid"
                    ),
                    {"wid": window_id, "uid": s["users"]["manager"].id},
                )
            ).fetchone()

        assert row is not None
        assert row.admitted is False
        assert row.exclusion_reason == "member_of_defending_team"

    async def test_membership_added_after_finish_does_not_rewrite_snapshot(self, seeded):
        s = seeded
        _reg, finished, window_id = await _start_and_finish(s, project="manager")

        async with s["engine"].connect() as conn:
            before = (
                await conn.execute(
                    text(
                        "SELECT count(*), count(*) FILTER (WHERE admitted) "
                        "FROM assessment_window_audience WHERE window_id = :wid"
                    ),
                    {"wid": window_id},
                )
            ).fetchone()
        total_before, admitted_before = before

        # After the window opened, manager2 joins the defending team.
        async with s["uow"]() as u:
            u.session.add(
                ProjectParticipation(project_id=s["projects"]["manager"], participant_id=s["users"]["manager2"].id)
            )
            await u.session.flush()

        # A later finish is a no-op and must not rebuild the snapshot.
        await _finish_attempt(s, finished.id, now=NOW + timedelta(minutes=20))

        async with s["engine"].connect() as conn:
            after = (
                await conn.execute(
                    text(
                        "SELECT count(*), count(*) FILTER (WHERE admitted) "
                        "FROM assessment_window_audience WHERE window_id = :wid"
                    ),
                    {"wid": window_id},
                )
            ).fetchone()
            manager2_row = (
                await conn.execute(
                    text(
                        "SELECT admitted, exclusion_reason FROM assessment_window_audience "
                        "WHERE window_id = :wid AND user_id = :uid"
                    ),
                    {"wid": window_id, "uid": s["users"]["manager2"].id},
                )
            ).fetchone()

        total_after, admitted_after = after
        assert (total_after, admitted_after) == (total_before, admitted_before)
        assert manager2_row is not None
        assert manager2_row.admitted is True
        assert manager2_row.exclusion_reason is None

    async def test_finish_rolls_back_window_and_audience_together(self, seeded):
        s = seeded
        reg = await _organized(s, project="manager")
        started, _created = await _start(s, reg, now=NOW)

        # A trigger fails on any audience insert; the whole finish transaction must roll back.
        async with s["engine"].begin() as conn:
            await conn.execute(
                text(
                    "CREATE FUNCTION fail_audience() RETURNS trigger AS $$ "
                    "BEGIN RAISE EXCEPTION 'audience boom'; RETURN NULL; END; "
                    "$$ LANGUAGE plpgsql"
                )
            )
            await conn.execute(
                text(
                    "CREATE TRIGGER trg_fail_audience AFTER INSERT ON assessment_window_audience "
                    "FOR EACH ROW EXECUTE FUNCTION fail_audience()"
                )
            )
        try:
            with pytest.raises(Exception, match="audience boom"):
                await _finish_attempt(s, started.id, now=NOW + timedelta(minutes=10))
        finally:
            async with s["engine"].begin() as conn:
                await conn.execute(text("DROP TRIGGER trg_fail_audience ON assessment_window_audience"))
                await conn.execute(text("DROP FUNCTION fail_audience"))

        async with s["engine"].connect() as conn:
            finished_count = (
                await conn.execute(text("SELECT count(*) FROM exam_attempt WHERE status='finished'"))
            ).scalar_one()
            windows = (await conn.execute(text("SELECT count(*) FROM assessment_window"))).scalar_one()
            audience = (await conn.execute(text("SELECT count(*) FROM assessment_window_audience"))).scalar_one()
            locks = (await conn.execute(text("SELECT count(*) FROM project_type_question_lock"))).scalar_one()

        assert finished_count == 0
        assert windows == 0
        assert audience == 0
        assert locks == 0


class TestAudienceMigration:
    async def test_table_exists_after_migration(self, seeded):
        s = seeded
        async with s["engine"].connect() as conn:
            tables = set(
                (await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).scalars()
            )
        assert "assessment_window_audience" in tables

    async def test_can_reverse_migration_preserving_exam(self, seeded, registration_database_url, run_migrations):
        s = seeded
        run_migrations(registration_database_url, "check")
        await s["engine"].dispose()
        run_migrations(registration_database_url, "downgrade", "d108a10b20c7")
        run_migrations(registration_database_url, "upgrade", "head")
        assert await count(s, "exam") == 3
        assert await count(s, "project_type_question") == 1
        async with s["engine"].connect() as conn:
            tables = set(
                (await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).scalars()
            )
        assert "assessment_window_audience" in tables


async def test_teacher_who_is_project_participant_remains_admitted(seeded):
    s = seeded
    teacher = s["users"]["local_teacher"].id
    async with s["uow"]() as u:
        u.session.add(ProjectParticipation(project_id=s["projects"]["manager"], participant_id=teacher, role="member"))
    _, _, window_id = await _start_and_finish(s)
    async with s["engine"].connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT role, admitted, exclusion_reason, own_project_ids "
                    "FROM assessment_window_audience WHERE window_id=:wid AND user_id=:uid"
                ),
                {"wid": window_id, "uid": teacher},
            )
        ).one()
    assert row.role == "teacher"
    assert row.admitted is True
    assert row.exclusion_reason is None
    assert s["projects"]["manager"] in row.own_project_ids


async def test_own_projects_do_not_include_another_workspace(seeded):
    s = seeded
    uid = s["users"]["member"].id
    async with s["uow"]() as u:
        project = Project(
            name="Foreign participation",
            author_id=s["users"]["outsider"].id,
            workspace_id=s["foreign_workspace"],
            project_type_id=s["types"][2],
        )
        u.session.add(project)
        await u.session.flush()
        foreign_id = project.id
        u.session.add(ProjectParticipation(project_id=foreign_id, participant_id=uid, role="member"))
    _, _, window_id = await _start_and_finish(s)
    async with s["engine"].connect() as conn:
        own_ids = (
            await conn.execute(
                text("SELECT own_project_ids FROM assessment_window_audience WHERE window_id=:wid AND user_id=:uid"),
                {"wid": window_id, "uid": uid},
            )
        ).scalar_one()
    assert foreign_id not in own_ids


async def test_audience_rejects_window_from_another_workspace(seeded):
    s = seeded
    _, _, window_id = await _start_and_finish(s)
    with pytest.raises(IntegrityError):
        async with s["uow"]() as u:
            u.session.add(
                AssessmentWindowAudience(
                    window_id=window_id,
                    workspace_id=s["foreign_workspace"],
                    user_id=s["users"]["outsider"].id,
                    role="teacher",
                    own_project_ids=[],
                    admitted=True,
                    exclusion_reason=None,
                    created_at=NOW,
                )
            )
            await u.session.flush()
