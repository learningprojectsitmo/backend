from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

from src.core.exceptions import NotFoundError, PermissionError, ValidationError
from src.model.project import Project, ProjectStage, ProjectType, StageTransition
from src.schema.project import ProjectFull
from src.services.stage_service import ProjectStageService


def _stage(id: int, order: int, requires_approval: bool = False) -> ProjectStage:
    return ProjectStage(id=id, name=f"stage{id}", order=order, requires_approval=requires_approval)


def _mock_project_fetch(session, project: Project | None) -> None:
    """Проект в сервисе достаётся через session.execute(select(Project)...)."""
    exec_result = Mock()
    exec_result.scalar_one_or_none.return_value = project
    session.execute = AsyncMock(return_value=exec_result)


def _mock_teacher(session, teacher: Mock, model_cls_name: str = "User") -> None:
    """Пользователь-преподаватель достаётся через session.get(User, user_id)."""
    session.get = AsyncMock(
        side_effect=lambda model_cls, _user_id: teacher if model_cls.__name__ == model_cls_name else None
    )


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
        _mock_project_fetch(type_repo.uow.session, project)
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
        _mock_project_fetch(type_repo.uow.session, project)

        # when / then
        with pytest.raises(PermissionError):
            await service.advance_stage(10, 999)

    @pytest.mark.asyncio
    async def test_should_not_advance_while_pending_approval(self):
        # given
        service, type_repo, _ = self._make_service()
        project = self._project_with_stages(current_stage_id=1, pending=True)
        _mock_project_fetch(type_repo.uow.session, project)

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
        _mock_project_fetch(type_repo.uow.session, project)
        _mock_teacher(type_repo.uow.session, teacher)

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
        _mock_project_fetch(type_repo.uow.session, project)
        _mock_teacher(type_repo.uow.session, teacher)

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
        _mock_project_fetch(type_repo.uow.session, project)

        # when / then
        with pytest.raises(ValidationError):
            await service.advance_stage(10, 100)

    @pytest.mark.asyncio
    async def test_should_raise_when_project_not_found(self):
        # given
        service, type_repo, _ = self._make_service()
        _mock_project_fetch(type_repo.uow.session, None)

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
            await service.update_project_type(9, workspace_id=7, data=Mock(name="Другое"), user_id=1)

    @pytest.mark.asyncio
    async def test_should_list_only_workspace_types(self):
        # given
        service, type_repo = self._make_service()
        type_repo.list_with_stages = AsyncMock(return_value=[])

        # when
        await service.list_project_types(workspace_id=42)

        # then
        type_repo.list_with_stages.assert_awaited_once_with(42)

    @pytest.mark.asyncio
    async def test_should_pass_duration_days_to_create_stage(self):
        # given
        service, type_repo = self._make_service()
        admin = self._global_admin()
        await self._mock_session_user(type_repo, admin)
        ptype = ProjectType(id=5, name="Курсовая", workspace_id=42)
        ptype.stages = []
        type_repo.get_by_id = AsyncMock(return_value=ptype)
        type_repo.get_by_id_with_stages = AsyncMock(return_value=ptype)
        type_repo.create_stage = AsyncMock(
            return_value=ProjectStage(id=1, name="Тема", order=0, requires_approval=False, duration_days=7)
        )

        # when
        await service.add_stage(
            type_id=5,
            workspace_id=42,
            data=Mock(name="Тема", order=0, requires_approval=False, duration_days=7),
            user_id=1,
        )

        # then
        type_id_arg, data_arg = type_repo.create_stage.await_args.args
        assert type_id_arg == 5  # noqa: PLR2004
        assert data_arg.duration_days == 7  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_should_include_duration_in_stage_info(self):
        # given
        service, type_repo = self._make_service()
        ptype = ProjectType(id=5, name="Курсовая")
        ptype.stages = [ProjectStage(id=1, name="Тема", order=0, requires_approval=False, duration_days=10)]
        type_repo.list_with_stages = AsyncMock(return_value=[ptype])

        # when
        types = await service.list_project_types(workspace_id=None)

        # then
        assert types[0].stages[0].duration_days == 10  # noqa: PLR2004


class TestProjectStageDeadline:
    """Дедлайны этапов в ProjectFull — отсчёт от входа в этап + duration_days"""

    def _project(self, stages: list[ProjectStage], entered: datetime | None, created: datetime) -> Project:
        ptype = ProjectType(id=1, name="Курсовая")
        ptype.stages = stages
        project = Project(
            id=10, name="Test", author_id=100, current_stage_id=stages[-1].id, stage_pending_approval=False
        )
        project.project_type = ptype
        project.created_at = created
        if entered is not None:
            project.stage_transitions = [
                StageTransition(
                    id=1,
                    project_id=10,
                    stage_id=stages[0].id,
                    from_stage_id=None,
                    action="advance",
                    actor_id=100,
                    created_at=entered,
                )
            ]
        else:
            project.stage_transitions = []
        return project

    def test_should_compute_deadline_from_advance_entry(self):
        # given
        tz = ZoneInfo("UTC")
        entered = datetime(2026, 9, 1, 12, 0, 0, tzinfo=tz)
        project = self._project(
            stages=[
                ProjectStage(id=1, name="Тема", order=0, requires_approval=False, duration_days=10),
                ProjectStage(id=2, name="Решение", order=1, requires_approval=False, duration_days=None),
            ],
            entered=entered,
            created=entered,
        )

        # when
        full = ProjectFull.from_orm(project)

        # then
        assert full.stages[0].deadline == entered + timedelta(days=10)
        assert full.stages[0].duration_days == 10  # noqa: PLR2004
        assert full.stages[1].deadline is None

    def test_should_fall_back_to_project_created_at_without_transitions(self):
        # given
        tz = ZoneInfo("UTC")
        created = datetime(2026, 9, 2, 9, 0, 0, tzinfo=tz)
        project = self._project(
            stages=[ProjectStage(id=1, name="Тема", order=0, requires_approval=False, duration_days=5)],
            entered=None,
            created=created,
        )

        # when
        full = ProjectFull.from_orm(project)

        # then
        assert full.stages[0].deadline == datetime(2026, 9, 7, 9, 0, 0, tzinfo=tz)
