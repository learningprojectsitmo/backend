from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from sqlalchemy import select

from src.core.exceptions import PermissionError
from src.model.user import Role, User
from src.model.workspace import WorkSpace, WorkSpaceCategories
from src.schema.workspace import WorkSpaceCreate, WorkSpaceUpdate
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.workspace_repository import WorkSpaceRepository


class WorkSpaceService(BaseService[WorkSpace, WorkSpaceCreate, WorkSpaceUpdate]):
    # Роль автора при создании пространства зависит от глобальной роли:
    # admin → admin, teacher → teacher, member/manager → manager (автор управляет своим пространством).
    AUTHOR_ROLE_BY_GLOBAL: ClassVar[dict[str, str]] = {"admin": "admin", "teacher": "teacher"}

    def __init__(self, workspace_repository: WorkSpaceRepository):
        super().__init__(workspace_repository)
        self._workspace_repository = workspace_repository

    async def get_workspace_by_id(self, workspace_id: int) -> WorkSpace | None:
        """Получить workspace по ID"""
        return await self._workspace_repository.get_by_id(workspace_id)

    async def get_workspaces_by_author(self, author_id: int) -> list[WorkSpace]:
        """Получить все workspace по автору"""
        return await self._workspace_repository.get_by_author_id(author_id)

    async def get_workspaces_by_status(self, status_id: int) -> list[WorkSpace]:
        """Получить все workspace по статусу"""
        return await self._workspace_repository.get_by_status_id(status_id)

    async def get_workspaces_paginated(self, page: int = 1, limit: int = 10) -> tuple[list[WorkSpace], int]:
        """Получить workspace с пагинацией"""
        skip = (page - 1) * limit
        workspaces = await self._workspace_repository.get_multi(skip=skip, limit=limit)
        total = await self._workspace_repository.count()
        return workspaces, total

    async def create_workspace(self, workspace_data: WorkSpaceCreate, author_id: int) -> WorkSpace:
        """Создать новый workspace и добавить автора в участники.

        Роль автора в пространстве определяется его глобальной ролью
        (admin → admin, teacher → teacher, остальные → manager).
        """
        if not workspace_data.author_id:
            workspace_data.author_id = author_id
        if not workspace_data.status_id:
            workspace_data.status_id = 1
        workspace = await self._workspace_repository.create(workspace_data)

        role_name = await self._resolve_author_role_name(author_id)
        role_result = await self._workspace_repository.uow.session.execute(select(Role).where(Role.name == role_name))
        role = role_result.scalar_one_or_none()
        await self._workspace_repository.add_participation(workspace.id, author_id, role.id if role else None)
        return workspace

    async def _resolve_author_role_name(self, author_id: int) -> str:
        """Вернуть роль в пространстве для автора по его глобальной роли"""
        result = await self._workspace_repository.uow.session.execute(
            select(Role.name).join(User, User.role_id == Role.id).where(User.id == author_id)
        )
        global_role = result.scalar_one_or_none() or "member"
        return self.AUTHOR_ROLE_BY_GLOBAL.get(global_role, "manager")

    async def update_workspace(
        self,
        workspace_id: int,
        workspace_data: WorkSpaceUpdate,
        current_user_id: int,
    ) -> WorkSpace | None:
        """Обновить workspace (только автор может обновлять)"""
        workspace = await self.get_workspace_by_id(workspace_id)
        if not workspace:
            return None

        if workspace.author_id != current_user_id:
            raise PermissionError("Only workspace author can update workspace")

        return await self._workspace_repository.update(workspace_id, workspace_data)

    async def delete_workspace(self, workspace_id: int, current_user_id: int) -> bool:
        """Удалить workspace (только автор может удалять)"""
        workspace = await self.get_workspace_by_id(workspace_id)
        if not workspace:
            return False

        if workspace.author_id != current_user_id:
            raise PermissionError("Only workspace author can delete workspace")

        return await self._workspace_repository.delete(workspace_id)

    async def get_workspaces_with_stats(self, skip: int = 0, limit: int = 10) -> tuple[list[WorkSpace], int]:
        """Получить workspace с подсчетом статистики"""
        return await self._workspace_repository.get_workspaces_with_stats(skip, limit)

    async def get_workspaces_menu_data(self, user_id: int, skip: int = 0, limit: int = 10) -> tuple[list[dict], int]:
        """Получить данные для меню workspace (только видимые пользователю)"""
        return await self._workspace_repository.get_workspaces_menu_data(user_id, skip, limit)

    async def search_spaces_by_text(self, query: str, user_id: int, limit: int = 10) -> list[dict]:
        """Поиск видимых пользователю пространств по названию"""
        return await self._workspace_repository.search_by_text(query, user_id, limit=limit)

    async def get_workspace_participants_count(self, workspace_id: int) -> int:
        """Получить количество участников workspace"""
        return await self._workspace_repository.get_participants_count(workspace_id)

    async def get_workspace_participants(
        self,
        workspace_id: int,
        skip: int = 0,
        limit: int = 10,
        search: str | None = None,
        project_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[list[dict], int]:
        """Получить участников workspace с пагинацией и фильтрацией"""
        return await self._workspace_repository.get_participants(
            workspace_id, skip, limit, search, project_id, date_from, date_to
        )

    async def remove_workspace_participant(self, workspace_id: int, user_id: int, current_user_id: int) -> bool:
        """Удалить участника из workspace (только автор или админ/менеджер)"""
        workspace = await self._workspace_repository.get_by_id(workspace_id)
        if not workspace:
            return False

        if workspace.author_id != current_user_id:
            raise PermissionError("Only workspace author can remove participants")

        return await self._workspace_repository.remove_participant(workspace_id, user_id)

    async def get_workspace_resumes(
        self,
        workspace_id: int,
        search: str | None = None,
        skills: list[str] | None = None,
        interests: list[str] | None = None,
        skip: int = 0,
        limit: int = 10,
        default_only: bool = False,
    ) -> tuple[list[dict], int]:
        """Получить видимые резюме участников workspace с фильтрацией и пагинацией"""
        return await self._workspace_repository.get_workspace_resumes(
            workspace_id, search, skills, interests, skip, limit, default_only=default_only
        )

    async def get_workspace_resume_filters(self, workspace_id: int) -> dict[str, list[str]]:
        """Получить доступные скиллы и интересы для фильтрации резюме workspace"""
        return await self._workspace_repository.get_workspace_resume_filters(workspace_id)

    async def get_all_categories(self) -> list:
        """Получить все категории workspace"""
        return await self._workspace_repository.get_all_categories()

    async def get_workspace_category_name(self, category_id: int) -> str | None:
        """Получить имя категории по ID"""
        return await self._workspace_repository.get_category_name(category_id)

    async def get_or_create_category(self, category_data: dict) -> WorkSpaceCategories:
        """Получить категорию или создать если не существует"""
        return await self._workspace_repository.get_or_create_category(category_data)
