from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import create_engine, null, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from src.api.v1.routes import routers
from src.core.container import get_uow
from src.core.dependencies import get_current_user
from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.model.project import ProjectStage, ProjectType
from src.model.user import Role, User
from src.model.workspace import WorkSpace, WorkSpaceParticipation, WorkSpaceStatus
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.repository.stage_repository import ProjectTypeRepository, StageTransitionRepository
from src.schema.exam import ExamCreate, ExamPublish, ExamSettingsReplace
from src.schema.project_type_question import QuestionListReplace
from src.services.exam_service import ExamService
from src.services.project_type_question_service import ProjectTypeQuestionService
from src.services.question_template_service import QuestionTemplateService
from src.services.stage_service import ProjectStageService

pytestmark = pytest.mark.integration


def custom(text_value="Своя оценка"):
    return {"text": text_value, "levels": [{"score": n, "description": f"Объяснение {n}"} for n in range(1, 6)]}


def service(uow):
    return ProjectTypeQuestionService(ProjectTypeQuestionRepository(uow), QuestionTemplateService())


@pytest_asyncio.fixture(loop_scope="function")
async def seeded(exam_db):
    engine, make_uow = exam_db
    async with make_uow() as u:
        roles = {name: Role(name=name) for name in ["admin", "teacher", "member", "manager"]}
        u.session.add_all(roles.values())
        users = {
            name: User(
                first_name=name,
                middle_name="Test",
                email=f"{name}@example.test",
                password_hashed="test",
                role=roles[role],
            )
            for name, role in [
                ("admin", "admin"),
                ("teacher", "teacher"),
                ("other_teacher", "teacher"),
                ("member", "member"),
                ("local_teacher", "member"),
                ("local_admin", "member"),
                ("manager", "manager"),
                ("null_member", "member"),
                ("outsider", "member"),
            ]
        }
        u.session.add_all(users.values())
        status = WorkSpaceStatus(name="test")
        u.session.add(status)
        await u.session.flush()
        spaces = [
            WorkSpace(name=f"Space{i}", author_id=users[owner].id, status_id=status.id)
            for i, owner in enumerate(["teacher", "other_teacher"])
        ]
        u.session.add_all(spaces)
        await u.session.flush()
        for name, role in [
            ("member", "member"),
            ("local_teacher", "teacher"),
            ("local_admin", "admin"),
            ("manager", "manager"),
            ("null_member", None),
        ]:
            u.session.add(
                WorkSpaceParticipation(
                    workspace_id=spaces[0].id, participant_id=users[name].id, role_id=roles[role].id if role else null()
                )
            )
        types = [ProjectType(name="Курсовой проект", workspace_id=s.id) for s in spaces]
        types.append(ProjectType(name="Системный тип", workspace_id=None))
        u.session.add_all(types)
        await u.session.flush()
        stage = ProjectStage(
            name="Защита", order=0, requires_approval=True, visible_to_participants=True, project_type_id=types[0].id
        )
        u.session.add(stage)
    return (engine, make_uow, users, [s.id for s in spaces], [t.id for t in types])


def exams(u):
    return ExamService(ExamRepository(u), ProjectTypeQuestionRepository(u))


async def ready(make_uow, users, spaces, types):
    async with make_uow() as u:
        await service(u).apply_template(spaces[0], types[0], "product", users["teacher"])
        return await exams(u).create(
            spaces[0],
            ExamCreate(title="Exam", starts_at="2026-11-30T07:00:00Z", project_type_ids=[types[0]]),
            users["teacher"],
        )


@pytest.mark.asyncio
async def test_two_exams_and_revision_history(seeded):
    _, make_uow, users, spaces, types = seeded
    a = await ready(make_uow, users, spaces, types)
    b = await ready(make_uow, users, spaces, types)
    async with make_uow() as u:
        v2 = await exams(u).replace_settings(
            spaces[0],
            a.id,
            ExamSettingsReplace(
                expected_version=1,
                reason="Longer",
                configuration=a.configuration.model_copy(update={"assessment_window_minutes": 5}),
            ),
            users["teacher"],
        )
    assert v2.current_settings_version == 2
    async with make_uow() as u:
        old = await exams(u).get_settings(spaces[0], a.id, 1, users["teacher"])
        other = await exams(u).get(spaces[0], b.id, users["teacher"])
    assert old.configuration.assessment_window_minutes == 3
    assert other.current_settings_version == 1
    with pytest.raises(BusinessLogicError):
        async with make_uow() as u:
            await exams(u).replace_settings(
                spaces[0],
                a.id,
                ExamSettingsReplace(expected_version=1, reason="Stale", configuration=a.configuration),
                users["teacher"],
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    [
        "admin",
        "teacher",
        "local_teacher",
        "local_admin",
        "member",
        "manager",
        "null_member",
        "other_teacher",
        "outsider",
    ],
)
async def test_scoped_roles_hidden_draft_and_publish(seeded, name):
    _, make_uow, users, spaces, types = seeded
    a = await ready(make_uow, users, spaces, types)
    writer = name in {"admin", "teacher", "local_teacher", "local_admin"}
    access = name not in {"other_teacher", "outsider"}
    if writer:
        async with make_uow() as u:
            assert (await exams(u).get(spaces[0], a.id, users[name])).id == a.id
    else:
        with pytest.raises(NotFoundError):
            async with make_uow() as u:
                await exams(u).get(spaces[0], a.id, users[name])
    async with make_uow() as u:
        published = await exams(u).publish(spaces[0], a.id, ExamPublish(expected_version=1), users["teacher"])
    assert published.status == "published"
    if access:
        async with make_uow() as u:
            assert (await exams(u).get(spaces[0], a.id, users[name])).status == "published"
    else:
        with pytest.raises(NotFoundError):
            async with make_uow() as u:
                await exams(u).get(spaces[0], a.id, users[name])
    if not writer and access:
        with pytest.raises(PermissionError):
            async with make_uow() as u:
                await exams(u).publish(spaces[0], a.id, ExamPublish(expected_version=1), users[name])


@pytest.mark.asyncio
async def test_publishing_readiness_schedule_and_registration_guard(seeded):
    _, make_uow, users, spaces, types = seeded
    async with make_uow() as u:
        a = await exams(u).create(
            spaces[0], ExamCreate(title="Empty", starts_at="2026-11-30T07:00:00Z"), users["teacher"]
        )
    with pytest.raises(BusinessLogicError):
        async with make_uow() as u:
            await exams(u).publish(spaces[0], a.id, ExamPublish(expected_version=1), users["teacher"])
    a = await ready(make_uow, users, spaces, types)
    with pytest.raises(BusinessLogicError):
        async with make_uow() as u:
            await exams(u).require_self_registration_open(
                spaces[0], a.id, users["manager"], now=datetime(2026, 11, 12, tzinfo=UTC)
            )
    async with make_uow() as u:
        a = await exams(u).publish(spaces[0], a.id, ExamPublish(expected_version=1), users["teacher"])
    async with make_uow() as u:
        again = await exams(u).publish(spaces[0], a.id, ExamPublish(expected_version=1), users["teacher"])
        assert again.published_at == a.published_at
        assert (
            await exams(u).require_self_registration_open(
                spaces[0], a.id, users["manager"], now=datetime(2026, 11, 29, tzinfo=UTC)
            )
        ).version == 1
    with pytest.raises(BusinessLogicError):
        async with make_uow() as u:
            await exams(u).require_self_registration_open(
                spaces[0], a.id, users["manager"], now=datetime(2026, 11, 30, 7, tzinfo=UTC)
            )
    with pytest.raises(BusinessLogicError):
        async with make_uow() as u:
            await exams(u).replace_settings(
                spaces[0],
                a.id,
                ExamSettingsReplace(
                    expected_version=1,
                    reason="Move",
                    configuration=a.configuration.model_copy(update={"project_type_ids": ()}),
                ),
                users["teacher"],
            )


async def published(make_uow, users, spaces, types):
    a = await ready(make_uow, users, spaces, types)
    async with make_uow() as u:
        return await exams(u).publish(spaces[0], a.id, ExamPublish(expected_version=1), users["teacher"])


@pytest.mark.asyncio
async def test_capture_deadlines_and_first_lock(seeded):
    _, make_uow, users, spaces, types = seeded
    a = await published(make_uow, users, spaces, types)
    async with make_uow() as u:
        first = await exams(u).prepare_assessment_window(
            spaces[0], a.id, types[0], expected_version=1, opened_at=datetime(2026, 11, 30, 10, tzinfo=UTC)
        )
    assert first.closes_at == datetime(2026, 11, 30, 10, 3, tzinfo=UTC)
    async with make_uow() as u:
        await exams(u).replace_settings(
            spaces[0],
            a.id,
            ExamSettingsReplace(
                expected_version=1,
                reason="Longer",
                configuration=a.configuration.model_copy(update={"assessment_window_minutes": 5}),
            ),
            users["teacher"],
        )
    async with make_uow() as u:
        second = await exams(u).prepare_assessment_window(
            spaces[0], a.id, types[0], expected_version=2, opened_at=datetime(2026, 11, 30, 10, 2, tzinfo=UTC)
        )
        lock = await ProjectTypeQuestionRepository(u).get_question_lock(types[0])
        assert lock.locked_at == first.opened_at
    assert second.closes_at == datetime(2026, 11, 30, 10, 7, tzinfo=UTC)
    assert first.settings_version == 1 and second.settings_version == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["clear", "reorder", "explanation", "text", "template"])
async def test_all_mutations_blocked_after_capture(seeded, operation):
    _, make_uow, users, spaces, types = seeded
    a = await published(make_uow, users, spaces, types)
    async with make_uow() as u:
        original = await service(u).get_questions(spaces[0], types[0], users["teacher"])
        await exams(u).prepare_assessment_window(
            spaces[0], a.id, types[0], expected_version=1, opened_at=datetime(2026, 11, 30, 10, tzinfo=UTC)
        )
    data = [q.model_dump(exclude={"position"}) for q in original.questions]
    if operation == "clear":
        data = []
    if operation == "reorder":
        data.reverse()
    if operation == "explanation":
        data[0]["levels"][0]["description"] = "Changed"
    if operation == "text":
        data[0]["text"] = "Changed"
    with pytest.raises(BusinessLogicError) as error:
        async with make_uow() as u:
            if operation == "template":
                await service(u).apply_template(spaces[0], types[0], "research", users["teacher"])
            else:
                await service(u).replace_questions(
                    spaces[0], types[0], QuestionListReplace(questions=data), users["teacher"]
                )
    assert error.value.detail["code"] == "questions_locked"
    async with make_uow() as u:
        assert await service(u).get_questions(spaces[0], types[0], users["teacher"]) == original
        await service(u).apply_template(spaces[1], types[1], "research", users["admin"])


@pytest.mark.asyncio
async def test_capture_rollback_and_invalid_type_version(seeded):
    _, make_uow, users, spaces, types = seeded
    a = await published(make_uow, users, spaces, types)
    with pytest.raises(RuntimeError):
        async with make_uow() as u:
            await exams(u).prepare_assessment_window(
                spaces[0], a.id, types[0], expected_version=1, opened_at=datetime(2026, 11, 30, 10, tzinfo=UTC)
            )
            raise RuntimeError("future window insert failed")
    async with make_uow() as u:
        assert await ProjectTypeQuestionRepository(u).get_question_lock(types[0]) is None
    for tid, version, error in [(types[1], 1, NotFoundError), (types[0], 2, BusinessLogicError)]:
        with pytest.raises(error):
            async with make_uow() as u:
                await exams(u).prepare_assessment_window(
                    spaces[0], a.id, tid, expected_version=version, opened_at=datetime(2026, 11, 30, 10, tzinfo=UTC)
                )


@pytest.mark.asyncio
async def test_concurrent_settings_have_one_winner(seeded):
    _, make_uow, users, spaces, types = seeded
    a = await ready(make_uow, users, spaces, types)

    async def update(minutes):
        try:
            async with make_uow() as u:
                return await exams(u).replace_settings(
                    spaces[0],
                    a.id,
                    ExamSettingsReplace(
                        expected_version=1,
                        reason="race",
                        configuration=a.configuration.model_copy(update={"assessment_window_minutes": minutes}),
                    ),
                    users["teacher"],
                )
        except BusinessLogicError as error:
            return error

    outcomes = await asyncio.gather(update(4), update(5))
    assert sum(isinstance(r, BusinessLogicError) for r in outcomes) == 1
    async with make_uow() as u:
        history = await exams(u).list_settings(spaces[0], a.id, users["teacher"], limit=50, offset=0)
    assert [r.version for r in history.items] == [1, 2]


@pytest.mark.asyncio
async def test_http_lifecycle_defaults_history_and_isolation(seeded):
    _, make_uow, users, spaces, types = seeded
    async with make_uow() as u:
        await service(u).apply_template(spaces[0], types[0], "product", users["teacher"])
    app = FastAPI()
    app.include_router(routers)

    async def dependency():
        async with make_uow() as u:
            yield u

    actor = [users["teacher"]]
    app.dependency_overrides[get_uow] = dependency
    app.dependency_overrides[get_current_user] = lambda: actor[0]
    base = f"/v1/workspaces/{spaces[0]}/exams"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.post(
            base, json={"title": "HTTP exam", "starts_at": "2026-11-30T07:00:00Z", "project_type_ids": [types[0]]}
        )
        assert response.status_code == 201, response.text
        exam = response.json()
        eid = exam["id"]
        assert exam["configuration"]["max_score"] == "25.00"
        assert exam["configuration"]["weights"] == {"teacher": 60, "manager": 30, "member": 10}
        actor[0] = users["manager"]
        assert (await client.get(f"{base}/{eid}")).status_code == 404
        assert (await client.get(base)).json()["items"] == []
        actor[0] = users["teacher"]
        assert (await client.post(f"{base}/{eid}/publish", json={"expected_version": 1})).status_code == 200
        config = exam["configuration"]
        config["assessment_window_minutes"] = 5
        update = {"expected_version": 1, "reason": "More time", "configuration": config}
        assert (await client.put(f"{base}/{eid}/settings", json=update)).status_code == 200
        assert (await client.put(f"{base}/{eid}/settings", json=update)).status_code == 409
        history = (await client.get(f"{base}/{eid}/settings")).json()
        assert [r["version"] for r in history["items"]] == [1, 2]
        assert (await client.get(f"{base}/{eid}/settings/1")).json()["configuration"]["assessment_window_minutes"] == 3
        assert (await client.get(f"/v1/workspaces/{spaces[1]}/exams/{eid}")).status_code == 404
        actor[0] = users["member"]
        assert (await client.get(f"{base}/{eid}")).status_code == 200
        assert (await client.get(f"{base}/{eid}/settings")).status_code == 403


@pytest.mark.asyncio
async def test_deferred_commit_failure_is_not_http_success(seeded):
    engine, make_uow, users, spaces, _types = seeded
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "CREATE FUNCTION fail_exam_commit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'late failure'; RETURN NEW; END $$"
            )
        )
        await connection.execute(
            text(
                "CREATE CONSTRAINT TRIGGER exam_commit_failure AFTER INSERT OR UPDATE ON exam DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fail_exam_commit()"
            )
        )
    app = FastAPI()
    app.include_router(routers)

    async def dependency():
        async with make_uow() as u:
            yield u

    app.dependency_overrides[get_uow] = dependency
    app.dependency_overrides[get_current_user] = lambda: users["teacher"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/v1/workspaces/{spaces[0]}/exams", json={"title": "Rollback", "starts_at": "2026-11-30T07:00:00Z"}
        )
    assert response.status_code == 500, response.text
    async with engine.connect() as connection:
        assert (await connection.execute(text("SELECT count(*) FROM exam"))).scalar() == 0
        assert (await connection.execute(text("SELECT count(*) FROM exam_settings_revision"))).scalar() == 0


@pytest.mark.asyncio
async def test_cannot_delete_exam_type_through_existing_crud(seeded):
    _, make_uow, users, spaces, types = seeded
    await ready(make_uow, users, spaces, types)
    with pytest.raises(BusinessLogicError) as error:
        async with make_uow() as u:
            await ProjectStageService(ProjectTypeRepository(u), StageTransitionRepository(u)).delete_project_type(
                types[0], spaces[0], users["teacher"].id
            )
    assert error.value.detail["code"] == "project_type_in_use"


@pytest.mark.asyncio
@pytest.mark.parametrize("capture_first", [False, True])
async def test_question_edit_capture_serializes_both_orders(seeded, capture_first):
    engine, make_uow, users, spaces, types = seeded
    a = await published(make_uow, users, spaces, types)
    pid_ready = asyncio.Event()
    pid = []

    async def second():
        try:
            async with make_uow() as u:
                pid.append((await u.session.execute(text("SELECT pg_backend_pid()"))).scalar())
                pid_ready.set()
                if capture_first:
                    await service(u).replace_questions(
                        spaces[0], types[0], QuestionListReplace(questions=[custom("After")]), users["teacher"]
                    )
                else:
                    await exams(u).prepare_assessment_window(
                        spaces[0], a.id, types[0], expected_version=1, opened_at=datetime(2026, 11, 30, 10, tzinfo=UTC)
                    )
        except BusinessLogicError as error:
            return error.detail["code"]
        return "ok"

    task = None
    try:
        async with make_uow() as u:
            if capture_first:
                await exams(u).prepare_assessment_window(
                    spaces[0], a.id, types[0], expected_version=1, opened_at=datetime(2026, 11, 30, 10, tzinfo=UTC)
                )
            else:
                await service(u).replace_questions(
                    spaces[0], types[0], QuestionListReplace(questions=[custom("Before")]), users["teacher"]
                )
            task = asyncio.create_task(second())
            await pid_ready.wait()
            async with asyncio.timeout(5):
                async with engine.connect() as connection:
                    while not (
                        await connection.execute(text("SELECT cardinality(pg_blocking_pids(:pid))"), {"pid": pid[0]})
                    ).scalar():
                        await asyncio.sleep(0)
        assert await asyncio.wait_for(task, 5) == ("questions_locked" if capture_first else "ok")
    finally:
        if task is not None and (not task.done()):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with make_uow() as u:
        result = await service(u).get_questions(spaces[0], types[0], users["teacher"])
    assert len(result.questions) == (5 if capture_first else 1)
    assert all(len(q.levels) == 5 for q in result.questions)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE exam SET current_settings_version=99 WHERE id=:eid",
        "UPDATE exam_settings_revision SET teacher_weight=59 WHERE exam_id=:eid",
        "UPDATE exam_settings_revision SET max_score='NaN'::numeric WHERE exam_id=:eid",
        "UPDATE exam_settings_project_type SET project_type_id=:foreign WHERE exam_id=:eid",
    ],
)
async def test_database_constraints_reject_invalid_settings_scope(seeded, sql):
    _, make_uow, users, spaces, types = seeded
    a = await ready(make_uow, users, spaces, types)
    with pytest.raises(IntegrityError):
        async with make_uow() as u:
            await u.session.execute(text(sql), {"eid": a.id, "foreign": types[1]})
    async with make_uow() as u:
        assert (await exams(u).get(spaces[0], a.id, users["teacher"])).current_settings_version == 1


def test_migration_cycle_preserves_existing_questions(exam_database_url, run_migrations):
    run_migrations(exam_database_url, "upgrade", "head")
    engine = create_engine(make_url(exam_database_url).set(drivername="postgresql+psycopg2"))
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO role(id,name) VALUES(700,'teacher')"))
            connection.execute(
                text(
                    "INSERT INTO \"user\"(id,first_name,middle_name,email,password_hashed,role_id,show_my_contacts) VALUES(700,'Teacher','T','migration@example.test','test',700,false)"
                )
            )
            connection.execute(text("INSERT INTO workspace_status(id,name) VALUES(700,'Test')"))
            connection.execute(text("INSERT INTO workspace(id,name,author_id,status_id) VALUES(700,'Space',700,700)"))
            connection.execute(text("INSERT INTO project_type(id,workspace_id,name) VALUES(700,700,'Type')"))
            connection.execute(
                text("INSERT INTO project_type_question(id,project_type_id,text,position) VALUES(700,700,'Keep',0)")
            )
            connection.execute(
                text(
                    "INSERT INTO project_type_question_level(question_id,score,description) SELECT 700,n,'Level' FROM generate_series(1,5) n"
                )
            )
        run_migrations(exam_database_url, "check")
        run_migrations(exam_database_url, "downgrade", "d100a10b20c3")
        run_migrations(exam_database_url, "upgrade", "head")
        run_migrations(exam_database_url, "check")
        with engine.connect() as connection:
            assert connection.execute(text("SELECT text FROM project_type_question WHERE id=700")).scalar() == "Keep"
            assert (
                connection.execute(
                    text("SELECT count(*) FROM project_type_question_level WHERE question_id=700")
                ).scalar()
                == 5
            )
        run_migrations(exam_database_url, "downgrade", "base")
        run_migrations(exam_database_url, "upgrade", "head")
        run_migrations(exam_database_url, "check")
    finally:
        engine.dispose()
