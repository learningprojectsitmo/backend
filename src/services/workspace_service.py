from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from src.core.exceptions import PermissionError
from src.model.workspace import WorkSpace, WorkSpaceCategories
from src.schema.workspace import WorkSpaceCreate, WorkSpaceUpdate
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.workspace_repository import WorkSpaceRepository


class WorkSpaceService(BaseService[WorkSpace, WorkSpaceCreate, WorkSpaceUpdate]):
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
        """Создать новый workspace"""
        if not workspace_data.author_id:
            workspace_data.author_id = author_id
        return await self._workspace_repository.create(workspace_data)

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

    async def get_workspaces_with_stats(
        self, skip: int = 0, limit: int = 10
    ) -> tuple[list[WorkSpace], int]:
        """Получить workspace с подсчетом статистики"""
        return await self._workspace_repository.get_workspaces_with_stats(skip, limit)

    async def get_workspaces_menu_data(
        self, skip: int = 0, limit: int = 10
    ) -> tuple[list[dict], int]:
        """Получить данные для меню workspace (оптимизированный запрос)"""
        return await self._workspace_repository.get_workspaces_menu_data(skip, limit)

    async def get_workspace_participants_count(self, workspace_id: int) -> int:
        """Получить количество участников workspace"""
        from src.model.workspace import WorkSpaceParticipation

        result = await self._workspace_repository.uow.session.execute(
            select(func.count()).where(WorkSpaceParticipation.workspace_id == workspace_id)
        )
        return result.scalar()

    async def get_all_categories(self) -> list:
        """Получить все категории workspace"""
        from src.model.workspace import WorkSpaceCategories

        result = await self._workspace_repository.uow.session.execute(
            select(WorkSpaceCategories).order_by(WorkSpaceCategories.id)
        )
        return list(result.scalars().all())

    async def get_workspace_category_name(self, category_id: int) -> str | None:
        """Получить имя категории по ID"""
        from src.model.workspace import WorkSpaceCategories

        result = await self._workspace_repository.uow.session.execute(
            select(WorkSpaceCategories).where(WorkSpaceCategories.id == category_id)
        )
        category = result.scalar_one_or_none()
        return category.name if category else None

    async def get_or_create_category(self, category_data: dict) -> WorkSpaceCategories:
        """Получить категорию или создать если не существует"""
        from src.model.workspace import WorkSpaceCategories

        result = await self._workspace_repository.uow.session.execute(
            select(WorkSpaceCategories).where(WorkSpaceCategories.name == category_data["name"])
        )
        existing = result.scalar_one_or_none()

        if existing:
            return existing

        category = WorkSpaceCategories(**category_data)
        self._workspace_repository.uow.session.add(category)
        return category
