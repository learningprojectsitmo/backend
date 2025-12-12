from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from src.model.models import Project
from src.schema.project import ProjectCreate, ProjectUpdate
from src.services.base_service import BaseService
from src.repository.project_repository import ProjectRepository


class ProjectService(BaseService[Project, ProjectCreate, ProjectUpdate]):
    def __init__(self, project_repository: ProjectRepository, db_session: AsyncSession):
        super().__init__(project_repository)
        self._project_repository = project_repository
        self._db_session = db_session

    async def get_project_by_id(self, project_id: int) -> Optional[Project]:
        """Получить проект по ID"""
        return await self._project_repository.get_by_id(project_id)

    async def get_projects_by_author(self, author_id: int) -> List[Project]:
        """Получить проекты по автору"""
        return await self._project_repository.get_by_author_id(author_id)

    async def get_projects_paginated(self, page: int = 1, limit: int = 10) -> tuple[List[Project], int]:
        """Получить проекты с пагинацией"""
        skip = (page - 1) * limit
        projects = await self._project_repository.get_multi(skip=skip, limit=limit)
        total = await self._project_repository.count()
        return projects, total

    async def create_project(self, project_data: ProjectCreate, author_id: int) -> Project:
        """Создать новый проект"""
        if not project_data.author_id:
            project_data.author_id = author_id
        return await self._project_repository.create(project_data)

    async def update_project(self, project_id: int, project_data: ProjectUpdate, current_user_id: int) -> Optional[Project]:
        """Обновить проект (только автор может обновлять)"""
        project = await self.get_project_by_id(project_id)
        if not project:
            return None

        if project.author_id != current_user_id:
            raise PermissionError("Только автор проекта может его обновлять")

        return await self._project_repository.update(project_id, project_data)

    async def delete_project(self, project_id: int, current_user_id: int) -> bool:
        """Удалить проект (только автор может удалять)"""
        project = await self.get_project_by_id(project_id)
        if not project:
            return False

        if project.author_id != current_user_id:
            raise PermissionError("Только автор проекта может его удалять")

        return await self._project_repository.delete(project_id)