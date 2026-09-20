from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from src.core.exceptions import NotFoundError, PermissionError, ValidationError
from src.model.project import Project, ProjectParticipation, SpecificationComment
from src.model.user import Role
from src.model.workspace import WorkSpaceParticipation
from src.schema.specification import SpecificationCommentResponse, SpecificationFull, SpecificationUpdate
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.project_repository import ProjectRepository
    from src.repository.specification_repository import SpecificationCommentRepository, SpecificationRepository


class SpecificationService(BaseService[object, object, SpecificationUpdate]):
    """Сервис технического задания проекта.

    Статусная модель:
        draft     — автор может редактировать;
        submitted — автор отправил ТЗ на утверждение (advance со стадии «Создание тз»);
        approved  — преподаватель утвердил ТЗ (approve стадии «Утверждение тз»).
    """

    def __init__(
        self,
        specification_repository: SpecificationRepository,
        project_repository: ProjectRepository | None = None,
        comment_repository: SpecificationCommentRepository | None = None,
    ) -> None:
        super().__init__(specification_repository)
        self._specification_repository = specification_repository
        self._project_repository = project_repository
        self._comment_repository = comment_repository

    async def _get_project(self, project_id: int) -> Project:
        if not self._project_repository:
            raise NotFoundError("Project not found")
        project = await self._project_repository.get_by_id(project_id)
        if not project:
            raise NotFoundError("Project not found")
        return project

    async def _is_workspace_editor(self, user_id: int, workspace_id: int | None) -> bool:
        if not workspace_id:
            return False
        result = await self._specification_repository.uow.session.execute(
            select(WorkSpaceParticipation)
            .join(Role, Role.id == WorkSpaceParticipation.role_id)
            .where(
                WorkSpaceParticipation.workspace_id == workspace_id,
                WorkSpaceParticipation.participant_id == user_id,
                Role.name.in_(("admin", "teacher")),
            )
        )
        return result.first() is not None

    async def _is_participant(self, project_id: int, user_id: int) -> bool:
        result = await self._specification_repository.uow.session.execute(
            select(ProjectParticipation).where(
                ProjectParticipation.project_id == project_id,
                ProjectParticipation.participant_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _can_view(self, project: Project, user_id: int) -> bool:
        return (
            project.author_id == user_id
            or await self._is_workspace_editor(user_id, project.workspace_id)
            or await self._is_participant(project.id, user_id)
        )

    async def _can_comment(self, project: Project, user_id: int, *, is_admin: bool = False) -> bool:
        return (
            is_admin or project.author_id == user_id or await self._is_workspace_editor(user_id, project.workspace_id)
        )

    async def _resolve_comment(self, spec_id: int, comment_id: int) -> SpecificationComment:
        if not self._comment_repository:
            raise NotFoundError("Comment not found")
        comment = await self._comment_repository.get_by_id(comment_id)
        if not comment or comment.specification_id != spec_id:
            raise NotFoundError("Comment not found")
        return comment

    async def get_or_create(self, project_id: int) -> object:
        """Получить ТЗ проекта; при отсутствии создать пустой черновик."""
        return await self._specification_repository.get_or_create_draft(project_id)

    async def get_specification(self, project_id: int, user_id: int) -> SpecificationFull:
        project = await self._get_project(project_id)
        if not await self._can_view(project, user_id):
            raise PermissionError("You do not have access to this project's specification")
        spec = await self.get_or_create(project_id)
        return SpecificationFull.model_validate(spec)

    async def update_specification(
        self,
        project_id: int,
        user_id: int,
        data: SpecificationUpdate,
    ) -> SpecificationFull:
        project = await self._get_project(project_id)
        if project.author_id != user_id:
            raise PermissionError("Only project author can update the specification")

        spec = await self.get_or_create(project_id)
        if spec.status != "draft":
            raise ValidationError("Specification can only be edited in draft status")

        payload: dict = {}
        for field in ("goal", "tasks", "acceptance_criteria"):
            value = getattr(data, field, None)
            if value is None:
                continue
            if isinstance(value, list):
                value = [str(item).strip() for item in value if str(item).strip()]
            payload[field] = value
        for field in ("functional_requirements", "non_functional_requirements"):
            groups = getattr(data, field, None)
            if groups is None:
                continue
            cleaned_groups: list[dict] = []
            for group in groups:
                name = (group.name or "").strip()
                items = [str(item).strip() for item in (group.requirements or []) if str(item).strip()]
                if name and items:
                    cleaned_groups.append({"name": name, "requirements": items})
            payload[field] = cleaned_groups
        if payload:
            for field, value in payload.items():
                setattr(spec, field, value)
            await self._specification_repository.uow.session.flush()
            await self._specification_repository.uow.session.refresh(spec)
        return SpecificationFull.model_validate(spec)

    async def get_comments(self, project_id: int, user_id: int) -> list[SpecificationCommentResponse]:
        project = await self._get_project(project_id)
        if not await self._can_view(project, user_id):
            raise PermissionError("You do not have access to this project's specification")
        spec = await self.get_or_create(project_id)
        if not self._comment_repository:
            return []
        comments = await self._comment_repository.get_by_specification_id(spec.id)
        return [
            SpecificationCommentResponse(
                id=c.id,
                specification_id=c.specification_id,
                author={"id": c.author.id, "username": c.author.first_name or "Unknown"},
                text=c.text,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in comments
        ]

    async def add_comment(
        self,
        project_id: int,
        user_id: int,
        text: str,
        *,
        is_admin: bool = False,
    ) -> SpecificationComment:
        project = await self._get_project(project_id)
        if not await self._can_comment(project, user_id, is_admin=is_admin):
            raise PermissionError("Only project author, teacher or admin can comment")
        spec = await self.get_or_create(project_id)
        comment = SpecificationComment(specification_id=spec.id, author_id=user_id, text=text.strip())
        self._specification_repository.uow.session.add(comment)
        await self._specification_repository.uow.session.flush()
        return comment

    async def update_comment(
        self,
        project_id: int,
        comment_id: int,
        user_id: int,
        text: str,
    ) -> SpecificationComment:
        project = await self._get_project(project_id)
        if not await self._can_view(project, user_id):
            raise PermissionError("You do not have access to this project's specification")
        spec = await self.get_or_create(project_id)
        comment = await self._resolve_comment(spec.id, comment_id)
        if comment.author_id != user_id:
            raise PermissionError("Only comment author can edit the comment")
        comment.text = text.strip()
        await self._specification_repository.uow.session.flush()
        return comment

    async def delete_comment(
        self,
        project_id: int,
        comment_id: int,
        user_id: int,
        *,
        is_admin: bool = False,
    ) -> bool:
        project = await self._get_project(project_id)
        if not await self._can_view(project, user_id):
            raise PermissionError("You do not have access to this project's specification")
        spec = await self.get_or_create(project_id)
        comment = await self._resolve_comment(spec.id, comment_id)
        is_workspace_editor = await self._is_workspace_editor(user_id, project.workspace_id)
        if comment.author_id != user_id and not is_admin and not is_workspace_editor:
            raise PermissionError("Only comment author, teacher or admin can delete the comment")
        if not self._comment_repository:
            raise NotFoundError("Comment repository is not configured")
        return await self._comment_repository.delete(comment.id)
