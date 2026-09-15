from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

from src.core.exceptions import NotFoundError, PermissionError, ValidationError
from src.model.project import Project, ProjectStage, ProjectType, StageTransition
from src.schema.project import ProjectFull
from src.services.stage_service import ProjectStageService


def _stage(id: int, order: int, requires_approval: bool = False, visible_to_participants: bool = True) -> ProjectStage:
    return ProjectStage(
        id=id,
        name=f"stage{id}",
        order=order,
        requires_approval=requires_approval,
        visible_to_participants=visible_to_participants,
    )


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
        transition_repo.get_transitions_by_project = AsyncMock(return_value=[])

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
        transition_repo.get_transitions_by_project.assert_awaited_once_with(10)

    @pytest.mark.asyncio
    async def test_should_expose_latest_reject_comment_in_project_full(self):
        # given
        project_type = ProjectType(id=1, name="Курсовая")
        first = _stage(1, 0)
        second = _stage(2, 1)
        actor = Mock()
        actor.first_name = "Иван"
        actor.last_name = "Петров"

        now = datetime.now(ZoneInfo("UTC"))
        old_reject = StageTransition(
            id=1,
            project_id=10,
            stage_id=2,
            from_stage_id=2,
            actor_id=200,
            action="reject",
            comment="Старый комментарий",
            created_at=now - timedelta(days=2),
        )
        old_reject.stage = second
        old_reject.from_stage = second
        old_reject.actor = actor
        new_reject = StageTransition(
            id=2,
            project_id=10,
            stage_id=1,
            from_stage_id=1,
            actor_id=200,
            action="reject",
            comment="Тема отклонена",
            created_at=now - timedelta(days=1),
        )
        new_reject.stage = first
        new_reject.from_stage = first
        new_reject.actor = actor

        project = Project(id=10, name="Test", author_id=100, current_stage_id=1, stage_pending_approval=False)
        project.project_type = project_type
        project.stage_transitions = [old_reject, new_reject]

        # when
        result = ProjectFull.from_orm(project, 100)

        # then
        assert result.stage_rejection is not None
        assert result.stage_rejection.comment == "Тема отклонена"
        assert result.stage_rejection.stage_name == "stage1"
        assert result.stage_rejection.actor_name == "Иван Петров"

    @pytest.mark.asyncio
    async def test_should_not_expose_rejection_when_stage_approved(self):
        # given
        project_type = ProjectType(id=1, name="Курсовая")
        project = Project(id=10, name="Test", author_id=100, stage_pending_approval=False)
        project.project_type = project_type
        project.stage_transitions = []

        # when
        result = ProjectFull.from_orm(project, 100)

        # then
        assert result.stage_rejection is None

    @pytest.mark.asyncio
    async def test_should_not_expose_rejection_after_stage_approved(self):
        # given — этап сначала вернули, потом утвердили
        project_type = ProjectType(id=1, name="Курсовая")
        now = datetime.now(ZoneInfo("UTC"))
        reject = StageTransition(
            id=1,
            project_id=10,
            stage_id=2,
            from_stage_id=2,
            actor_id=200,
            action="reject",
            comment="заполни все",
            created_at=now - timedelta(days=2),
        )
        approve = StageTransition(
            id=2,
            project_id=10,
            stage_id=2,
            from_stage_id=None,
            actor_id=200,
            action="approve",
            comment=None,
            created_at=now - timedelta(days=1),
        )
        project = Project(id=10, name="Test", author_id=100, current_stage_id=2, stage_pending_approval=False)
        project.project_type = project_type
        project.stage_transitions = [reject, approve]

        # when
        result = ProjectFull.from_orm(project, 100)

        # then
        assert result.stage_rejection is None

    @pytest.mark.asyncio
    async def test_should_approve_current_stage_and_advance_to_next(self):
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

        # then — этап утверждён и проект автоматически перешёл на следующий
        assert result.current_stage_id == 3  # noqa: PLR2004
        assert result.stage_pending_approval is False
        calls = transition_repo.create_transition.call_args_list
        assert calls[0].kwargs["action"] == "approve"
        assert calls[1].kwargs["action"] == "advance"
        assert calls[1].kwargs["stage_id"] == 3  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_should_approve_final_stage_without_advance(self):
        # given
        service, type_repo, transition_repo = self._make_service()
        project = self._project_with_stages(current_stage_id=3, pending=True)
        type_repo.uow.session.flush = AsyncMock()

        teacher = Mock()
        teacher_role = Mock()
        teacher_role.name = "teacher"
        teacher.role = teacher_role
        _mock_project_fetch(type_repo.uow.session, project)
        _mock_teacher(type_repo.uow.session, teacher)

        # when
        result = await service.approve_stage(10, 200)

        # then — последний этап утверждён, перехода нет
        assert result.current_stage_id == 3  # noqa: PLR2004
        assert result.stage_pending_approval is False
        calls = transition_repo.create_transition.call_args_list
        assert len(calls) == 1
        assert calls[0].kwargs["action"] == "approve"

    @pytest.mark.asyncio
    async def test_should_mark_next_stage_pending_when_it_requires_approval(self):
        # given — второй и третий этапы требуют утверждения
        service, type_repo, transition_repo = self._make_service()
        type_repo.uow.session.flush = AsyncMock()
        ptype = ProjectType(id=1, name="Курсовая")
        ptype.stages = [
            _stage(1, 0),
            _stage(2, 1, requires_approval=True),
            _stage(3, 2, requires_approval=True),
        ]
        project = Project(id=10, name="Test", author_id=100, current_stage_id=2, stage_pending_approval=True)
        project.project_type = ptype
        _mock_project_fetch(type_repo.uow.session, project)

        teacher = Mock()
        teacher_role = Mock()
        teacher_role.name = "teacher"
        teacher.role = teacher_role
        _mock_teacher(type_repo.uow.session, teacher)

        # when
        result = await service.approve_stage(10, 200)

        # then — уже на следующем этапе и снова ожидает утверждения
        assert result.current_stage_id == 3  # noqa: PLR2004
        assert result.stage_pending_approval is True
        calls = transition_repo.create_transition.call_args_list
        assert calls[1].kwargs["action"] == "advance"
        assert calls[1].kwargs["stage_id"] == 3  # noqa: PLR2004

    @pytest.mark.asyncio
    async def test_should_raise_when_project_type_missing(self):
        # given
        service, type_repo, _ = self._make_service()
        project = Project(id=10, name="Test", author_id=100, stage_pending_approval=False)
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
        transition_repo.get_transitions_by_project = AsyncMock(return_value=[])

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
            data=Mock(name="Тема", order=0, requires_approval=False, duration_days=7, visible_to_participants=False),
            user_id=1,
        )

        # then
        type_id_arg, data_arg = type_repo.create_stage.await_args.args
        assert type_id_arg == 5  # noqa: PLR2004
        assert data_arg.duration_days == 7  # noqa: PLR2004
        assert data_arg.visible_to_participants is False

    @pytest.mark.asyncio
    async def test_should_update_visible_to_participants(self):
        # given
        service, type_repo = self._make_service()
        admin = self._global_admin()
        await self._mock_session_user(type_repo, admin)
        ptype = ProjectType(id=5, name="Курсовая", workspace_id=42)
        ptype.stages = []
        type_repo.get_by_id = AsyncMock(return_value=ptype)
        type_repo.get_by_id_with_stages = AsyncMock(return_value=ptype)
        type_repo.update_stage = AsyncMock(
            return_value=ProjectStage(
                id=19, name="Решение", order=1, requires_approval=False, duration_days=None, project_type_id=5
            )
        )

        data = Mock()
        data.name = "Решение"
        data.visible_to_participants = False

        # when
        await service.update_stage(type_id=5, stage_id=19, workspace_id=None, data=data, user_id=1)

        # then
        stage_id_arg, data_arg = type_repo.update_stage.await_args.args
        assert stage_id_arg == 19  # noqa: PLR2004
        assert data_arg.visible_to_participants is False

    @pytest.mark.asyncio
    async def test_should_update_workspace_stage_without_workspace_id(self):
        # given
        service, type_repo = self._make_service()
        admin = self._global_admin()
        await self._mock_session_user(type_repo, admin)
        ptype = ProjectType(id=5, name="Курсовая", workspace_id=42)
        ptype.stages = []
        type_repo.get_by_id = AsyncMock(return_value=ptype)
        type_repo.get_by_id_with_stages = AsyncMock(return_value=ptype)
        type_repo.update_stage = AsyncMock(
            return_value=ProjectStage(
                id=19, name="Решение", order=1, requires_approval=False, duration_days=None, project_type_id=5
            )
        )

        data = Mock()
        data.name = "Решение"

        # when: workspace_id не передан — сценарий обновления этапа из UI
        result = await service.update_stage(type_id=5, stage_id=19, workspace_id=None, data=data, user_id=1)

        # then
        assert result.id == 5  # noqa: PLR2004
        stage_id_arg, data_arg = type_repo.update_stage.await_args.args
        assert stage_id_arg == 19  # noqa: PLR2004
        assert data_arg.name == "Решение"

    @pytest.mark.asyncio
    async def test_should_deny_update_stage_of_other_workspace(self):
        # given
        service, type_repo = self._make_service()
        admin = self._global_admin()
        await self._mock_session_user(type_repo, admin)
        ptype = ProjectType(id=9, name="Диплом", workspace_id=42)
        type_repo.get_by_id = AsyncMock(return_value=ptype)

        # when / then: тип принадлежит workspace 42, но запрос идёт за workspace 7
        with pytest.raises(PermissionError):
            await service.update_stage(type_id=9, stage_id=19, workspace_id=7, data=Mock(name="Другое"), user_id=1)

    @pytest.mark.asyncio
    async def test_should_include_duration_in_stage_info(self):
        # given
        service, type_repo = self._make_service()
        ptype = ProjectType(id=5, name="Курсовая")
        ptype.stages = [
            ProjectStage(
                id=1, name="Тема", order=0, requires_approval=False, duration_days=10, visible_to_participants=True
            )
        ]
        type_repo.list_with_stages = AsyncMock(return_value=[ptype])

        # when
        types = await service.list_project_types(workspace_id=None)

        # then
        assert types[0].stages[0].duration_days == 10  # noqa: PLR2004
        assert types[0].stages[0].visible_to_participants is True


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
                ProjectStage(
                    id=1, name="Тема", order=0, requires_approval=False, duration_days=10, visible_to_participants=True
                ),
                ProjectStage(
                    id=2,
                    name="Решение",
                    order=1,
                    requires_approval=False,
                    duration_days=None,
                    visible_to_participants=True,
                ),
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
            stages=[
                ProjectStage(
                    id=1, name="Тема", order=0, requires_approval=False, duration_days=5, visible_to_participants=True
                )
            ],
            entered=None,
            created=created,
        )

        # when
        full = ProjectFull.from_orm(project)

        # then
        assert full.stages[0].deadline == datetime(2026, 9, 7, 9, 0, 0, tzinfo=tz)
