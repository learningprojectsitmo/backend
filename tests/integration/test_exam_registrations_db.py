from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import null, text
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.model.exam_registration import ExamRegistration
from src.model.project import Project, ProjectType
from src.model.user import Role, User
from src.model.workspace import WorkSpace, WorkSpaceParticipation, WorkSpaceStatus
from src.repository.exam_registration_repository import ExamRegistrationRepository
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam import ExamCreate, ExamPublish
from src.schema.exam_registration import SlotBatchCreate
from src.schema.project_type_question import QuestionListReplace
from src.services.exam_registration_service import ExamRegistrationService
from src.services.exam_service import ExamService
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
async def seeded(registration_db):
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
                email=f"{name}@example.test",
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
