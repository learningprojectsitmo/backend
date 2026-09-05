from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from src.core.exceptions import NotFoundError, PermissionError, ValidationError
from src.model.notification import NotificationType
from src.model.project import Project, ProjectParticipation, ProjectStage, ProjectStatus, ProjectVacancy, Response
from src.model.settings import SpaceSettings
from src.model.user import Role, User
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
    from src.services.notification_service import NotificationService


class ProjectService(BaseService[Project, ProjectCreate, ProjectUpdate]):
    def __init__(
        self,
        project_repository: ProjectRepository,
        resume_repository: ResumeRepository | None = None,
        notification_service: NotificationService | None = None,
    ):
        super().__init__(project_repository)
        self._project_repository = project_repository
        self._resume_repository = resume_repository
        self._notification_service = notification_service

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
        # Уменьшаем количество необходимых участников для роли
        if invitation.vacancy_id:
            await self._project_repository.decrement_vacancy_count(invitation.vacancy_id)
        if self._notification_service and invitation.inviter_id and project:
            invitee = await self._project_repository.uow.session.get(User, user_id)
            actor_name = f"{invitee.first_name} {invitee.last_name or ''}".strip() if invitee else "User"
            await self._notification_service.create_notification(
                user_id=invitation.inviter_id,
                type=NotificationType.invitation_accepted,
                actor_name=actor_name,
                actor_id=user_id,
                project_id=invitation.project_id,
                project_name=project.name,
                vacancy_title=invitation.vacancy.title if invitation.vacancy else None,
                invitation_id=invitation_id,
            )
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
        if self._notification_service and invitation.inviter_id:
            project = await self._project_repository.get_by_id(invitation.project_id)
            invitee = await self._project_repository.uow.session.get(User, user_id)
            actor_name = f"{invitee.first_name} {invitee.last_name or ''}".strip() if invitee else "User"
            project_name = project.name if project else "Project"
            await self._notification_service.create_notification(
                user_id=invitation.inviter_id,
                type=NotificationType.invitation_rejected,
                actor_name=actor_name,
                actor_id=user_id,
                project_id=invitation.project_id,
                project_name=project_name,
                invitation_id=invitation_id,
            )
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
            theme=project.theme,
            description=project.description,
            participants_count=len(participants),
            progress=project.progress or 0,
            tags=tags,
            participants_preview=preview,
            author_id=project.author_id,
        )

    async def _resolve_workspace_deadline(self, workspace_id: int | None):
        """Получить дедлайн по умолчанию из настроек пространства (или None)."""
        if not workspace_id:
            return None
        space_settings = await self._project_repository.uow.session.execute(
            select(SpaceSettings).where(SpaceSettings.space_id == workspace_id)
        )
        settings = space_settings.scalar_one_or_none()
        return settings.default_project_deadline if settings else None

    async def _assign_initial_stage(self, project: Project) -> None:
        """Если у проекта выбран тип — ставим текущий этап = первый (или ожидание утверждения)."""
        if not project.project_type_id:
            return
        first_stage = await self._project_repository.uow.session.execute(
            select(ProjectStage)
            .where(ProjectStage.project_type_id == project.project_type_id)
            .order_by(ProjectStage.order)
            .limit(1)
        )
        stage = first_stage.scalar_one_or_none()
        if not stage:
            return
        project.current_stage_id = stage.id
        project.stage_pending_approval = stage.requires_approval

        all_stages = await self._project_repository.uow.session.execute(
            select(ProjectStage)
            .where(ProjectStage.project_type_id == project.project_type_id)
            .order_by(ProjectStage.order)
        )
        stage_list = list(all_stages.scalars().all())
        if stage_list:
            idx = next((i for i, s in enumerate(stage_list) if s.id == stage.id), 0)
            project.progress = round(((idx + 1) / len(stage_list)) * 100)

        await self._project_repository.uow.session.flush()

    async def create_project(self, project_data: ProjectCreate, author_id: int) -> Project:
        """Создать новый проект"""
        if not project_data.author_id:
            project_data.author_id = author_id

        # Только руководитель проекта (manager) может создавать проекты в workspace
        if project_data.workspace_id:
            ws_participation = await self._project_repository.uow.session.execute(
                select(WorkSpaceParticipation, Role)
                .join(Role, Role.id == WorkSpaceParticipation.role_id)
                .where(
                    WorkSpaceParticipation.workspace_id == project_data.workspace_id,
                    WorkSpaceParticipation.participant_id == author_id,
                )
            )
            row = ws_participation.first()
            if not row or row[1].name != "manager":
                raise PermissionError("Only a project manager (role 'manager') can create a project in this workspace")

            existing_count = await self._project_repository.uow.session.execute(
                select(func.count())
                .select_from(Project)
                .where(
                    Project.workspace_id == project_data.workspace_id,
                    Project.author_id == author_id,
                )
            )
            if existing_count.scalar_one() > 0:
                raise PermissionError("Вы уже создали проект в этом пространстве. Можно создать только один проект.")

        # Преобразуем в dict и вырезаем теги и вакансии
        payload = project_data.model_dump(exclude_none=True)
        tags_names = payload.pop("tags", None)
        vacancies_data = payload.pop("vacancies", None)

        # Дедлайн берётся из настроек пространства и всегда имеет приоритет
        workspace_deadline = await self._resolve_workspace_deadline(project_data.workspace_id)
        if workspace_deadline:
            payload["deadline"] = workspace_deadline

        # Черновик по умолчанию: если статус не указан, помечаем проект как draft
        if not payload.get("status_id"):
            draft_status = await self._project_repository.uow.session.execute(
                select(ProjectStatus).where(ProjectStatus.name == "draft")
            )
            draft = draft_status.scalar_one_or_none()
            if draft:
                payload["status_id"] = draft.id

        # 1. Создаем основной объект проекта
        project = await self._project_repository.create(payload)
        await self._project_repository.uow.session.flush()

        # Если выбран тип проекта — автоматически ставим текущий этап = первый
        await self._assign_initial_stage(project)

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
        await self._project_repository.uow.session.refresh(
            project, ["tags", "status", "vacancies", "participants", "project_type", "current_stage"]
        )

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

            await self._project_repository.uow.session.refresh(
                project, ["tags", "status", "participants", "vacancies", "project_type", "current_stage"]
            )

        return project

    async def remove_participant(self, project_id: int, participant_user_id: int, current_user_id: int) -> bool:
        project = await self.get_project_by_id(project_id)
        if not project:
            return False
        if project.author_id != current_user_id:
            raise PermissionError("Only project author can remove participants")
        # Увеличиваем количество мест в вакансии если участник был принят по роли
        accepted = await self._project_repository.get_accepted_response_for_participant(project_id, participant_user_id)
        if accepted and accepted.vacancy_id:
            await self._project_repository.increment_vacancy_count(accepted.vacancy_id)
        return await self._project_repository.remove_participant(project_id, participant_user_id)

    async def apply_for_project(
        self, project_id: int, user_id: int, vacancy_id: int | None = None, resume_id: int | None = None
    ) -> Response:
        """Откликнуться на проект"""
        project = await self._project_repository.get_by_id(project_id)
        if not project:
            raise NotFoundError("Project not found")
        if not resume_id:
            raise ValidationError("Resume is required to apply for a project")
        if self._resume_repository:
            resume = await self._resume_repository.get_by_id(resume_id)
            if not resume:
                raise ValidationError("Resume not found")
            if resume.author_id != user_id:
                raise ValidationError("You can only attach your own resume")
        if project.author_id == user_id:
            raise ValidationError("You cannot apply to your own project")
        if await self._project_repository.is_user_in_project(project_id, user_id):
            raise ValidationError("You are already a participant of this project")
        if await self._project_repository.has_pending_response(project_id, user_id):
            raise ValidationError("You already have a pending response for this project")
        if await self._project_repository.has_pending_invitation(project_id, user_id):
            raise ValidationError("You already have a pending invitation for this project")
        response = await self._project_repository.create_response(
            respondent_id=user_id,
            project_id=project_id,
            vacancy_id=vacancy_id,
            resume_id=resume_id,
            type="response",
        )
        if self._notification_service and project.author:
            user = await self._project_repository.uow.session.get(User, user_id)
            actor_name = f"{user.first_name} {user.last_name or ''}".strip() if user else "User"
            await self._notification_service.create_notification(
                user_id=project.author_id,
                type=NotificationType.response_received,
                actor_name=actor_name,
                actor_id=user_id,
                project_id=project_id,
                project_name=project.name,
                vacancy_title=response.vacancy.title if response.vacancy else None,
                response_id=response.id,
            )
        return response

    async def invite_to_project(
        self,
        project_id: int,
        inviter_id: int,
        invitee_id: int,
        vacancy_id: int | None = None,
        resume_id: int | None = None,
    ) -> Response:
        """Пригласить пользователя в проект"""
        project = await self._project_repository.get_by_id(project_id)
        if not project:
            raise NotFoundError("Project not found")
        if project.author_id != inviter_id:
            raise PermissionError("Only project author can invite")
        if await self._project_repository.is_user_in_project(project_id, invitee_id):
            raise ValidationError("User is already a participant of this project")
        if await self._project_repository.has_pending_response(project_id, invitee_id):
            raise ValidationError("User already has a pending response for this project")
        invitation = await self._project_repository.create_response(
            respondent_id=invitee_id,
            project_id=project_id,
            vacancy_id=vacancy_id,
            resume_id=resume_id,
            type="invitation",
            inviter_id=inviter_id,
        )
        if self._notification_service and project.author:
            actor_name = f"{project.author.first_name} {project.author.last_name or ''}".strip()
            await self._notification_service.create_notification(
                user_id=invitee_id,
                type=NotificationType.invitation_received,
                actor_name=actor_name,
                actor_id=inviter_id,
                project_id=project_id,
                project_name=project.name,
                vacancy_title=invitation.vacancy.title if invitation.vacancy else None,
                invitation_id=invitation.id,
            )
        return invitation

    async def accept_response(self, response_id: int, author_id: int) -> Response:
        """Принять отклик (автор проекта) — участник получает уведомление и решает, вступить ли"""
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
        if self._notification_service and project.author:
            actor_name = f"{project.author.first_name} {project.author.last_name or ''}".strip()
            await self._notification_service.create_notification(
                user_id=response.respondent_id,
                type=NotificationType.response_accepted,
                actor_name=actor_name,
                actor_id=author_id,
                project_id=response.project_id,
                project_name=project.name,
                vacancy_title=response.vacancy.title if response.vacancy else None,
                response_id=response.id,
            )
        return result

    async def confirm_join(self, response_id: int, user_id: int) -> Response:
        """Участник подтверждает вступление в проект после принятия отклика"""
        response = await self._project_repository.get_response_by_id(response_id)
        if not response:
            raise NotFoundError("Response not found")
        if response.respondent_id != user_id:
            raise PermissionError("This response is not yours")
        if response.type != "response":
            raise ValidationError("This is not a response")
        if response.status != "accepted":
            raise ValidationError("Can only confirm accepted responses")
        project = await self._project_repository.get_by_id(response.project_id)
        if project and project.max_participants is not None and len(project.participants) >= project.max_participants:
            raise ValidationError("Project has reached maximum number of participants")
        await self._project_repository.add_participant(response.project_id, user_id)
        if response.vacancy_id:
            await self._project_repository.decrement_vacancy_count(response.vacancy_id)
        return response

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
        if self._notification_service and project.author:
            actor_name = f"{project.author.first_name} {project.author.last_name or ''}".strip()
            await self._notification_service.create_notification(
                user_id=response.respondent_id,
                type=NotificationType.response_rejected,
                actor_name=actor_name,
                actor_id=author_id,
                project_id=response.project_id,
                project_name=project.name,
                response_id=response.id,
            )
        return result

    async def get_project_responses(self, project_id: int, author_id: int) -> list[Response]:
        """Получить все отклики проекта (только автор)"""
        project = await self._project_repository.get_by_id(project_id)
        if not project:
            raise NotFoundError("Project not found")
        if project.author_id != author_id:
            raise PermissionError("Only project author can view responses")
        return await self._project_repository.get_responses_by_project_id(project_id)

    async def delete_project(self, project_id: int, is_admin: bool = False) -> bool:
        """Удалить проект (только при наличии права project:delete)"""
        project = await self.get_project_by_id(project_id)
        if not project:
            return False

        if not is_admin:
            raise PermissionError("You don't have permission to delete this project")

        return await self._project_repository.delete(project_id)
