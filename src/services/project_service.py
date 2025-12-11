
from sqlalchemy.orm import Session

from schemas import ProjectCreate, ProjectUpdate
from src.model.models import Project
from src.repository.project_repository import ProjectRepository
from src.services.base_service import BaseService


class ProjectService(BaseService[Project, ProjectCreate, ProjectUpdate]):
    def __init__(self, project_repository: ProjectRepository, db_session: Session):
        super().__init__(project_repository)
        self._project_repository = project_repository
        self._db_session = db_session

    def get_project_by_id(self, project_id: int) -> Project | None:
        """Получить проект по ID"""
        return self._project_repository.get_by_id(project_id)

    def get_projects_by_author(self, author_id: int) -> list[Project]:
        """Получить проекты автора"""
        return self._project_repository.get_by_author_id(author_id)

    def get_projects_paginated(self, page: int = 1, limit: int = 10) -> tuple[list[Project], int]:
        """Получить проекты с пагинацией"""
        skip = (page - 1) * limit
        projects = self._project_repository.get_multi(skip=skip, limit=limit)
        total = self._project_repository.count()
        return projects, total

    def create_project(self, project_data: ProjectCreate, author_id: int) -> Project:
        """Создать новый проект"""
        if not project_data.author_id:
            project_data.author_id = author_id
        return self._project_repository.create(project_data)

    def update_project(self, project_id: int, project_data: ProjectUpdate, current_user_id: int) -> Project | None:
        """Обновить проект (только автор может обновлять)"""
        project = self.get_project_by_id(project_id)
        if not project:
            return None

        if project.author_id != current_user_id:
            raise PermissionError("Только автор проекта может его обновлять")

        return self._project_repository.update(project_id, project_data)

    def delete_project(self, project_id: int, current_user_id: int) -> bool:
        """Удалить проект (только автор может удалять)"""
        project = self.get_project_by_id(project_id)
        if not project:
            return False

        if project.author_id != current_user_id:
            raise PermissionError("Только автор проекта может его удалять")

        return self._project_repository.delete(project_id)
