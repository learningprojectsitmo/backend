from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, inspect, null, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from src.core.exceptions import NotFoundError, PermissionError
from src.model.project import Project, ProjectStage, ProjectType
from src.model.project_type_question import ProjectTypeQuestion, ProjectTypeQuestionLevel
from src.model.user import Role, User
from src.model.workspace import WorkSpace, WorkSpaceParticipation, WorkSpaceStatus
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.project_type_question import QuestionListReplace
from src.services.project_type_question_service import ProjectTypeQuestionService
from src.services.question_template_service import QuestionTemplateService
from tests.integration.conftest import migrate

pytestmark = pytest.mark.integration


def custom(text_value="Своя оценка"):
    return {"text": text_value, "levels": [{"score": n, "description": f"Объяснение {n}"} for n in range(1, 6)]}


def service(uow):
    return ProjectTypeQuestionService(ProjectTypeQuestionRepository(uow), QuestionTemplateService())


@pytest_asyncio.fixture(loop_scope="function")
async def seeded(question_db):
    engine, make_uow = question_db
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
    return engine, make_uow, users, [s.id for s in spaces], [t.id for t in types]


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["product", "technical_integration", "research"])
async def test_copy_edit_append_reorder_and_independence(seeded, code):
    _, make_uow, users, spaces, types = seeded
    async with make_uow() as u:
        original = await service(u).apply_template(spaces[0], types[0], code, users["teacher"])
        other = await service(u).apply_template(spaces[1], types[1], code, users["admin"])
    assert len(original.questions) == 5
    assert sum(max(level.score for level in q.levels) for q in original.questions) == 25
    assert len({q.id for q in original.questions + other.questions}) == 10
    data = [q.model_dump(exclude={"position"}) for q in original.questions]
    data[0]["text"] = "Изменённый вопрос"
    data[0]["levels"][0]["description"] = "Новое объяснение"
    data.reverse()
    data.append(custom())
    async with make_uow() as u:
        saved = await service(u).replace_questions(
            spaces[0], types[0], QuestionListReplace.model_validate({"questions": data}), users["local_teacher"]
        )
    assert [q.id for q in saved.questions[:5]] == [q.id for q in reversed(original.questions)]
    assert [q.position for q in saved.questions] == list(range(6))
    async with make_uow() as u:
        persisted = await service(u).get_questions(spaces[0], types[0], users["null_member"])
        untouched = await service(u).get_questions(spaces[1], types[1], users["admin"])
    assert persisted == saved
    assert persisted.questions[4].text == "Изменённый вопрос"
    assert persisted.questions[4].levels[0].description == "Новое объяснение"
    assert untouched == other
    assert QuestionTemplateService().get_template(code).questions[0].text != "Изменённый вопрос"
    async with make_uow() as u:
        replaced = await service(u).apply_template(spaces[0], types[0], code, users["local_admin"])
    assert not {q.id for q in saved.questions} & {q.id for q in replaced.questions}
    async with make_uow() as u:
        empty = await service(u).replace_questions(
            spaces[0], types[0], QuestionListReplace(questions=[]), users["teacher"]
        )
    assert empty.questions == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "error"),
    [
        ("member", PermissionError),
        ("manager", PermissionError),
        ("null_member", PermissionError),
        ("other_teacher", NotFoundError),
        ("outsider", NotFoundError),
    ],
)
async def test_real_database_access_denial_preserves_list(seeded, name, error):
    _, make_uow, users, spaces, types = seeded
    async with make_uow() as u:
        initial = await service(u).apply_template(spaces[0], types[0], "product", users["teacher"])
    with pytest.raises(error):
        async with make_uow() as u:
            await service(u).replace_questions(spaces[0], types[0], QuestionListReplace(questions=[]), users[name])
    async with make_uow() as u:
        assert await service(u).get_questions(spaces[0], types[0], users["teacher"]) == initial


@pytest.mark.asyncio
async def test_foreign_ids_and_scope_are_atomic(seeded):
    _, make_uow, users, spaces, types = seeded
    async with make_uow() as u:
        initial = await service(u).apply_template(spaces[0], types[0], "product", users["teacher"])
        foreign = await service(u).apply_template(spaces[1], types[1], "research", users["admin"])
    data = [custom("Попытка частичного изменения"), foreign.questions[0].model_dump(exclude={"position"})]
    with pytest.raises(NotFoundError):
        async with make_uow() as u:
            await service(u).replace_questions(
                spaces[0], types[0], QuestionListReplace.model_validate({"questions": data}), users["teacher"]
            )
    for type_id in [types[1], types[2], 999999]:
        with pytest.raises(NotFoundError):
            async with make_uow() as u:
                await service(u).get_questions(spaces[0], type_id, users["admin"])
    async with make_uow() as u:
        assert await service(u).get_questions(spaces[0], types[0], users["teacher"]) == initial


@pytest.mark.asyncio
async def test_database_failure_rolls_back_entire_replacement(seeded):
    engine, make_uow, users, spaces, types = seeded
    async with make_uow() as u:
        initial = await service(u).apply_template(spaces[0], types[0], "product", users["teacher"])
    # A real late database error after some row changes, not a mocked rollback.
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE FUNCTION reject_test_question() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.text = 'trigger failure' THEN RAISE EXCEPTION 'test failure'; END IF; RETURN NEW; END $$"
            )
        )
        await conn.execute(
            text(
                "CREATE TRIGGER reject_test_question BEFORE INSERT OR UPDATE ON project_type_question FOR EACH ROW EXECUTE FUNCTION reject_test_question()"
            )
        )
    with pytest.raises(DBAPIError):
        async with make_uow() as u:
            await service(u).replace_questions(
                spaces[0],
                types[0],
                QuestionListReplace.model_validate({"questions": [custom("first change"), custom("trigger failure")]}),
                users["teacher"],
            )
    async with make_uow() as u:
        assert await service(u).get_questions(spaces[0], types[0], users["teacher"]) == initial


@pytest.mark.asyncio
async def test_constraints_and_parent_cascade(seeded):
    engine, make_uow, users, spaces, types = seeded
    async with make_uow() as u:
        initial = await service(u).apply_template(spaces[0], types[0], "product", users["teacher"])
    qid = initial.questions[0].id
    invalid = [
        ("UPDATE project_type_question_level SET score=0 WHERE question_id=:qid AND score=1", {}),
        ("UPDATE project_type_question_level SET score=6 WHERE question_id=:qid AND score=1", {}),
        ("UPDATE project_type_question_level SET score=2 WHERE question_id=:qid AND score=1", {}),
        ("UPDATE project_type_question_level SET description=' ' WHERE question_id=:qid", {}),
        ("UPDATE project_type_question SET text=' ' WHERE id=:qid", {}),
    ]
    for sql, params in invalid:
        with pytest.raises(IntegrityError):
            async with engine.begin() as conn:
                await conn.execute(text(sql), dict(params, qid=qid))
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM project_stage WHERE project_type_id=:tid"), {"tid": types[0]})
        await conn.execute(text("DELETE FROM project_type WHERE id=:tid"), {"tid": types[0]})
        assert (await conn.execute(select(ProjectTypeQuestion))).all() == []
        assert (await conn.execute(select(ProjectTypeQuestionLevel))).all() == []


@pytest.mark.asyncio
async def test_concurrent_writes_wait_for_parent_lock_and_keep_whole_list(seeded):
    engine, make_uow, users, spaces, types = seeded
    first_saved = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()
    pid_holder = []

    async def first():
        async with make_uow() as u:
            await service(u).replace_questions(
                spaces[0],
                types[0],
                QuestionListReplace.model_validate({"questions": [custom("A1"), custom("A2")]}),
                users["teacher"],
            )
            first_saved.set()
            await release_first.wait()

    async def second():
        await first_saved.wait()
        async with make_uow() as u:
            pid_holder.append((await u.session.execute(text("SELECT pg_backend_pid()"))).scalar_one())
            second_started.set()
            await service(u).replace_questions(
                spaces[0],
                types[0],
                QuestionListReplace.model_validate({"questions": [custom("B1"), custom("B2"), custom("B3")]}),
                users["teacher"],
            )

    task1 = asyncio.create_task(first())
    task2 = asyncio.create_task(second())
    try:
        await asyncio.wait_for(second_started.wait(), 5)

        async def blocked():
            async with engine.connect() as conn:
                while True:
                    if (
                        await conn.execute(text("SELECT cardinality(pg_blocking_pids(:pid))"), {"pid": pid_holder[0]})
                    ).scalar_one() > 0:
                        return

        await asyncio.wait_for(blocked(), 5)
        assert not task2.done()
    finally:
        release_first.set()
        await asyncio.wait_for(asyncio.gather(task1, task2), 10)
    async with make_uow() as u:
        result = await service(u).get_questions(spaces[0], types[0], users["teacher"])
    assert [q.text for q in result.questions] == ["B1", "B2", "B3"]
    assert [q.position for q in result.questions] == [0, 1, 2]


def test_migration_preserves_existing_types_and_stages(question_database_url):
    url = question_database_url
    engine = create_engine(make_url(url).set(drivername="postgresql+psycopg2"))
    try:
        migrate(url, "upgrade", "b2c3d4e5f6a7")
        with engine.begin() as conn:
            tid = conn.execute(
                text("INSERT INTO project_type(name) VALUES ('Курсовой проект') RETURNING id")
            ).scalar_one()
            sid = conn.execute(
                text(
                    "INSERT INTO project_stage(project_type_id,name,\"order\",requires_approval,visible_to_participants) VALUES (:tid,'Защита',0,true,true) RETURNING id"
                ),
                {"tid": tid},
            ).scalar_one()
            role_id = conn.execute(Role.__table__.insert().values(name="teacher").returning(Role.id)).scalar_one()
            user_id = conn.execute(
                User.__table__.insert()
                .values(first_name="Teacher", middle_name="Test", password_hashed="test", role_id=role_id)
                .returning(User.id)
            ).scalar_one()
            project_id = conn.execute(
                Project.__table__.insert()
                .values(name="Существующий проект", author_id=user_id, project_type_id=tid)
                .returning(Project.id)
            ).scalar_one()
        migrate(url, "upgrade", "head")
        migrate(url, "check")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM project_type_question")).scalar_one() == 0
        migrate(url, "downgrade", "b2c3d4e5f6a7")
        assert "project_type_question" not in inspect(engine).get_table_names()
        migrate(url, "upgrade", "head")
        migrate(url, "check")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT id,name FROM project_type")).one() == (tid, "Курсовой проект")
            assert conn.execute(text("SELECT id,name,project_type_id FROM project")).one() == (
                project_id,
                "Существующий проект",
                tid,
            )
            assert conn.execute(text("SELECT id,name FROM project_stage")).one() == (sid, "Защита")
        migrate(url, "downgrade", "base")
        migrate(url, "upgrade", "head")
        migrate(url, "check")
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_local_admin_has_no_access_to_other_workspace(seeded):
    _, make_uow, users, spaces, types = seeded
    with pytest.raises(NotFoundError):
        async with make_uow() as u:
            await service(u).replace_questions(
                spaces[1], types[1], QuestionListReplace(questions=[]), users["local_admin"]
            )
