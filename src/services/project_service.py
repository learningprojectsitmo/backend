from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.exceptions import PermissionError, ValidationError
from src.model.project import Project, ProjectParticipation, ProjectVacancy
from src.schema.project import (
    ParticipantPreview,
    ProjectCreate,
    ProjectListItem,
    ProjectStatusItem,
    ProjectUpdate,
)
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.project_repository import ProjectRepository


class ProjectService(BaseService[Project, ProjectCreate, ProjectUpdate]):
    def __init__(self, project_repository: ProjectRepository):
        super().__init__(project_repository)
        self._project_repository = project_repository

    async def get_project_by_id(self, project_id: int) -> Project | None:
        """Получить проект по ID"""
        return await self._project_repository.get_by_id(project_id)

    async def get_projects_by_author(self, author_id: int) -> list[Project]:
        """Получить проекты по автору"""
        return await self._project_repository.get_by_author_id(author_id)

    async def get_projects_by_workspace(
        self, workspace_id: int, page: int = 1, limit: int = 10
    ) -> tuple[list[Project], int]:
        skip = (page - 1) * limit
        projects = await self._project_repository.get_projects_by_workspace(workspace_id, skip=skip, limit=limit)
        total = await self._project_repository.count_by_workspace(workspace_id)
        return projects, total

    async def get_projects_paginated(self, page: int = 1, limit: int = 10) -> tuple[list[Project], int]:
        """Получить проекты с пагинацией"""
        skip = (page - 1) * limit
        projects = await self._project_repository.get_projects_with_details(skip=skip, limit=limit)
        total = await self._project_repository.count()
        return projects, total

    def to_project_list_item(self, project: Project) -> ProjectListItem:
        participants = project.participants or []
        preview: list[ParticipantPreview] = []
        for relation in participants[:3]:
            user = relation.participant
            if not user:
                continue
            full_name = (
                " ".join(
                    part for part in (getattr(user, "first_name", ""), getattr(user, "last_name", "")) if part
                ).strip()
                or "Unknown"
            )
            preview.append(
                ParticipantPreview(
                    id=user.id,
                    full_name=full_name,
                    avatar_url=getattr(user, "avatar_url", None),
                )
            )

        status = project.status
        status_data = ProjectStatusItem(
            name=status.name if status else "draft",
            color=status.color if status else "#999999",
        )

        tags = [tag.name for tag in getattr(project, "tags", []) or []]

        return ProjectListItem(
            id=project.id,
            name=project.name,
            status=status_data,
            deadline=project.deadline,
            description=project.description,
            participants_count=len(participants),
            progress=project.progress or 0,
            tags=tags,
            participants_preview=preview,
        )

    async def create_project(self, project_data: ProjectCreate, author_id: int) -> Project:
        """Создать новый проект"""
        if not project_data.author_id:
            project_data.author_id = author_id

        # Преобразуем в dict и вырезаем теги и вакансии
        payload = project_data.model_dump(exclude_none=True)
        tags_names = payload.pop("tags", None)
        vacancies_data = payload.pop("vacancies", None)

        # 1. Создаем основной объект проекта
        project = await self._project_repository.create(payload)
        await self._project_repository.uow.session.flush()

        # Подгружаем и теги, и статус сразу, чтобы Pydantic не спотыкался
        await self._project_repository.uow.session.refresh(project, ["tags", "status"])

        if tags_names:
            project.tags = await self._project_repository.get_or_create_tags(tags_names)
            await self._project_repository.uow.session.flush()

        if vacancies_data:
            for v in vacancies_data:
                vacancy = ProjectVacancy(
                    project_id=project.id,
                    title=v["title"],
                    tasks=v.get("tasks", []),
                    required_count=v.get("required_count", 1),
                )
                self._project_repository.uow.session.add(vacancy)
            await self._project_repository.uow.session.flush()

        # Добавляем автора как участника проекта
        participation = ProjectParticipation(
            project_id=project.id,
            participant_id=author_id,
        )
        self._project_repository.uow.session.add(participation)
        await self._project_repository.uow.session.flush()

        # Чтобы Pydantic увидел обновленные связи после flush
        await self._project_repository.uow.session.refresh(project, ["tags", "status", "vacancies", "participants"])

        return project

    async def update_project(
        self,
        project_id: int,
        project_data: ProjectUpdate,
        current_user_id: int,
    ) -> Project | None:
        """Обновить проект (только автор может обновлять)"""
        project = await self.get_project_by_id(project_id)
        if not project:
            return None

        if project.author_id != current_user_id:
            raise PermissionError("Only project author can update project")

        payload = project_data.model_dump(exclude_none=True)
        tags_names = payload.pop("tags", None)
        vacancies_data = payload.pop("vacancies", None)

        project = await self._project_repository.update(project_id, payload)

        if project is not None:
            # Важно подгрузить текущие теги перед обновлением
            await self._project_repository.uow.session.refresh(project, ["tags", "status", "vacancies"])

            if tags_names is not None:
                project.tags = await self._project_repository.get_or_create_tags(tags_names)
                await self._project_repository.uow.session.flush()

            if vacancies_data is not None:
                total_required = sum(v.get("required_count", 1) for v in vacancies_data)
                if project.max_participants is not None and total_required > project.max_participants:
                    raise ValidationError(
                        f"Сумма необходимых участников ({total_required}) превышает максимальное количество ({project.max_participants})",
                    )

                # Удаляем старые вакансии и создаём новые
                for old_v in project.vacancies:
                    await self._project_repository.uow.session.delete(old_v)
                await self._project_repository.uow.session.flush()

                for v in vacancies_data:
                    vacancy = ProjectVacancy(
                        project_id=project.id,
                        title=v["title"],
                        tasks=v.get("tasks", []),
                        required_count=v.get("required_count", 1),
                    )
                    self._project_repository.uow.session.add(vacancy)
                await self._project_repository.uow.session.flush()

            await self._project_repository.uow.session.refresh(project, ["tags", "status", "participants", "vacancies"])

        return project

    async def remove_participant(self, project_id: int, participant_user_id: int, current_user_id: int) -> bool:
        project = await self.get_project_by_id(project_id)
        if not project:
            return False
        if project.author_id != current_user_id:
            raise PermissionError("Only project author can remove participants")
        return await self._project_repository.remove_participant(project_id, participant_user_id)

    async def delete_project(self, project_id: int, current_user_id: int) -> bool:
        """Удалить проект (только автор может удалять)"""
        project = await self.get_project_by_id(project_id)
        if not project:
            return False

        if project.author_id != current_user_id:
            raise PermissionError("Only project author can delete project")

        return await self._project_repository.delete(project_id)
