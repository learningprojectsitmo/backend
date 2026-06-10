from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from src.core.exceptions import NotFoundError, PermissionError, ValidationError
from src.model.project import Project, ProjectParticipation, ProjectVacancy, Response
from src.model.workspace import WorkSpaceParticipation
from src.schema.project import (
    MyInvitationItem,
    MyInvitationListResponse,
    MyProjectItem,
    MyProjectListResponse,
    MyResponseItem,
    MyResponseListResponse,
    ParticipantPreview,
    ProjectCreate,
    ProjectListItem,
    ProjectStatusItem,
    ProjectUpdate,
)
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.project_repository import ProjectRepository
    from src.repository.resume_repository import ResumeRepository


class ProjectService(BaseService[Project, ProjectCreate, ProjectUpdate]):
    def __init__(
        self,
        project_repository: ProjectRepository,
        resume_repository: ResumeRepository | None = None,
    ):
        super().__init__(project_repository)
        self._project_repository = project_repository
        self._resume_repository = resume_repository

    async def _get_user_resume_url(self, user_id: int) -> tuple[str, str]:
        """Получить URL и заголовок первого резюме пользователя"""
        if not self._resume_repository:
            return "", ""
        resumes = await self._resume_repository.get_by_author_id(user_id)
        if not resumes:
            return "", ""
        resume = resumes[0]
        return f"/resume/{resume.id}", resume.header or ""

    async def get_project_by_id(self, project_id: int) -> Project | None:
        """Получить проект по ID"""
        return await self._project_repository.get_by_id(project_id)

    async def get_projects_by_author(self, author_id: int) -> list[Project]:
        """Получить проекты по автору"""
        return await self._project_repository.get_by_author_id(author_id)

    async def get_my_responses(self, user_id: int) -> MyResponseListResponse:
        """Получить отклики текущего пользователя"""
        responses = await self._project_repository.get_responses_by_respondent_id(user_id)
        resume_url, resume_title = await self._get_user_resume_url(user_id)
        items = [
            MyResponseItem(
                id=r.id,
                project_id=r.project_id,
                project_name=r.project.name if r.project else "",
                description=r.project.description if r.project else "",
                role=r.vacancy.title if r.vacancy else "",
                resume_url=resume_url,
                resume_title=resume_title,
                date=r.created_at.isoformat() if r.created_at else "",
                status=r.status,
            )
            for r in responses
        ]
        return MyResponseListResponse(items=items, total=len(items))

    async def get_my_invitations(self, user_id: int) -> MyInvitationListResponse:
        """Получить приглашения текущего пользователя"""
        invitations = await self._project_repository.get_invitations_by_invitee_id(user_id)
        resume_url, resume_title = await self._get_user_resume_url(user_id)
        items = [
            MyInvitationItem(
                id=inv.id,
                project_id=inv.project_id,
                project_name=inv.project.name if inv.project else "",
                description=inv.project.description if inv.project else "",
                inviter_name=(f"{inv.inviter.first_name} {inv.inviter.last_name or ''}".strip() if inv.inviter else ""),
                role=inv.vacancy.title if inv.vacancy else "",
                resume_url=resume_url,
                resume_title=resume_title,
                date=inv.created_at.isoformat() if inv.created_at else "",
                status=inv.status,
            )
            for inv in invitations
        ]
        return MyInvitationListResponse(items=items, total=len(items))

    async def get_projects_by_ids(self, project_ids: list[int]) -> MyProjectListResponse:
        """Получить проекты по списку ID"""
        projects = await self._project_repository.get_projects_by_ids(project_ids)
        items = [
            MyProjectItem(
                id=p.id,
                title=p.name,
                description=p.description,
                status=p.status.name if p.status else "not_started",
                progress=p.progress or 0,
                start_date=p.created_at.isoformat() if p.created_at else "",
                members_count=len(p.participants or []),
                roles=[v.title for v in (p.vacancies or [])],
            )
            for p in projects
        ]
        return MyProjectListResponse(items=items, total=len(items))

    async def get_my_created_projects(self, user_id: int) -> MyProjectListResponse:
        """Получить проекты, созданные пользователем"""
        projects = await self.get_projects_by_author(user_id)
        items = [
            MyProjectItem(
                id=p.id,
                title=p.name,
                description=p.description,
                status=p.status.name if p.status else "not_started",
                progress=p.progress or 0,
                start_date=p.created_at.isoformat() if p.created_at else "",
                members_count=len(p.participants or []),
                roles=[v.title for v in (p.vacancies or [])],
            )
            for p in projects
        ]
        return MyProjectListResponse(items=items, total=len(items))

    async def get_my_projects(self, user_id: int) -> MyProjectListResponse:
        """Получить проекты, в которых участвует пользователь"""
        projects = await self._project_repository.get_projects_by_participant_id(user_id)
        items = [
            MyProjectItem(
                id=p.id,
                title=p.name,
                description=p.description,
                status=p.status.name if p.status else "not_started",
                progress=p.progress or 0,
                start_date=p.created_at.isoformat() if p.created_at else "",
                members_count=len(p.participants or []),
                roles=[v.title for v in (p.vacancies or [])],
            )
            for p in projects
        ]
        return MyProjectListResponse(items=items, total=len(items))

    async def withdraw_response(self, response_id: int, user_id: int) -> Response:
        """Отозвать отклик"""
        response = await self._project_repository.get_response_by_id(response_id)
        if not response:
            raise NotFoundError("Response not found")
        if response.respondent_id != user_id:
            raise PermissionError("You can only withdraw your own responses")
        if response.type != "response":
            raise ValidationError("This is not a response")
        if response.status != "pending":
            raise ValidationError("Can only withdraw pending responses")
        result = await self._project_repository.update_response_status(response_id, "withdrawn")
        if not result:
            raise NotFoundError("Response not found")
        return result

    async def accept_invitation(self, invitation_id: int, user_id: int) -> Response:
        """Принять приглашение"""
        invitation = await self._project_repository.get_response_by_id(invitation_id)
        if not invitation:
            raise NotFoundError("Invitation not found")
        if invitation.respondent_id != user_id:
            raise PermissionError("This invitation is not for you")
        if invitation.type != "invitation":
            raise ValidationError("This is not an invitation")
        if invitation.status != "pending":
            raise ValidationError("Can only accept pending invitations")
        project = await self._project_repository.get_by_id(invitation.project_id)
        if project and project.max_participants is not None and len(project.participants) >= project.max_participants:
            raise ValidationError("Project has reached maximum number of participants")
        result = await self._project_repository.update_response_status(invitation_id, "accepted")
        if not result:
            raise NotFoundError("Invitation not found")
        # Добавляем пользователя как участника проекта
        await self._project_repository.add_participant(invitation.project_id, user_id)
        return result

    async def reject_invitation(self, invitation_id: int, user_id: int) -> Response:
        """Отклонить приглашение"""
        invitation = await self._project_repository.get_response_by_id(invitation_id)
        if not invitation:
            raise NotFoundError("Invitation not found")
        if invitation.respondent_id != user_id:
            raise PermissionError("This invitation is not for you")
        if invitation.type != "invitation":
            raise ValidationError("This is not an invitation")
        if invitation.status != "pending":
            raise ValidationError("Can only reject pending invitations")
        result = await self._project_repository.update_response_status(invitation_id, "rejected")
        if not result:
            raise NotFoundError("Invitation not found")
        return result

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

        # Если проект принадлежит workspace — синхронизируем участие в workspace
        if project.workspace_id:
            existing = await self._project_repository.uow.session.execute(
                select(WorkSpaceParticipation).where(
                    WorkSpaceParticipation.workspace_id == project.workspace_id,
                    WorkSpaceParticipation.participant_id == author_id,
                )
            )
            if not existing.scalar_one_or_none():
                ws_participation = WorkSpaceParticipation(
                    workspace_id=project.workspace_id,
                    participant_id=author_id,
                )
                self._project_repository.uow.session.add(ws_participation)
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

    async def apply_for_project(self, project_id: int, user_id: int, vacancy_id: int | None = None) -> Response:
        """Откликнуться на проект"""
        project = await self._project_repository.get_by_id(project_id)
        if not project:
            raise NotFoundError("Project not found")
        if project.author_id == user_id:
            raise ValidationError("You cannot apply to your own project")
        if await self._project_repository.is_user_in_project(project_id, user_id):
            raise ValidationError("You are already a participant of this project")
        if await self._project_repository.has_pending_response(project_id, user_id):
            raise ValidationError("You already have a pending response for this project")
        return await self._project_repository.create_response(
            respondent_id=user_id,
            project_id=project_id,
            vacancy_id=vacancy_id,
            type="response",
        )

    async def invite_to_project(
        self, project_id: int, inviter_id: int, invitee_id: int, vacancy_id: int | None = None
    ) -> Response:
        """Пригласить пользователя в проект"""
        project = await self._project_repository.get_by_id(project_id)
        if not project:
            raise NotFoundError("Project not found")
        if project.author_id != inviter_id:
            raise PermissionError("Only project author can invite")
        if await self._project_repository.is_user_in_project(project_id, invitee_id):
            raise ValidationError("User is already a participant of this project")
        return await self._project_repository.create_response(
            respondent_id=invitee_id,
            project_id=project_id,
            vacancy_id=vacancy_id,
            type="invitation",
            inviter_id=inviter_id,
        )

    async def accept_response(self, response_id: int, author_id: int) -> Response:
        """Принять отклик (автор проекта) — создаёт приглашение для пользователя"""
        response = await self._project_repository.get_response_by_id(response_id)
        if not response:
            raise NotFoundError("Response not found")
        if response.type != "response":
            raise ValidationError("This is not a response")
        if response.status != "pending":
            raise ValidationError("Can only accept pending responses")
        project = await self._project_repository.get_by_id(response.project_id)
        if not project or project.author_id != author_id:
            raise PermissionError("Only project author can accept responses")
        if project.max_participants is not None and len(project.participants) >= project.max_participants:
            raise ValidationError("Project has reached maximum number of participants")
        result = await self._project_repository.update_response_status(response_id, "accepted")
        if not result:
            raise NotFoundError("Response not found")
        invitation = await self._project_repository.create_response(
            respondent_id=response.respondent_id,
            project_id=response.project_id,
            vacancy_id=response.vacancy_id,
            type="invitation",
            inviter_id=author_id,
        )
        return invitation

    async def reject_response(self, response_id: int, author_id: int) -> Response:
        """Отклонить отклик (автор проекта)"""
        response = await self._project_repository.get_response_by_id(response_id)
        if not response:
            raise NotFoundError("Response not found")
        if response.type != "response":
            raise ValidationError("This is not a response")
        if response.status != "pending":
            raise ValidationError("Can only reject pending responses")
        project = await self._project_repository.get_by_id(response.project_id)
        if not project or project.author_id != author_id:
            raise PermissionError("Only project author can reject responses")
        result = await self._project_repository.update_response_status(response_id, "rejected")
        if not result:
            raise NotFoundError("Response not found")
        return result

    async def get_project_responses(self, project_id: int, author_id: int) -> list[Response]:
        """Получить все отклики проекта (только автор)"""
        project = await self._project_repository.get_by_id(project_id)
        if not project:
            raise NotFoundError("Project not found")
        if project.author_id != author_id:
            raise PermissionError("Only project author can view responses")
        return await self._project_repository.get_responses_by_project_id(project_id)

    async def delete_project(self, project_id: int, current_user_id: int) -> bool:
        """Удалить проект (только автор может удалять)"""
        project = await self.get_project_by_id(project_id)
        if not project:
            return False

        if project.author_id != current_user_id:
            raise PermissionError("Only project author can delete project")

        return await self._project_repository.delete(project_id)
