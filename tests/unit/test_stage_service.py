from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from src.core.exceptions import NotFoundError, PermissionError, ValidationError
from src.model.project import Project, ProjectStage, ProjectType
from src.services.stage_service import ProjectStageService


def _stage(id: int, order: int, requires_approval: bool = False) -> ProjectStage:
    return ProjectStage(id=id, name=f"stage{id}", order=order, requires_approval=requires_approval)


class TestProjectStageService:
    """Тесты для ProjectStageService — переходы по этапам"""

    def _make_service(self) -> tuple:
        type_repo = Mock()
        type_repo.uow = Mock()
        type_repo.uow.session = AsyncMock()

        transition_repo = Mock()
        transition_repo.create_transition = AsyncMock()

        service = ProjectStageService(type_repo, transition_repo)  # type: ignore[arg-type]
        return service, type_repo, transition_repo

    def _project_with_stages(self, current_stage_id=None, pending=False) -> Project:
        ptype = ProjectType(id=1, name="Курсовая")
        ptype.stages = [
            _stage(1, 0),  # первый — не требует утверждения
            _stage(2, 1, requires_approval=True),  # второй — требует утверждения
            _stage(3, 2),  # третий
        ]
        project = Project(
            id=10,
            name="Test",
            author_id=100,
            current_stage_id=current_stage_id,
            stage_pending_approval=pending,
        )
        project.project_type = ptype
        project.project_type_id = 1
        return project

    @pytest.mark.asyncio
    async def test_should_advance_to_second_with_pending_approval(self):
        # given
        service, type_repo, transition_repo = self._make_service()
        project = self._project_with_stages(current_stage_id=1)
        type_repo.uow.session.get = AsyncMock(return_value=project)
        type_repo.uow.session.flush = AsyncMock()

        # when
        result = await service.advance_stage(10, 100)

        # then
        assert result.current_stage_id == 2  # noqa: PLR2004
        assert result.stage_pending_approval is True  # второй этап требует утверждения
        transition_repo.create_transition.assert_awaited_once()
        kwargs = transition_repo.create_transition.await_args.kwargs
        assert kwargs["project_id"] == 10  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_should_deny_advance_for_non_author(self):
        # given
        service, type_repo, _ = self._make_service()
        project = self._project_with_stages(current_stage_id=1)
        type_repo.uow.session.get = AsyncMock(return_value=project)

        # when / then
        with pytest.raises(PermissionError):
            await service.advance_stage(10, 999)

    @pytest.mark.asyncio
    async def test_should_not_advance_while_pending_approval(self):
        # given
        service, type_repo, _ = self._make_service()
        project = self._project_with_stages(current_stage_id=1, pending=True)
        type_repo.uow.session.get = AsyncMock(return_value=project)

        # when / then
        with pytest.raises(ValidationError):
            await service.advance_stage(10, 100)

    @pytest.mark.asyncio
    async def test_should_reject_and_rollback_to_previous_stage(self):
        # given
        service, type_repo, transition_repo = self._make_service()
        project = self._project_with_stages(current_stage_id=2, pending=True)
        type_repo.uow.session.get = AsyncMock(return_value=project)
        type_repo.uow.session.flush = AsyncMock()

        # пользователь — преподаватель (роль teacher)
        teacher = Mock()
        teacher_role = Mock()
        teacher_role.name = "teacher"
        teacher.role = teacher_role
        # session.get(User, user_id) -> teacher, session.get(Project, project_id) -> project
        type_repo.uow.session.get = AsyncMock(
            side_effect=lambda model_cls, _user_id: project if model_cls.__name__ == "Project" else teacher
        )

        # when
        result = await service.reject_stage(10, 200, comment="Тема отклонена")

        # then
        assert result.current_stage_id == 1  # вернулись на предыдущий
        assert result.stage_pending_approval is False
        kwargs = transition_repo.create_transition.await_args.kwargs
        assert kwargs["action"] == "reject"
        assert kwargs["comment"] == "Тема отклонена"

    @pytest.mark.asyncio
    async def test_should_approve_current_stage(self):
        # given
        service, type_repo, transition_repo = self._make_service()
        project = self._project_with_stages(current_stage_id=2, pending=True)
        type_repo.uow.session.flush = AsyncMock()

        teacher = Mock()
        teacher_role = Mock()
        teacher_role.name = "teacher"
        teacher.role = teacher_role
        type_repo.uow.session.get = AsyncMock(
            side_effect=lambda model_cls, _user_id: project if model_cls.__name__ == "Project" else teacher
        )

        # when
        result = await service.approve_stage(10, 200)

        # then
        assert result.stage_pending_approval is False
        kwargs = transition_repo.create_transition.await_args.kwargs
        assert kwargs["action"] == "approve"

    @pytest.mark.asyncio
    async def test_should_raise_when_project_type_missing(self):
        # given
        service, type_repo, _ = self._make_service()
        project = Project(id=10, name="Test", author_id=100)
        type_repo.uow.session.get = AsyncMock(return_value=project)

        # when / then
        with pytest.raises(ValidationError):
            await service.advance_stage(10, 100)

    @pytest.mark.asyncio
    async def test_should_raise_when_project_not_found(self):
        # given
        service, type_repo, _ = self._make_service()
        type_repo.uow.session.get = AsyncMock(return_value=None)

        # when / then
        with pytest.raises(NotFoundError):
            await service.advance_stage(999, 100)


class TestProjectTypeCRUDWorkspaceScoped:
    """Тесты для workspace-scoped CRUD типов проектов и этапов"""

    def _make_service(self) -> tuple:
        type_repo = Mock()
        type_repo.uow = Mock()
        type_repo.uow.session = AsyncMock()

        transition_repo = Mock()
        transition_repo.create_transition = AsyncMock()

        service = ProjectStageService(type_repo, transition_repo)  # type: ignore[arg-type]
        return service, type_repo

    def _global_admin(self) -> Mock:
        user = Mock()
        role = Mock()
        role.name = "admin"
        user.role = role
        return user

    async def _mock_session_user(self, type_repo, user: Mock) -> None:
        type_repo.uow.session.get = AsyncMock(
            side_effect=lambda model_cls, _user_id: user if model_cls.__name__ == "User" else None
        )

    @pytest.mark.asyncio
    async def test_should_create_type_in_workspace_as_admin(self):
        # given
        service, type_repo = self._make_service()
        admin = self._global_admin()
        await self._mock_session_user(type_repo, admin)
        type_repo.create = AsyncMock(return_value=ProjectType(id=5, name="Курсовая", workspace_id=42))

        # when
        result = await service.create_project_type(
            data=Mock(name="Курсовая", description="Тест", workspace_id=42),
            workspace_id=42,
            user_id=1,
        )

        # then
        assert result.id == 5  # noqa: PLR2004
        type_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_should_deny_delete_type_in_foreign_workspace(self):
        # given
        service, type_repo = self._make_service()
        # Пользователь — не админ глобально и не состоит в workspace 42
        user = Mock()
        role = Mock()
        role.name = "member"
        user.role = role
        await self._mock_session_user(type_repo, user)
        # В workspace нет участия
        exec_result = Mock()
        exec_result.first.return_value = None
        type_repo.uow.session.execute = AsyncMock(return_value=exec_result)
        ptype = ProjectType(id=9, name="Диплом", workspace_id=42)
        type_repo.get_by_id = AsyncMock(return_value=ptype)

        # when / then
        with pytest.raises(PermissionError):
            await service.delete_project_type(9, 42, user_id=1)

    @pytest.mark.asyncio
    async def test_should_deny_edit_type_of_other_workspace(self):
        # given
        service, type_repo = self._make_service()
        admin = self._global_admin()
        await self._mock_session_user(type_repo, admin)
        ptype = ProjectType(id=9, name="Диплом", workspace_id=42)
        type_repo.get_by_id = AsyncMock(return_value=ptype)

        # when / then: тип принадлежит workspace 42, но запрос идёт за workspace 7
        with pytest.raises(PermissionError):
            await service.update_project_type(
                9, workspace_id=7, data=Mock(name="Другое"), user_id=1
            )

    @pytest.mark.asyncio
    async def test_should_list_only_workspace_types(self):
        # given
        service, type_repo = self._make_service()
        type_repo.list_with_stages = AsyncMock(return_value=[])

        # when
        await service.list_project_types(workspace_id=42)

        # then
        type_repo.list_with_stages.assert_awaited_once_with(42)
