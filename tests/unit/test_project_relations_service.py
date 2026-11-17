"""Tests for ProjectRelationsService — verifiable project relationship source."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from src.core.exceptions import NotFoundError
from src.model.project import Project
from src.services.project_relations import ProjectRelationsService


def _make_mock_project_repo(project: Mock) -> Mock:
    """Return a ProjectRepository mock that returns *project* from get_by_id."""
    repo = Mock()
    repo.get_by_id = AsyncMock(return_value=project)
    return repo


def _make_mock_ws_repo(session) -> Mock:
    """Return a WorkspaceRepository mock with a session attached."""
    repo = Mock()
    uow = Mock()
    uow.session = session
    repo.uow = uow
    return repo


def _row(participant_id, local_role_name, global_role_name):
    """Create a mock row with the given fields."""
    row = Mock()
    row.participant_id = participant_id
    row.local_role_name = local_role_name
    row.global_role_name = global_role_name
    return row


def _session_returning_all(rows):
    session = AsyncMock()
    session.execute = AsyncMock(return_value=Mock(all=lambda: rows))
    return session


class TestGetManagerId:
    async def test_manager_id_is_project_author(self):
        project = Mock(spec=Project)
        project.id = 42
        project.author_id = 10
        project.workspace_id = 5

        svc = ProjectRelationsService(
            project_repository=_make_mock_project_repo(project),
            workspace_repository=_make_mock_ws_repo(AsyncMock()),
        )

        manager_id = await svc.get_manager_id(42, workspace_id=5)
        assert manager_id == 10

    async def test_manager_id_wrong_workspace_raises_not_found(self):
        project = Mock(spec=Project)
        project.id = 42
        project.author_id = 10
        project.workspace_id = 5

        svc = ProjectRelationsService(
            project_repository=_make_mock_project_repo(project),
            workspace_repository=_make_mock_ws_repo(AsyncMock()),
        )

        with pytest.raises(NotFoundError):
            await svc.get_manager_id(42, workspace_id=999)


class TestGetMemberIds:
    async def test_member_ids_are_project_participants(self):
        project = Mock(spec=Project)
        project.id = 42
        project.author_id = 10
        project.workspace_id = 5

        p1 = Mock()
        p1.participant_id = 11
        p1.role = "teacher"  # arbitrary string — must be ignored
        p2 = Mock()
        p2.participant_id = 12
        p2.role = None
        project.participants = [p1, p2]

        svc = ProjectRelationsService(
            project_repository=_make_mock_project_repo(project),
            workspace_repository=_make_mock_ws_repo(AsyncMock()),
        )

        member_ids = await svc.get_member_ids(42, workspace_id=5)
        assert sorted(member_ids) == [11, 12]

    async def test_member_ids_empty_when_no_participants(self):
        project = Mock(spec=Project)
        project.id = 42
        project.author_id = 10
        project.workspace_id = 5
        project.participants = []

        svc = ProjectRelationsService(
            project_repository=_make_mock_project_repo(project),
            workspace_repository=_make_mock_ws_repo(AsyncMock()),
        )

        member_ids = await svc.get_member_ids(42, workspace_id=5)
        assert member_ids == []


class TestGetWorkspaceTeacherIds:
    async def test_workspace_teacher_ids_local_role_priority(self):
        """Local role=teacher takes priority over global role=member."""
        session = _session_returning_all([_row(10, "teacher", "member")])

        svc = ProjectRelationsService(
            project_repository=Mock(),
            workspace_repository=_make_mock_ws_repo(session),
        )

        teacher_ids = await svc.get_workspace_teacher_ids(1)
        assert 10 in teacher_ids

    async def test_workspace_teacher_ids_admin_maps_to_teacher(self):
        """Admin effective role is included (admin is a teacher for assessment)."""
        session = _session_returning_all([_row(20, "admin", "member")])

        svc = ProjectRelationsService(
            project_repository=Mock(),
            workspace_repository=_make_mock_ws_repo(session),
        )

        teacher_ids = await svc.get_workspace_teacher_ids(1)
        assert 20 in teacher_ids

    async def test_workspace_author_not_teacher_without_participation(self):
        """Workspace.author_id is NOT a teacher without explicit participation."""
        session = _session_returning_all([])

        svc = ProjectRelationsService(
            project_repository=Mock(),
            workspace_repository=_make_mock_ws_repo(session),
        )

        teacher_ids = await svc.get_workspace_teacher_ids(1)
        assert 30 not in teacher_ids

    async def test_null_role_excluded_from_teachers(self):
        """Both local and global roles NULL → not a teacher."""
        session = _session_returning_all([_row(40, None, None)])

        svc = ProjectRelationsService(
            project_repository=Mock(),
            workspace_repository=_make_mock_ws_repo(session),
        )

        teacher_ids = await svc.get_workspace_teacher_ids(1)
        assert 40 not in teacher_ids

    async def test_global_teacher_fallback(self):
        """When local role is NULL, global role=teacher is used."""
        session = _session_returning_all([_row(50, None, "teacher")])

        svc = ProjectRelationsService(
            project_repository=Mock(),
            workspace_repository=_make_mock_ws_repo(session),
        )

        teacher_ids = await svc.get_workspace_teacher_ids(1)
        assert 50 in teacher_ids


class TestGetProjectRelations:
    async def test_get_project_relations_composite(self):
        """Composite result combines manager, members, and teachers."""
        project = Mock(spec=Project)
        project.id = 42
        project.author_id = 10
        project.workspace_id = 5
        p = Mock()
        p.participant_id = 11
        p.role = None
        project.participants = [p]

        session = _session_returning_all([_row(2, "teacher", None)])

        svc = ProjectRelationsService(
            project_repository=_make_mock_project_repo(project),
            workspace_repository=_make_mock_ws_repo(session),
        )

        rel = await svc.get_project_relations(42, workspace_id=5)
        assert rel.project_id == 42
        assert rel.workspace_id == 5
        assert rel.manager_id == 10
        assert rel.member_ids == [11]
        assert 2 in rel.workspace_teacher_ids


class TestIsWorkspaceTeacher:
    def _session_with_one_row(self, row):
        session = AsyncMock()
        session.execute = AsyncMock(return_value=Mock(one_or_none=lambda: row))
        return session

    async def test_is_workspace_teacher_true(self):
        """User with effective teacher role returns True."""
        session = self._session_with_one_row(_row(None, "teacher", None))

        svc = ProjectRelationsService(
            project_repository=Mock(),
            workspace_repository=_make_mock_ws_repo(session),
        )

        assert await svc.is_workspace_teacher(5, workspace_id=1) is True

    async def test_is_workspace_teacher_false(self):
        """User without teacher role returns False."""
        session = self._session_with_one_row(_row(None, "member", None))

        svc = ProjectRelationsService(
            project_repository=Mock(),
            workspace_repository=_make_mock_ws_repo(session),
        )

        assert await svc.is_workspace_teacher(6, workspace_id=1) is False

    async def test_is_workspace_teacher_no_participation(self):
        """User not in workspace returns False."""
        session = self._session_with_one_row(None)

        svc = ProjectRelationsService(
            project_repository=Mock(),
            workspace_repository=_make_mock_ws_repo(session),
        )

        assert await svc.is_workspace_teacher(99, workspace_id=1) is False
