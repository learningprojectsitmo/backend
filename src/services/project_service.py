from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

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
    ProjectFull,
    ProjectListItem,
    ProjectStatusItem,
    ProjectUpdate,
    ResponseListItem,
    ResponseListResponse,
    resolve_busy_status,
    resolve_status_fields,
)
from src.services.base_service import BaseService
from src.util.urls import build_resume_url

if TYPE_CHECKING:
    from src.repository.project_repository import ProjectRepository
    from src.repository.resume_repository import ResumeRepository
    from src.services.mail_service import MailService
    from src.services.notification_service import NotificationService

# Роли в пространстве, которым разрешено создавать проекты (совпадает с stage_service.MANAGE_ROLES).
PROJECT_CREATE_ROLES: frozenset[str] = frozenset({"teacher", "admin", "manager"})

#: Глобальные роли, которым доступен общий список откликов и приглашений.
#: Менеджер пространства отклики чужих проектов не видит: он ими не управляет.
RESPONSE_LIST_ROLES: frozenset[str] = frozenset({"admin", "teacher"})


def _user_full_name(user: User | None) -> str:
    """Отображаемое имя пользователя; пустая строка вместо ``None``."""
    if not user:
        return ""
    return f"{user.first_name or ''} {user.last_name or ''}".strip()


class ProjectService(BaseService[Project, ProjectCreate, ProjectUpdate]):
    def __init__(
        self,
        project_repository: ProjectRepository,
        resume_repository: ResumeRepository | None = None,
        notification_service: NotificationService | None = None,
        mail_service: MailService | None = None,
    ):
        super().__init__(project_repository)
        self._project_repository = project_repository
        self._resume_repository = resume_repository
        self._notification_service = notification_service
        self._mail_service = mail_service

    @staticmethod
    def is_draft(project: Project) -> bool:
        """Проект скрыт от участников: не начат либо текущий этап не виден участникам."""
        stages = (project.project_type.stages if project.project_type else []) or []
        if not stages:
            return False
        if project.current_stage_id is None:
            return True
        for s in stages:
            if s.id == project.current_stage_id:
                return not s.visible_to_participants
        return True

    async def _visible_projects(self, projects: list[Project], viewer_id: int) -> list[Project]:
        """Скрыть черновики от всех, кроме автора и редакторов пространства (admin/teacher)."""
        editor_workspace_ids: set[int] = set()
        draft_workspace_ids = {p.workspace_id for p in projects if self.is_draft(p) and p.workspace_id}
        if draft_workspace_ids:
            editor_workspace_ids = await self._editor_workspace_ids(viewer_id, draft_workspace_ids)
        return [
            p
            for p in projects
            if not (self.is_draft(p) and p.author_id != viewer_id and p.workspace_id not in editor_workspace_ids)
        ]

    @staticmethod
    def draft_criterion() -> ColumnElement[bool]:
        """SQL-эквивалент :meth:`is_draft` — проект скрыт от участников.

        Нужен, чтобы отфильтровать черновики до пагинации: иначе страница
        приходит уже обрезанной по limit, а total считается по ней же.
        """
        has_stages = Project.project_type_id.in_(select(ProjectStage.project_type_id))
        hidden_stage = Project.current_stage_id.in_(
            select(ProjectStage.id).where(ProjectStage.visible_to_participants.is_(False))
        )
        return and_(has_stages, or_(Project.current_stage_id.is_(None), hidden_stage))

    async def _visible_projects_criterion(
        self, viewer_id: int | None, workspace_ids: set[int] | None
    ) -> ColumnElement[bool] | None:
        """Критерий видимости проектов для выборки с пагинацией.

        ``workspace_ids=None`` — проекты всех пространств (тогда проверяем роль
        во всех пространствах, где пользователь состоит).
        """
        if viewer_id is None:
            return None

        visible = or_(
            ~self.draft_criterion(),
            Project.author_id == viewer_id,
        )
        editor_workspace_ids = await self._editor_workspace_ids(viewer_id, workspace_ids)
        if editor_workspace_ids:
            visible = or_(visible, Project.workspace_id.in_(editor_workspace_ids))
        return visible

    async def _editor_workspace_ids(self, user_id: int, workspace_ids: set[int] | None) -> set[int]:
        """ID пространств, в которых пользователь имеет роль admin/teacher (видит черновики)."""
        if workspace_ids is not None and not workspace_ids:
            return set()
        stmt = (
            select(WorkSpaceParticipation.workspace_id)
            .join(Role, Role.id == WorkSpaceParticipation.role_id)
            .where(
                WorkSpaceParticipation.participant_id == user_id,
                Role.name.in_(("admin", "teacher")),
            )
        )
        if workspace_ids is not None:
            stmt = stmt.where(WorkSpaceParticipation.workspace_id.in_(workspace_ids))
        result = await self._project_repository.uow.session.execute(stmt)
        return set(result.scalars().all())

    async def is_workspace_editor(self, user_id: int, workspace_id: int | None) -> bool:
        """Является ли пользователь редактором (admin/teacher) в указанном пространстве."""
        if not workspace_id:
            return False
        result = await self._project_repository.uow.session.execute(
            select(WorkSpaceParticipation)
            .join(Role, Role.id == WorkSpaceParticipation.role_id)
            .where(
                WorkSpaceParticipation.workspace_id == workspace_id,
                WorkSpaceParticipation.participant_id == user_id,
                Role.name.in_(("admin", "teacher")),
            )
        )
        return result.first() is not None

    async def _get_user_resume_url(self, user_id: int) -> tuple[str, str]:
        """Получить URL и заголовок первого резюме пользователя.

        Контекст пространства здесь не подставляется: ответы и приглашения
        относятся к разным проектам, и единственный workspaceId ввёл бы
        breadcrumb в чужое пространство.
        """
        if not self._resume_repository:
            return "", ""
        resumes = await self._resume_repository.get_by_author_id(user_id)
        if not resumes:
            return "", ""
        resume = resumes[0]
        return build_resume_url(resume.id), resume.header or ""

    async def get_project_by_id(self, project_id: int) -> Project | None:
        """Получить проект по ID"""
        return await self._project_repository.get_by_id(project_id)

    async def build_full(self, project: Project, current_user_id: int | None = None) -> ProjectFull:
        """Собрать :class:`ProjectFull` с производными статусами откликов.

        Единая точка сборки для всех эндпоинтов, отдающих карточку проекта: сам
        статус «уже в другой команде» зависит от двух внешних факторов — занятости
        участника и настройки пространства, — которые нельзя узнать из ORM-объекта.
        Если собрать ``ProjectFull.from_orm`` напрямую (как было раньше), статус
        откатывается к сырому значению из БД в одном из ответов API.
        """
        allow_multi = await self._workspace_allows_multi_participation(project.workspace_id)
        busy_user_ids = (
            set()
            if allow_multi
            else await self._project_repository.get_workspace_busy_participant_ids(project.workspace_id, project.id)
        )
        return ProjectFull.from_orm(project, current_user_id, allow_multi, busy_user_ids)

    async def get_projects_by_author(self, author_id: int) -> list[Project]:
        """Получить проекты по автору"""
        return await self._project_repository.get_by_author_id(author_id)

    async def _resolve_busy_by_project(
        self, user_id: int, items: list[tuple[int, int | None]]
    ) -> tuple[dict[int, bool], dict[int | None, bool]]:
        """Занят ли пользователь в другом проекте пространства — по id проекта.

        Возвращает пару: занятость по каждому проекту из ``items`` и флаги
        ``allow_multi_project_participation`` по пространствам. Отклики в профиле
        смешаны из разных пространств, поэтому занятость нельзя посчитать одним
        общим флагом: она всегда определяется внутри пространства самого отклика.
        Все проекты пользователя выбираются одним запросом, дальше сравнение идёт
        в Python.

        Флаги пространств отдаются вместе с занятостью, чтобы вызывающая сторона
        не повторяла тот же запрос к space_settings вторым разом.
        """
        if not items:
            return {}, {}
        scopes = await self._project_repository.get_user_project_scopes(user_id)
        if not scopes:
            return {}, {}

        workspace_flags = await self._resolve_allow_multi_participation_batch({w for _, w in scopes})
        user_projects_by_workspace: dict[int | None, set[int]] = {}
        for project_id, workspace_id in scopes:
            user_projects_by_workspace.setdefault(workspace_id, set()).add(project_id)

        busy: dict[int, bool] = {}
        for project_id, workspace_id in items:
            if workspace_flags.get(workspace_id, True):
                busy[project_id] = False
                continue
            others = user_projects_by_workspace.get(workspace_id, set()) - {project_id}
            busy[project_id] = bool(others)
        return busy, workspace_flags

    async def get_my_responses(self, user_id: int) -> MyResponseListResponse:
        """Получить отклики текущего пользователя"""
        responses = await self._project_repository.get_responses_by_respondent_id(user_id)
        resume_url, resume_title = await self._get_user_resume_url(user_id)
        busy_by_project, allow_multi_by_workspace = await self._resolve_busy_by_project(
            user_id,
            [(r.project_id, r.project.workspace_id if r.project else None) for r in responses],
        )
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
                **resolve_status_fields(
                    r.status,
                    busy_by_project.get(r.project_id, False),
                    allow_multi_by_workspace.get(r.project.workspace_id if r.project else None, True),
                ),
            )
            for r in responses
        ]
        return MyResponseListResponse(items=items, total=len(items))

    async def get_my_invitations(self, user_id: int) -> MyInvitationListResponse:
        """Получить приглашения текущего пользователя"""
        invitations = await self._project_repository.get_invitations_by_invitee_id(user_id)
        resume_url, resume_title = await self._get_user_resume_url(user_id)
        busy_by_project, _ = await self._resolve_busy_by_project(
            user_id,
            [(inv.project_id, inv.project.workspace_id if inv.project else None) for inv in invitations],
        )
        workspace_ids = {inv.project.workspace_id for inv in invitations if inv.project}
        flags = await self._resolve_allow_multi_participation_batch(workspace_ids)
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
                allow_multi_project_participation=flags.get(inv.project.workspace_id if inv.project else None, True),
                **resolve_status_fields(
                    inv.status,
                    busy_by_project.get(inv.project_id, False),
                    flags.get(inv.project.workspace_id if inv.project else None, True),
                ),
            )
            for inv in invitations
        ]
        return MyInvitationListResponse(items=items, total=len(items))

    async def list_all_responses(
        self,
        viewer: User,
        *,
        page: int = 1,
        limit: int = 20,
        type_filter: str | None = None,
        status: str | None = None,
        workspace_id: int | None = None,
        project_id: int | None = None,
        search: str | None = None,
    ) -> ResponseListResponse:
        """Отклики и приглашения по всем проектам, доступным пользователю.

        Область видимости задаёт :meth:`_responses_scope_criterion`:
        глобальный админ видит всё, преподаватель — проекты, которые он создал,
        и проекты пространств, где у него роль admin/teacher. Фильтры применяются
        в SQL, а не к выбранной странице, иначе ``total`` отражал бы длину
        обрезанной выборки и пагинация всегда показывала бы одну страницу.
        """
        scope = await self._responses_scope_criterion(viewer)

        base = select(Response).join(Project, Project.id == Response.project_id)
        if scope is not None:
            base = base.where(scope)
        # "all" — сентинел фронтенда («фильтр не выбран»), а не значение из БД:
        # в response.type лежат только "response"/"invitation". Проверка на
        # непустоту ниже иначе превратила бы «Все» в пустую выдачу.
        if type_filter and type_filter != "all":
            base = base.where(Response.type == type_filter)
        if status and status != "all":
            base = base.where(Response.status == status)
        if workspace_id is not None:
            base = base.where(Project.workspace_id == workspace_id)
        if project_id is not None:
            base = base.where(Response.project_id == project_id)
        if search and search.strip():
            term = f"%{search.strip()}%"
            base = base.where(
                Response.respondent_id.in_(
                    select(User.id).where(
                        or_(User.first_name.ilike(term), User.last_name.ilike(term), User.email.ilike(term))
                    )
                )
            )

        session = self._project_repository.uow.session
        total = int(await session.scalar(select(func.count()).select_from(base.subquery())) or 0)

        result = await session.execute(
            base.options(
                selectinload(Response.respondent),
                selectinload(Response.inviter),
                selectinload(Response.vacancy),
                selectinload(Response.project).selectinload(Project.workspace),
            )
            .order_by(Response.created_at.desc(), Response.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        rows = list(result.scalars().all())

        return ResponseListResponse(
            items=await self._to_response_list_items(rows),
            total=total,
            page=page,
            limit=limit,
            total_pages=(total + limit - 1) // limit if total > 0 else 0,
        )

    async def _responses_scope_criterion(self, viewer: User) -> ColumnElement[bool] | None:
        """Критерий видимости проектов для глобального списка откликов.

        ``None`` — видно всё (глобальный админ). Иначе — свои проекты плюс
        проекты пространств, где пользователь admin/teacher: это тот же состав
        редакторов, которым видны черновики проектов.
        """
        if viewer.role and viewer.role.name == "admin":
            return None
        editor_workspace_ids = await self._editor_workspace_ids(viewer.id, None)
        if not editor_workspace_ids:
            return Project.author_id == viewer.id
        return or_(Project.author_id == viewer.id, Project.workspace_id.in_(editor_workspace_ids))

    async def _to_response_list_items(self, rows: list[Response]) -> list[ResponseListItem]:
        """Ответы и приглашения страницы в схемы общего списка."""
        if not rows:
            return []

        workspace_ids = {row.project.workspace_id for row in rows if row.project}
        flags = await self._resolve_allow_multi_participation_batch(workspace_ids)
        # Занятость считается только там, где пространство запрещает несколько
        # команд: в режиме с множественными командами «уже в другой команде»
        # для человека в двух проектах — норма, а не блокировка.
        busy_by_project = await self._busy_respondents_by_project(
            [
                (row.project_id, row.project.workspace_id if row.project else None)
                for row in rows
                if not flags.get(row.project.workspace_id if row.project else None, True)
            ]
        )

        items: list[ResponseListItem] = []
        for row in rows:
            project = row.project
            respondent = row.respondent
            workspace_id = project.workspace_id if project else None
            allow_multi = flags.get(workspace_id, True)
            items.append(
                ResponseListItem(
                    id=row.id,
                    project_id=row.project_id,
                    project_name=project.name if project else "",
                    workspace_id=workspace_id,
                    workspace_name=project.workspace.name if project and project.workspace else None,
                    user_id=row.respondent_id,
                    name=_user_full_name(respondent),
                    respondent_email=respondent.email if respondent else None,
                    inviter_name=_user_full_name(row.inviter) if row.inviter_id else None,
                    vacancy_id=row.vacancy_id,
                    role=row.vacancy.title if row.vacancy else "",
                    resume_url=build_resume_url(row.resume_id, workspace_id=workspace_id),
                    response_date=str(row.created_at.date()) if row.created_at else "",
                    type=row.type,
                    allow_multi_project_participation=allow_multi,
                    **resolve_busy_status(
                        row.status,
                        row.respondent_id,
                        busy_by_project.get(row.project_id),
                        allow_multi,
                    ),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
            )
        return items

    async def _busy_respondents_by_project(self, scopes: list[tuple[int, int | None]]) -> dict[int, set[int]]:
        """Занятые респонденты по проекту: участники ДРУГИХ проектов пространства.

        Один запрос на пространство, а не на проект: страница общего списка
        пересекает много проектов, и поштучный подсчёт дал бы до ``limit``
        одинаковых запросов. Пустое пространство (``None``) пропускаем —
        сравнивать не с чем, и проектов без пространства в выборке не бывает.
        """
        project_ids_by_workspace: dict[int, set[int]] = {}
        for project_id, workspace_id in scopes:
            if workspace_id:
                project_ids_by_workspace.setdefault(workspace_id, set()).add(project_id)
        if not project_ids_by_workspace:
            return {}

        busy: dict[int, set[int]] = {}
        for workspace_id, project_ids in project_ids_by_workspace.items():
            result = await self._project_repository.uow.session.execute(
                select(ProjectParticipation.participant_id)
                .join(Project, Project.id == ProjectParticipation.project_id)
                .where(
                    Project.workspace_id == workspace_id,
                    Project.id.notin_(project_ids),
                )
                .distinct()
            )
            participants = set(result.scalars().all())
            for project_id in project_ids:
                busy[project_id] = participants
        return busy

    async def get_projects_by_ids(self, project_ids: list[int], viewer_id: int) -> MyProjectListResponse:
        """Получить проекты по списку ID (черновики — только для автора)"""
        projects = await self._project_repository.get_projects_by_ids(project_ids)
        projects = await self._visible_projects(projects, viewer_id)
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
        """Получить проекты, в которых участвует пользователь (черновики — только свои)"""
        projects = await self._project_repository.get_projects_by_participant_id(user_id)
        projects = await self._visible_projects(projects, user_id)
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
        if (
            project
            and not await self._workspace_allows_multi_participation(project.workspace_id)
            and await self._project_repository.is_user_participant_in_other_project(
                user_id, project.workspace_id, invitation.project_id
            )
        ):
            raise ValidationError("Вы уже участвуете в другом проекте этого пространства")
        result = await self._project_repository.update_response_status(invitation_id, "accepted")
        if not result:
            raise NotFoundError("Invitation not found")
        # Добавляем пользователя как участника проекта
        await self._project_repository.add_participant(invitation.project_id, user_id)
        # Уменьшаем количество необходимых участников для роли
        if invitation.vacancy_id:
            await self._project_repository.decrement_vacancy_count(invitation.vacancy_id)
        # Остальные ожидающие отклики и приглашения пользователя в этом пространстве — «уже в команде»
        await self._cancel_sibling_pending(user_id, invitation_id, project.workspace_id if project else None)
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
        if self._mail_service and invitation.inviter_id:
            inviter = await self._project_repository.uow.session.get(User, invitation.inviter_id)
            if inviter and inviter.email:
                await self._mail_service.send_invitation_accepted_email(
                    to=inviter.email,
                    first_name=inviter.first_name or "Уважаемый автор",
                    project_name=project.name,
                    project_id=invitation.project_id,
                    vacancy_title=invitation.vacancy.title if invitation.vacancy else None,
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
        if self._mail_service and invitation.inviter_id:
            inviter = await self._project_repository.uow.session.get(User, invitation.inviter_id)
            if inviter and inviter.email:
                await self._mail_service.send_invitation_rejected_email(
                    to=inviter.email,
                    first_name=inviter.first_name or "Уважаемый автор",
                    project_name=project.name if project else "project",
                    project_id=invitation.project_id,
                )
        return result

    async def get_projects_by_workspace(
        self, workspace_id: int, page: int = 1, limit: int = 10, viewer_id: int | None = None, **filters
    ) -> tuple[list[Project], int]:
        return await self._projects_page(workspace_id, page, limit, viewer_id, filters)

    async def get_projects_paginated(
        self, page: int = 1, limit: int = 10, viewer_id: int | None = None, **filters
    ) -> tuple[list[Project], int]:
        """Получить проекты с пагинацией (черновики скрыты от не-авторов)"""
        return await self._projects_page(None, page, limit, viewer_id, filters)

    async def _projects_page(
        self,
        workspace_id: int | None,
        page: int,
        limit: int,
        viewer_id: int | None,
        filters: dict[str, Any],
    ) -> tuple[list[Project], int]:
        """Страница проектов вместе с общим числом видимых проектов."""
        visible = await self._visible_projects_criterion(
            viewer_id, {workspace_id} if workspace_id is not None else None
        )
        return await self._project_repository.get_projects_page(
            workspace_id=workspace_id,
            skip=(page - 1) * limit,
            limit=limit,
            visible=visible,
            **filters,
        )

    async def get_project_filter_facets(self, workspace_id: int) -> dict[str, list[Any]]:
        """Справочники для фильтров списка проектов пространства."""
        return await self._project_repository.get_project_filter_facets(workspace_id)

    async def search_projects_by_text(self, query: str, limit: int = 10, viewer_id: int | None = None) -> list[Project]:
        """Поиск проектов по тексту (черновики скрыты от не-авторов)"""
        projects = await self._project_repository.search_by_text(query, limit=limit)
        if viewer_id is None:
            return projects
        return await self._visible_projects(projects, viewer_id)

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

        current_stage = getattr(project, "current_stage", None)

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
            current_stage_id=project.current_stage_id,
            current_stage_name=current_stage.name if current_stage else None,
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

    async def _workspace_requires_project_type(self, workspace_id: int | None) -> bool:
        """Требуется ли тип проекта при создании в пространстве (по умолчанию — да)."""
        if not workspace_id:
            return False
        space_settings = await self._project_repository.uow.session.execute(
            select(SpaceSettings).where(SpaceSettings.space_id == workspace_id)
        )
        settings = space_settings.scalar_one_or_none()
        if not settings:
            return True
        return settings.require_project_type_on_create

    async def _raise_if_project_type_required(self, workspace_id: int | None, project_type_id: int | None) -> None:
        """Запретить создание проекта без типа, если это требует настройка пространства."""
        if project_type_id:
            return
        if not await self._workspace_requires_project_type(workspace_id):
            return
        raise ValidationError("Project type is required to create a project in this workspace")

    async def _get_space_settings(self, workspace_id: int | None) -> SpaceSettings | None:
        """Настройки пространства или ``None``, если пространства/настроек нет."""
        if not workspace_id:
            return None
        space_settings = await self._project_repository.uow.session.execute(
            select(SpaceSettings).where(SpaceSettings.space_id == workspace_id)
        )
        return space_settings.scalar_one_or_none()

    async def _workspace_allows_multi_participation(self, workspace_id: int | None) -> bool:
        """Разрешено ли в пространстве участие в нескольких проектах одновременно."""
        if not workspace_id:
            return True
        settings = await self._get_space_settings(workspace_id)
        if not settings:
            return True
        return settings.allow_multi_project_participation

    async def _workspace_allows_multi_project_creation(self, workspace_id: int | None) -> bool:
        """Разрешено ли в пространстве создавать несколько проектов одному автору."""
        if not workspace_id:
            return True
        settings = await self._get_space_settings(workspace_id)
        if not settings:
            return False
        return settings.allow_multi_project_creation

    async def workspace_allows_multi_project_creation(self, workspace_id: int | None) -> bool:
        """Публичная обёртка: разрешено ли создание нескольких проектов в пространстве."""
        return await self._workspace_allows_multi_project_creation(workspace_id)

    async def workspace_allows_multi_participation(self, workspace_id: int | None) -> bool:
        """Публичная обёртка: разрешено ли участие в нескольких проектах в пространстве."""
        return await self._workspace_allows_multi_participation(workspace_id)

    async def _cancel_sibling_pending(self, user_id: int, exclude_response_id: int, workspace_id: int | None) -> None:
        """Если в пространстве запрещено участие в нескольких проектах — пометить остальные
        ожидающие отклики/приглашения пользователя как «уже в команде»."""
        if workspace_id is None or await self._workspace_allows_multi_participation(workspace_id):
            return
        await self._project_repository.mark_sibling_pending_as_in_team(user_id, exclude_response_id, workspace_id)

    async def _resolve_allow_multi_participation_batch(self, workspace_ids: set[int | None]) -> dict[int | None, bool]:
        """Разрешено ли участие в нескольких проектах для каждого пространства (пакетно)."""
        if not workspace_ids:
            return {}
        if None in workspace_ids:
            workspace_ids = workspace_ids - {None}
        if not workspace_ids:
            return {}
        result = await self._project_repository.uow.session.execute(
            select(SpaceSettings.space_id, SpaceSettings.allow_multi_project_participation).where(
                SpaceSettings.space_id.in_(workspace_ids)
            )
        )
        rows = dict(result.all())
        return {wid: rows.get(wid, True) for wid in workspace_ids}

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
        # Автор всегда тот, кто делает запрос: иначе можно было бы создать проект
        # от имени другого пользователя (и обойти лимит «один проект на автора»).
        project_data.author_id = author_id

        # Только управляющие роли пространства (manager/admin/teacher) могут создавать проекты
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
            if not row or row[1].name not in PROJECT_CREATE_ROLES:
                raise PermissionError(
                    "Only a project manager (role in 'manager'/'admin'/'teacher') can create a project in this workspace"
                )

            if not await self._workspace_allows_multi_project_creation(project_data.workspace_id):
                existing_count = await self._project_repository.uow.session.execute(
                    select(func.count())
                    .select_from(Project)
                    .where(
                        Project.workspace_id == project_data.workspace_id,
                        Project.author_id == author_id,
                    )
                )
                if existing_count.scalar_one() > 0:
                    raise PermissionError(
                        "Вы уже создали проект в этом пространстве. Можно создать только один проект."
                    )

            # Если в настройках пространства включено требование типа проекта — блокируем создание без типа
            await self._raise_if_project_type_required(project_data.workspace_id, project_data.project_type_id)

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
        """Удалить участника из команды проекта (автор или глобальный админ)."""
        project = await self.get_project_by_id(project_id)
        if not project:
            return False
        if not await self._can_manage_team(project, current_user_id):
            raise PermissionError("Only project author or admin can remove participants")
        if project.author_id == participant_user_id:
            raise ValidationError("Cannot remove the project author")
        # Увеличиваем количество мест в вакансии если участник был принят по роли
        accepted = await self._project_repository.get_accepted_response_for_participant(project_id, participant_user_id)
        if accepted and accepted.vacancy_id:
            await self._project_repository.increment_vacancy_count(accepted.vacancy_id)
        return await self._project_repository.remove_participant(project_id, participant_user_id)

    async def _can_manage_team(self, project: Project, user_id: int) -> bool:
        """Может ли пользователь управлять командой проекта (автор или глобальный админ)."""
        if project.author_id == user_id:
            return True
        result = await self._project_repository.uow.session.execute(
            select(Role.name).join(User, User.role_id == Role.id).where(User.id == user_id)
        )
        return result.scalar_one_or_none() == "admin"

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
        if self._mail_service and project.author and project.author.email:
            await self._mail_service.send_response_received_email(
                to=project.author.email,
                first_name=project.author.first_name or "Уважаемый автор",
                project_name=project.name,
                project_id=project.id,
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
        # Кандидат в dialog приходит с can_invite=false и reason="busy", но это
        # подсказка интерфейса: тот же запрет проверяем здесь, иначе прямой вызов
        # API пригласит человека, которому в этом пространстве нельзя.
        if (
            project.workspace_id
            and not await self._workspace_allows_multi_participation(project.workspace_id)
            and await self._project_repository.is_user_participant_in_other_project(
                invitee_id, project.workspace_id, project_id
            )
        ):
            raise ValidationError("Участник уже состоит в другом проекте этого пространства")
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
        if self._mail_service:
            invitee = await self._project_repository.uow.session.get(User, invitee_id)
            if invitee and invitee.email:
                await self._mail_service.send_invitation_received_email(
                    to=invitee.email,
                    first_name=invitee.first_name or "Пользователь",
                    project_name=project.name,
                    vacancy_title=invitation.vacancy.title if invitation.vacancy else None,
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
        if self._mail_service:
            respondent = await self._project_repository.uow.session.get(User, response.respondent_id)
            if respondent and respondent.email:
                await self._mail_service.send_response_accepted_email(
                    to=respondent.email,
                    first_name=respondent.first_name or "Пользователь",
                    project_name=project.name,
                    vacancy_title=response.vacancy.title if response.vacancy else None,
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
        if (
            project
            and not await self._workspace_allows_multi_participation(project.workspace_id)
            and await self._project_repository.is_user_participant_in_other_project(
                user_id, project.workspace_id, response.project_id
            )
        ):
            raise ValidationError("Вы уже участвуете в другом проекте этого пространства")
        await self._project_repository.add_participant(response.project_id, user_id)
        await self._project_repository.update_response_status(response_id, "in_team")
        if response.vacancy_id:
            await self._project_repository.decrement_vacancy_count(response.vacancy_id)
        # Остальные ожидающие отклики и приглашения пользователя в этом пространстве — «уже в команде»
        await self._cancel_sibling_pending(user_id, response_id, project.workspace_id if project else None)
        if self._notification_service and project:
            user = await self._project_repository.uow.session.get(User, user_id)
            actor_name = f"{user.first_name} {user.last_name or ''}".strip() if user else "User"
            await self._notification_service.create_notification(
                user_id=project.author_id,
                type=NotificationType.response_confirmed,
                actor_name=actor_name,
                actor_id=user_id,
                project_id=response.project_id,
                project_name=project.name,
                vacancy_title=response.vacancy.title if response.vacancy else None,
                response_id=response_id,
            )
        if self._mail_service and project.author and project.author.email:
            await self._mail_service.send_response_confirmed_email(
                to=project.author.email,
                first_name=project.author.first_name or "Уважаемый автор",
                project_name=project.name,
                project_id=project.id,
                vacancy_title=response.vacancy.title if response.vacancy else None,
            )
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
        if self._mail_service:
            respondent = await self._project_repository.uow.session.get(User, response.respondent_id)
            if respondent and respondent.email:
                await self._mail_service.send_response_rejected_email(
                    to=respondent.email,
                    first_name=respondent.first_name or "Пользователь",
                    project_name=project.name,
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
