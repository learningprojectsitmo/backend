from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from src.core.exceptions import NotFoundError, PermissionError, ValidationError
from src.model.project import Project, ProjectSpecification, SpecificationComment
from src.schema.specification import RequirementGroup, SpecificationUpdate
from src.services.specification_service import SpecificationService


def _project(
    author_id: int = 100,
    workspace_id: int | None = None,
    participants: list[int] | None = None,
) -> Project:
    project = Project(id=10, name="Test", author_id=author_id, workspace_id=workspace_id)
    project.participations = participants or []
    return project


def _spec(status: str = "draft", goal: str = "Цель", tasks: list[str] | None = None) -> ProjectSpecification:
    spec = ProjectSpecification(id=1, project_id=10, status=status)
    spec.goal = goal
    spec.tasks = tasks or ["Задача 1"]
    spec.functional_requirements = []
    spec.non_functional_requirements = []
    spec.acceptance_criteria = ["Критерий 1"]
    spec.rejection_comment = None
    return spec


def _resolved_row(value: object) -> Mock:
    result = Mock()
    result.first.return_value = value
    return result


def _participant_result(found: bool) -> Mock:
    result = Mock()
    result.scalar_one_or_none.return_value = object() if found else None
    return result


class TestSpecificationService:
    """Тесты сервиса технического задания проекта"""

    def _make_service(self) -> tuple:
        spec_repo = Mock()
        spec_repo.uow = Mock()
        spec_repo.uow.session = AsyncMock()

        project_repo = Mock()
        project_repo.get_by_id = AsyncMock(return_value=None)

        service = SpecificationService(spec_repo, project_repository=project_repo)  # type: ignore[arg-type]
        return service, spec_repo, project_repo

    @pytest.mark.asyncio
    async def test_should_return_spec_to_author(self):
        # given
        service, spec_repo, project_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())

        # when
        result = await service.get_specification(10, 100)

        # then
        assert result.status == "draft"
        assert result.goal == "Цель"
        spec_repo.get_or_create_draft.assert_awaited_once_with(10)

    @pytest.mark.asyncio
    async def test_should_allow_teacher_editor_to_view_spec(self):
        # given — преподаватель workspace (админ/teacher), не автор
        service, spec_repo, project_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100, workspace_id=42)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())
        spec_repo.uow.session.execute = AsyncMock(return_value=_resolved_row(Mock()))

        # when
        result = await service.get_specification(10, 200)

        # then
        assert result.status == "draft"

    @pytest.mark.asyncio
    async def test_should_allow_participant_to_view_spec(self):
        # given — участник проекта
        service, spec_repo, project_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100, workspace_id=None)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())
        spec_repo.uow.session.execute = AsyncMock(return_value=_participant_result(found=True))

        # when
        result = await service.get_specification(10, 300)

        # then
        assert result.status == "draft"

    @pytest.mark.asyncio
    async def test_should_deny_view_for_stranger(self):
        # given — посторонний пользователь
        service, spec_repo, project_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec_repo.uow.session.execute = AsyncMock(return_value=_participant_result(found=False))

        # when / then
        with pytest.raises(PermissionError):
            await service.get_specification(10, 500)

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_project_missing(self):
        # given
        service, _, project_repo = self._make_service()
        project_repo.get_by_id.return_value = None

        # when / then
        with pytest.raises(NotFoundError):
            await service.get_specification(999, 100)

    @pytest.mark.asyncio
    async def test_should_update_spec_fields_by_author(self):
        # given
        service, spec_repo, project_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec = _spec()
        spec_repo.get_or_create_draft = AsyncMock(return_value=spec)
        spec_repo.uow.session.flush = AsyncMock()

        data = SpecificationUpdate(
            goal="Новая цель",
            tasks=["Задача A", "", "  Задача B  "],
            acceptance_criteria=["Критерий X", "  "],
        )

        # when
        result = await service.update_specification(10, 100, data)

        # then
        assert result.goal == "Новая цель"
        assert result.tasks == ["Задача A", "Задача B"]  # пустые строки отброшены/обрезаны
        assert result.acceptance_criteria == ["Критерий X"]
        spec_repo.uow.session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_should_update_requirement_groups_by_author(self):
        # given
        service, spec_repo, project_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec = _spec()
        spec_repo.get_or_create_draft = AsyncMock(return_value=spec)
        spec_repo.uow.session.flush = AsyncMock()

        data = SpecificationUpdate(
            functional_requirements=[
                RequirementGroup(name="Студент", requirements=["Может смотреть ТЗ", ""]),
                RequirementGroup(name="Преподаватель", requirements=["Оценивает ТЗ"]),
                RequirementGroup(name="  ", requirements=["Пустая группа"]),
                RequirementGroup(name="Пустая", requirements=[]),
            ],
            non_functional_requirements=[
                RequirementGroup(name="Производительность", requirements=["До 100 пользователей"]),
            ],
        )

        # when
        result = await service.update_specification(10, 100, data)

        # then — пустые имена и группы без требований отброшены
        result_functional = [g.model_dump() for g in result.functional_requirements]
        result_non_functional = [g.model_dump() for g in result.non_functional_requirements]
        assert result_functional == [
            {"name": "Студент", "requirements": ["Может смотреть ТЗ"]},
            {"name": "Преподаватель", "requirements": ["Оценивает ТЗ"]},
        ]
        assert result_non_functional == [
            {"name": "Производительность", "requirements": ["До 100 пользователей"]},
        ]
        spec_repo.uow.session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_should_deny_update_for_non_author(self):
        # given
        service, _, project_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)

        # when / then
        with pytest.raises(PermissionError):
            await service.update_specification(10, 999, SpecificationUpdate(goal="Хак"))

    @pytest.mark.asyncio
    async def test_should_deny_update_not_in_draft_status(self):
        # given — ТЗ уже отправлено на утверждение
        service, spec_repo, project_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec(status="submitted"))

        # when / then
        with pytest.raises(ValidationError):
            await service.update_specification(10, 100, SpecificationUpdate(goal="Новая цель"))


def _comment(author_id: int = 100, specification_id: int = 1) -> SpecificationComment:
    return SpecificationComment(id=5, specification_id=specification_id, author_id=author_id, text="Комментарий")


def _comment_with_author(author_id: int = 100, username: str = "Иван") -> SpecificationComment:
    comment = _comment(author_id=author_id)
    comment.author = Mock()
    comment.author.id = author_id
    comment.author.first_name = username
    return comment


class TestSpecificationCommentService:
    """Тесты сервиса комментариев к техническому заданию"""

    def _make_service(self) -> tuple:
        spec_repo = Mock()
        spec_repo.uow = Mock()
        spec_repo.uow.session = AsyncMock()
        spec_repo.uow.session.execute = AsyncMock(return_value=_resolved_row(None))

        project_repo = Mock()
        project_repo.get_by_id = AsyncMock(return_value=None)

        comment_repo = Mock()
        comment_repo.get_by_id = AsyncMock(return_value=None)
        comment_repo.delete = AsyncMock(return_value=True)

        service = SpecificationService(
            spec_repo,  # type: ignore[arg-type]
            project_repository=project_repo,  # type: ignore[arg-type]
            comment_repository=comment_repo,  # type: ignore[arg-type]
        )
        return service, spec_repo, project_repo, comment_repo

    @pytest.mark.asyncio
    async def test_should_get_comments_for_author(self):
        # given
        service, spec_repo, project_repo, comment_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())
        comment_repo.get_by_specification_id = AsyncMock(return_value=[_comment_with_author(200, "Иван")])

        # when
        result = await service.get_comments(10, 100)

        # then
        assert len(result) == 1
        assert result[0].text == "Комментарий"
        assert result[0].author.username == "Иван"

    @pytest.mark.asyncio
    async def test_should_deny_get_comments_for_stranger(self):
        # given
        service, spec_repo, project_repo, _ = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100, workspace_id=None)
        spec_repo.uow.session.execute = AsyncMock(return_value=_participant_result(found=False))

        # when / then
        with pytest.raises(PermissionError):
            await service.get_comments(10, 500)

    @pytest.mark.asyncio
    async def test_should_add_comment_by_author(self):
        # given
        author_id = 100
        service, spec_repo, project_repo, _ = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=author_id)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())

        # when
        result = await service.add_comment(10, author_id, "  Привет  ")

        # then
        assert result.text == "Привет"
        assert result.author_id == author_id

    @pytest.mark.asyncio
    async def test_should_add_comment_by_teacher(self):
        # given — преподаватель воркспейса
        teacher_id = 200
        service, spec_repo, project_repo, _ = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100, workspace_id=42)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())
        spec_repo.uow.session.execute = AsyncMock(return_value=_resolved_row(Mock()))

        # when
        result = await service.add_comment(10, teacher_id, "Комментарий преподавателя")

        # then
        assert result.author_id == teacher_id

    @pytest.mark.asyncio
    async def test_should_add_comment_by_admin(self):
        # given — глобальный админ
        admin_id = 600
        service, spec_repo, project_repo, _ = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())

        # when
        result = await service.add_comment(10, admin_id, "Комментарий админа", is_admin=True)

        # then
        assert result.author_id == admin_id

    @pytest.mark.asyncio
    async def test_should_deny_add_comment_for_participant(self):
        # given — участник команды, не автор
        service, spec_repo, project_repo, _ = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())

        # when / then
        with pytest.raises(PermissionError):
            await service.add_comment(10, 300, "Комментарий участника")

    @pytest.mark.asyncio
    async def test_should_deny_add_comment_for_stranger(self):
        # given — посторонний пользователь
        service, spec_repo, project_repo, _ = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())

        # when / then
        with pytest.raises(PermissionError):
            await service.add_comment(10, 500, "Комментарий")

    @pytest.mark.asyncio
    async def test_should_update_comment_by_author(self):
        # given
        service, spec_repo, project_repo, comment_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())
        comment_repo.get_by_id = AsyncMock(return_value=_comment(author_id=100))

        # when
        result = await service.update_comment(10, 5, 100, "  Новый текст  ")

        # then
        assert result.text == "Новый текст"

    @pytest.mark.asyncio
    async def test_should_deny_update_comment_for_foreigner(self):
        # given — другой пользователь пытается отредактировать чужой комментарий
        service, spec_repo, project_repo, comment_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())
        comment_repo.get_by_id = AsyncMock(return_value=_comment(author_id=100))

        # when / then
        with pytest.raises(PermissionError):
            await service.update_comment(10, 5, 200, "Хак")

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_comment_not_in_spec(self):
        # given — комментарий из другого ТЗ
        service, spec_repo, project_repo, comment_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())
        comment_repo.get_by_id = AsyncMock(return_value=_comment(author_id=100, specification_id=999))

        # when / then
        with pytest.raises(NotFoundError):
            await service.update_comment(10, 5, 100, "Хак")

    @pytest.mark.asyncio
    async def test_should_delete_comment_by_author(self):
        # given
        service, spec_repo, project_repo, comment_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())
        comment_repo.get_by_id = AsyncMock(return_value=_comment(author_id=300))

        # when
        result = await service.delete_comment(10, 5, 300)

        # then
        assert result is True
        comment_repo.delete.assert_awaited_once_with(5)

    @pytest.mark.asyncio
    async def test_should_delete_comment_by_admin(self):
        # given — админ удаляет чужой комментарий
        service, spec_repo, project_repo, comment_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())
        comment_repo.get_by_id = AsyncMock(return_value=_comment(author_id=300))

        # when
        result = await service.delete_comment(10, 5, 600, is_admin=True)

        # then
        assert result is True

    @pytest.mark.asyncio
    async def test_should_delete_comment_by_teacher(self):
        # given — преподаватель удаляет чужой комментарий
        service, spec_repo, project_repo, comment_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100, workspace_id=42)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())
        spec_repo.uow.session.execute = AsyncMock(return_value=_resolved_row(Mock()))
        comment_repo.get_by_id = AsyncMock(return_value=_comment(author_id=300))

        # when
        result = await service.delete_comment(10, 5, 200)

        # then
        assert result is True

    @pytest.mark.asyncio
    async def test_should_deny_delete_comment_for_stranger(self):
        # given — посторонний пользователь
        service, spec_repo, project_repo, comment_repo = self._make_service()
        project_repo.get_by_id.return_value = _project(author_id=100)
        spec_repo.get_or_create_draft = AsyncMock(return_value=_spec())
        comment_repo.get_by_id = AsyncMock(return_value=_comment(author_id=300))

        # when / then
        with pytest.raises(PermissionError):
            await service.delete_comment(10, 5, 500)
