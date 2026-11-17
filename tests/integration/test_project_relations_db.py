"""Integration tests for ProjectRelationsService against real PostgreSQL."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import delete, update

from src.core.exceptions import NotFoundError
from src.model.project import Project, ProjectParticipation
from src.model.user import Role, User
from src.model.workspace import WorkSpace, WorkSpaceParticipation, WorkSpaceStatus
from src.repository.project_repository import ProjectRepository
from src.repository.workspace_repository import WorkSpaceRepository
from src.services.project_relations import ProjectRelationsService

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(loop_scope="function")
async def seeded(exam_db):
    engine, make_uow = exam_db
    async with make_uow() as u:
        roles = {name: Role(name=name) for name in ["admin", "teacher", "manager", "member"]}
        u.session.add_all(roles.values())
        await u.session.flush()

        # Workspace author is user 1 (NOT a teacher)
        ws_author = User(
            first_name="WsAuthor",
            middle_name="Test",
            email="wsauthor@example.test",
            password_hashed="test",
            role=roles["member"],
        )
        teacher = User(
            first_name="Teacher",
            middle_name="Test",
            email="teacher@example.test",
            password_hashed="test",
            role=roles["teacher"],
        )
        local_teacher = User(
            first_name="LocalTeacher",
            middle_name="Test",
            email="localteacher@example.test",
            password_hashed="test",
            role=roles["member"],  # global member, local teacher
        )
        manager = User(
            first_name="Manager",
            middle_name="Test",
            email="manager@example.test",
            password_hashed="test",
            role=roles["manager"],
        )
        member = User(
            first_name="Member",
            middle_name="Test",
            email="member@example.test",
            password_hashed="test",
            role=roles["member"],
        )
        outsider = User(
            first_name="Outsider",
            middle_name="Test",
            email="outsider@example.test",
            password_hashed="test",
            role=roles["member"],
        )
        u.session.add_all([ws_author, teacher, local_teacher, manager, member, outsider])
        await u.session.flush()

        status = WorkSpaceStatus(name="test")
        u.session.add(status)
        await u.session.flush()

        ws = WorkSpace(name="Space", author_id=ws_author.id, status_id=status.id)
        u.session.add(ws)
        await u.session.flush()

        # workspace_participation rows (role_id of the 4 roles)
        for user, role_name in [
            (teacher, "teacher"),
            (local_teacher, "teacher"),  # local teacher overrides global member
            (manager, "manager"),
            (member, "member"),
        ]:
            u.session.add(
                WorkSpaceParticipation(
                    workspace_id=ws.id,
                    participant_id=user.id,
                    role_id=roles[role_name].id,
                )
            )
        await u.session.flush()

        # Project: manager (author) + member as participant
        project = Project(
            name="Project",
            author_id=manager.id,
            workspace_id=ws.id,
        )
        u.session.add(project)
        await u.session.flush()

        u.session.add(
            ProjectParticipation(
                project_id=project.id,
                participant_id=member.id,
                role="member",
            )
        )
        await u.session.flush()

        await u.commit()

        ids = {
            "ws_id": ws.id,
            "ws_author_id": ws_author.id,
            "teacher_id": teacher.id,
            "local_teacher_id": local_teacher.id,
            "manager_id": manager.id,
            "member_id": member.id,
            "outsider_id": outsider.id,
            "project_id": project.id,
        }
        yield engine, make_uow, ids
        return


@pytest_asyncio.fixture(loop_scope="function")
async def svc(seeded):
    _engine, make_uow, ids = seeded
    async with make_uow() as u:
        service = ProjectRelationsService(
            project_repository=ProjectRepository(u),
            workspace_repository=WorkSpaceRepository(u),
        )
        yield service, ids


@pytest.mark.asyncio
async def test_manager_id_is_author(svc):
    service, ids = svc
    manager_id = await service.get_manager_id(ids["project_id"], workspace_id=ids["ws_id"])
    assert manager_id == ids["manager_id"]


@pytest.mark.asyncio
async def test_member_ids_from_participation(svc):
    service, ids = svc
    member_ids = await service.get_member_ids(ids["project_id"], workspace_id=ids["ws_id"])
    assert member_ids == [ids["member_id"]]


@pytest.mark.asyncio
async def test_workspace_teacher_ids_includes_global_and_local(svc):
    service, ids = svc
    teacher_ids = await service.get_workspace_teacher_ids(ids["ws_id"])
    assert ids["teacher_id"] in teacher_ids  # global teacher
    assert ids["local_teacher_id"] in teacher_ids  # local teacher overrides member


@pytest.mark.asyncio
async def test_workspace_author_not_in_teachers(svc):
    service, ids = svc
    teacher_ids = await service.get_workspace_teacher_ids(ids["ws_id"])
    assert ids["ws_author_id"] not in teacher_ids
    assert ids["manager_id"] not in teacher_ids
    assert ids["member_id"] not in teacher_ids


@pytest.mark.asyncio
async def test_is_workspace_teacher(svc):
    service, ids = svc
    assert await service.is_workspace_teacher(ids["teacher_id"], workspace_id=ids["ws_id"]) is True
    assert await service.is_workspace_teacher(ids["local_teacher_id"], workspace_id=ids["ws_id"]) is True
    assert await service.is_workspace_teacher(ids["manager_id"], workspace_id=ids["ws_id"]) is False


@pytest.mark.asyncio
async def test_cross_workspace_isolation(svc):
    service, ids = svc
    with pytest.raises(NotFoundError):
        await service.get_manager_id(ids["project_id"], workspace_id=99999)
    with pytest.raises(NotFoundError):
        await service.get_member_ids(ids["project_id"], workspace_id=99999)


@pytest.mark.asyncio
async def test_get_project_relations_composite(svc):
    service, ids = svc
    rel = await service.get_project_relations(ids["project_id"], workspace_id=ids["ws_id"])
    assert rel.project_id == ids["project_id"]
    assert rel.workspace_id == ids["ws_id"]
    assert rel.manager_id == ids["manager_id"]
    assert rel.member_ids == [ids["member_id"]]
    assert ids["teacher_id"] in rel.workspace_teacher_ids
    assert ids["local_teacher_id"] in rel.workspace_teacher_ids


@pytest.mark.asyncio
async def test_revoked_teacher_loses_access(seeded):
    """Removing a teacher from workspace_participation revokes their teacher role.

    The service reads live workspace_participation; after the row is removed,
    the user is no longer in workspace_teacher_ids and is_workspace_teacher
    returns False. The workspace author is unaffected (never a teacher).
    """
    _engine, make_uow, ids = seeded

    async with make_uow() as u:
        service = ProjectRelationsService(
            project_repository=ProjectRepository(u),
            workspace_repository=WorkSpaceRepository(u),
        )
        # Before revocation: teacher is present
        assert await service.is_workspace_teacher(ids["teacher_id"], workspace_id=ids["ws_id"]) is True
        assert ids["teacher_id"] in await service.get_workspace_teacher_ids(ids["ws_id"])

        # Revoke: delete the workspace_participation row for the teacher
        await u.session.execute(
            delete(WorkSpaceParticipation).where(
                WorkSpaceParticipation.workspace_id == ids["ws_id"],
                WorkSpaceParticipation.participant_id == ids["teacher_id"],
            )
        )
        await u.session.flush()

        assert await service.is_workspace_teacher(ids["teacher_id"], workspace_id=ids["ws_id"]) is False
        assert ids["teacher_id"] not in await service.get_workspace_teacher_ids(ids["ws_id"])

        await u.rollback()


@pytest.mark.asyncio
async def test_role_text_never_makes_teacher(seeded):
    """ProjectParticipation.role free text is never trusted as assessment role."""
    _engine, make_uow, ids = seeded

    async with make_uow() as u:
        service = ProjectRelationsService(
            project_repository=ProjectRepository(u),
            workspace_repository=WorkSpaceRepository(u),
        )
        # Set the participant's free-text role to "teacher" and verify it does
        # NOT appear in workspace_teacher_ids (member_ids unchanged).
        await u.session.execute(
            update(ProjectParticipation)
            .where(ProjectParticipation.project_id == ids["project_id"])
            .values(role="teacher")
        )
        await u.session.flush()

        member_ids = await service.get_member_ids(ids["project_id"], workspace_id=ids["ws_id"])
        assert ids["member_id"] in member_ids  # still a member

        teacher_ids = await service.get_workspace_teacher_ids(ids["ws_id"])
        assert ids["member_id"] not in teacher_ids  # role text not trusted

        await u.rollback()
