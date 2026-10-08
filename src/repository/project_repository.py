from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, cast, func, or_, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from src.core.uow import IUnitOfWork
from src.model.project import (
    ACTIVE_RESPONSE_STATUSES,
    Project,
    ProjectParticipation,
    ProjectStage,
    ProjectType,
    ProjectVacancy,
    Response,
    StageTransition,
    Tag,
    project_tag,
)
from src.model.user import User
from src.repository.base_repository import BaseRepository
from src.schema.project import ProjectCreate, ProjectUpdate

# Опции, без которых список проектов не отрендерится: карточка и таблица читают
# статус, теги, участников и текущий этап.
PROJECT_LIST_LOADERS: tuple[Any, ...] = (
    selectinload(Project.project_type).selectinload(ProjectType.stages),
    selectinload(Project.current_stage),
    selectinload(Project.participants).selectinload(ProjectParticipation.participant),
    selectinload(Project.tags),
    selectinload(Project.status),
)


class ProjectRepository(BaseRepository[Project, ProjectCreate, ProjectUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Project

    async def get_by_id(self, id: int) -> Project | None:
        query = (
            select(Project)
            .where(Project.id == id)
            .options(
                selectinload(Project.author),
                selectinload(Project.participants).selectinload(ProjectParticipation.participant),
                selectinload(Project.tags),
                selectinload(Project.status),
                selectinload(Project.vacancies),
                selectinload(Project.responses).selectinload(Response.vacancy),
                selectinload(Project.responses).selectinload(Response.respondent),
                selectinload(Project.responses).selectinload(Response.inviter),
                selectinload(Project.responses).selectinload(Response.resume),
                selectinload(Project.project_type).selectinload(ProjectType.stages),
                selectinload(Project.current_stage),
                selectinload(Project.stage_transitions).selectinload(StageTransition.stage),
                selectinload(Project.stage_transitions).selectinload(StageTransition.from_stage),
                selectinload(Project.stage_transitions).selectinload(StageTransition.actor),
            )
        )
        result = await self.uow.session.execute(query)
        return result.scalar_one_or_none()

    async def is_user_in_project(self, project_id: int, user_id: int) -> bool:
        """Есть ли пользователь в проекте.

        ``limit(1)``, а не ``scalar_one_or_none``: проверка существования не
        должна падать на дубликатах. Исторические базы могли получить по
        несколько строк участия на пару (project_id, participant_id), и
        ``scalar_one_or_none`` превращал такую базу в 500 на любом вызове,
        где нужен булев ответ.
        """
        result = await self.uow.session.execute(
            select(ProjectParticipation)
            .where(
                ProjectParticipation.project_id == project_id,
                ProjectParticipation.participant_id == user_id,
            )
            .limit(1),
        )
        return result.scalars().first() is not None

    async def get_by_author_id(self, author_id: int) -> list[Project]:
        query = (
            select(Project)
            .where(Project.author_id == author_id)
            .options(
                selectinload(Project.participants).selectinload(ProjectParticipation.participant),
                selectinload(Project.tags),
                selectinload(Project.status),
                selectinload(Project.vacancies),
            )
        )
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def get_projects_by_ids(self, project_ids: list[int]) -> list[Project]:
        query = (
            select(Project)
            .where(Project.id.in_(project_ids))
            .options(
                selectinload(Project.project_type).selectinload(ProjectType.stages),
                selectinload(Project.participants).selectinload(ProjectParticipation.participant),
                selectinload(Project.tags),
                selectinload(Project.status),
                selectinload(Project.vacancies),
            )
        )
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def get_projects_by_participant_id(self, participant_id: int) -> list[Project]:
        subquery = select(ProjectParticipation.project_id).where(ProjectParticipation.participant_id == participant_id)
        query = (
            select(Project)
            .where(Project.id.in_(subquery))
            .options(
                selectinload(Project.project_type).selectinload(ProjectType.stages),
                selectinload(Project.participants).selectinload(ProjectParticipation.participant),
                selectinload(Project.tags),
                selectinload(Project.status),
                selectinload(Project.vacancies),
            )
        )
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def get_responses_by_respondent_id(self, respondent_id: int) -> list[Response]:
        query = (
            select(Response)
            .where(Response.respondent_id == respondent_id, Response.type == "response")
            .options(
                selectinload(Response.project),
                selectinload(Response.vacancy),
            )
        )
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def get_response_by_id(self, response_id: int) -> Response | None:
        result = await self.uow.session.execute(select(Response).where(Response.id == response_id))
        return result.scalar_one_or_none()

    async def get_response_by_id_for_update(self, response_id: int) -> Response | None:
        """Взять отклик/приглашение под блокировкой строки.

        Принимание заявки — это «прочитал статус → потом вставил участие», и
        без блокировки два параллельных запроса читают один и тот же статус
        ``pending``/``accepted`` и оба вставляют по строке в
        ``project_participation``. Такое происходит при двойном клике по кнопке
        подтверждения: фронт не успевает её задизейблить между кликами.

        Блокировка сериализует второй запрос — он дождётся коммита первого и
        увидит терминальный статус. Аналог ``get_by_token_with_for_update`` в
        invitation_repository для вступления по ссылке.
        """
        result = await self.uow.session.execute(
            select(Response).where(Response.id == response_id).with_for_update(),
        )
        return result.scalars().first()

    async def update_response_status(
        self, response_id: int, status: str, rejection_reason: str | None = None
    ) -> Response | None:
        response = await self.get_response_by_id(response_id)
        if not response:
            return None
        response.status = status
        # Причина передаётся только из ``reject_response``: остальные смены
        # статуса (принятие, отзыв, отмена соседних записей) её не трогают.
        if rejection_reason is not None:
            response.rejection_reason = rejection_reason
        await self.uow.session.flush()
        return response

    async def get_invitations_by_invitee_id(self, invitee_id: int) -> list[Response]:
        query = (
            select(Response)
            .where(Response.respondent_id == invitee_id, Response.type == "invitation")
            .options(
                selectinload(Response.project),
                selectinload(Response.vacancy),
                selectinload(Response.inviter),
            )
        )
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def count_invitations_by_user_id(self, user_id: int) -> int:
        result = await self.uow.session.execute(
            select(func.count())
            .select_from(Response)
            .where(Response.respondent_id == user_id, Response.type == "invitation"),
        )
        return result.scalar() or 0

    async def get_projects_page(
        self,
        workspace_id: int | None = None,
        skip: int = 0,
        limit: int = 10,
        search: str | None = None,
        stages: list[str] | None = None,
        tags: list[str] | None = None,
        member_ids: list[int] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        visible: ColumnElement[bool] | None = None,
    ) -> tuple[list[Project], int]:
        """Страница проектов с фильтрами и настоящим total.

        ``visible`` — критерий видимости (черновики). Он применяется в SQL, а не
        к уже выбранной странице: иначе total отражал бы длину обрезанной
        выборки, и пагинация всегда показывала бы одну страницу.
        """
        base = select(Project)

        if workspace_id is not None:
            base = base.where(Project.workspace_id == workspace_id)
        if search and search.strip():
            term = f"%{search.strip()}%"
            base = base.where(or_(Project.name.ilike(term), Project.theme.ilike(term), Project.description.ilike(term)))
        if stages:
            # Фильтр по названию этапа, а не по id: у одного типа проекта «Создание тз»
            # — это stage 3, у другого — stage 11, а в списке это один и тот же этап.
            base = base.where(
                Project.current_stage_id.in_(select(ProjectStage.id).where(ProjectStage.name.in_(stages)))
            )
        if tags:
            base = base.where(Project.tags.any(Tag.name.in_(tags)))
        if member_ids:
            base = base.where(Project.participants.any(ProjectParticipation.participant_id.in_(member_ids)))
        if date_from or date_to:
            base = base.where(Project.deadline.is_not(None))
            if date_from:
                base = base.where(cast(Project.deadline, Date) >= date_from)
            if date_to:
                base = base.where(cast(Project.deadline, Date) <= date_to)
        if visible is not None:
            base = base.where(visible)

        # count считаем по той же выборке, что и страница, иначе total разойдётся с items
        total = await self.uow.session.scalar(select(func.count()).select_from(base.subquery())) or 0

        query = base.options(*PROJECT_LIST_LOADERS).order_by(Project.id.desc()).offset(skip).limit(limit)
        result = await self.uow.session.execute(query)
        return list(result.scalars().all()), int(total)

    async def get_project_filter_facets(self, workspace_id: int) -> dict[str, list[Any]]:
        """Справочники для фильтров списка проектов пространства.

        Нужны отдельно от страницы списка: варианты фильтра должны быть
        одинаковыми на всех страницах, а не зависеть от того, что попало
        в текущий ответ.
        """
        project_ids = select(Project.id).where(Project.workspace_id == workspace_id)

        tags_result = await self.uow.session.execute(
            select(Tag.name)
            .join(project_tag, project_tag.c.tag_id == Tag.id)
            .where(project_tag.c.project_id.in_(project_ids))
            .distinct()
        )
        members_result = await self.uow.session.execute(
            select(User.id, User.first_name, User.last_name)
            .join(ProjectParticipation, ProjectParticipation.participant_id == User.id)
            .where(ProjectParticipation.project_id.in_(project_ids))
            .distinct()
        )
        projects_result = await self.uow.session.execute(
            select(Project.id, Project.name).where(Project.workspace_id == workspace_id).order_by(Project.name)
        )

        members: list[dict[str, Any]] = []
        for user_id, first_name, last_name in members_result.all():
            full_name = " ".join(part for part in (first_name, last_name) if part).strip()
            members.append({"id": user_id, "full_name": full_name or "Unknown"})

        # Названия этапов, встречающиеся в проектах пространства. Порядок — по
        # минимальному «order» среди типов, где этап есть: у каждого типа своя
        # нумерация, а показывать надо единый список.
        stage_order = ProjectStage.__table__.c.order
        stages_result = await self.uow.session.execute(
            select(ProjectStage.name, func.min(stage_order))
            .join(Project, Project.current_stage_id == ProjectStage.id)
            .where(Project.workspace_id == workspace_id)
            .group_by(ProjectStage.name)
        )

        return {
            "stages": [name for name, _ in sorted(stages_result.all(), key=lambda row: (row[1], row[0]))],
            "tags": sorted(str(name) for name in tags_result.scalars().all()),
            "members": members,
            "projects": [{"id": row[0], "name": row[1]} for row in projects_result.all()],
        }

    async def update_deadline_by_workspace(self, workspace_id: int, deadline: datetime | None) -> None:
        """Обновить дедлайн всех проектов пространства (ретроактивно)."""
        stmt = (
            update(Project)
            .where(Project.workspace_id == workspace_id)
            .values(deadline=deadline)
            .execution_options(synchronize_session="fetch")
        )
        await self.uow.session.execute(stmt)

    async def count_by_workspace(self, workspace_id: int) -> int:
        result = await self.uow.session.execute(
            select(func.count()).select_from(Project).where(Project.workspace_id == workspace_id)
        )
        return result.scalar()

    async def search_by_text(self, query: str, limit: int = 100) -> list[Project]:
        """Поиск проектов по названию, теме и описанию"""
        term = f"%{query}%"
        stmt = (
            select(Project)
            .where(
                or_(
                    Project.name.ilike(term),
                    Project.theme.ilike(term),
                    Project.description.ilike(term),
                )
            )
            .options(
                selectinload(Project.project_type).selectinload(ProjectType.stages),
                selectinload(Project.current_stage),
                selectinload(Project.participants).selectinload(ProjectParticipation.participant),
                selectinload(Project.tags),
                selectinload(Project.status),
                selectinload(Project.workspace),
            )
            .order_by(Project.name.asc())
            .limit(limit)
        )
        result = await self.uow.session.execute(stmt)
        return list(result.scalars().all())

    async def remove_participant(self, project_id: int, user_id: int) -> bool:
        """Убрать пользователя из проекта, удалив ВСЕ строки участия.

        Исторически пара (project_id, participant_id) могла встречаться
        несколько раз. Удаление одной строки оставляло пользователя в команде
        (и ``scalar_one_or_none`` на второй попытке падал бы), поэтому выбираем
        и удаляем все. Именно ORM-delete, а не bulk ``delete()``: на bulk не
        срабатывает ``before_delete`` в audit_listeners, и запись о снятии
        участника пропала бы из ленты активности проекта.
        """
        result = await self.uow.session.execute(
            select(ProjectParticipation).where(
                ProjectParticipation.project_id == project_id,
                ProjectParticipation.participant_id == user_id,
            ),
        )
        participations = list(result.scalars().all())
        if not participations:
            return False
        for participation in participations:
            await self.uow.session.delete(participation)
        await self.uow.session.flush()
        return True

    async def get_or_create_tags(self, tag_names: list[str]) -> list[Tag]:
        if not tag_names:
            return []

        existing_tags_result = await self.uow.session.execute(select(Tag).where(Tag.name.in_(tag_names)))
        existing_tags_list = list(existing_tags_result.scalars().all())
        existing_tags = {tag.name: tag for tag in existing_tags_list}

        tags = []
        for tag_name in tag_names:
            tag = existing_tags.get(tag_name)
            if tag is None:
                tag = Tag(name=tag_name)
                self.uow.session.add(tag)
                tags.append(tag)
            else:
                tags.append(tag)

        await self.uow.session.flush()
        return tags

    async def has_pending_response(self, project_id: int, user_id: int) -> bool:
        result = await self.uow.session.execute(
            select(Response)
            .where(
                Response.project_id == project_id,
                Response.respondent_id == user_id,
                Response.status == "pending",
            )
            .limit(1),
        )
        return result.scalars().first() is not None

    async def has_pending_invitation(self, project_id: int, user_id: int) -> bool:
        result = await self.uow.session.execute(
            select(Response)
            .where(
                Response.project_id == project_id,
                Response.respondent_id == user_id,
                Response.type == "invitation",
                Response.status == "pending",
            )
            .limit(1),
        )
        return result.scalars().first() is not None

    async def create_response(
        self,
        respondent_id: int,
        project_id: int,
        vacancy_id: int | None = None,
        type: str = "response",
        inviter_id: int | None = None,
        note: str | None = None,
        resume_id: int | None = None,
    ) -> Response:
        response = Response(
            respondent_id=respondent_id,
            project_id=project_id,
            vacancy_id=vacancy_id,
            type=type,
            inviter_id=inviter_id,
            note=note,
            resume_id=resume_id,
        )
        self.uow.session.add(response)
        await self.uow.session.flush()
        await self.uow.session.refresh(response, ["vacancy"])
        return response

    async def get_response_counts_by_vacancy_ids(self, vacancy_ids: list[int]) -> dict[int, int]:
        """Сколько АКТИВНЫХ откликов и приглашений висит на каждой из ролей.

        Нужна перед архивацией роли при правке проекта: у роли с живыми
        откликами нельзя прятаться из формы — заявитель ещё ждёт решения, а
        у участника пропала бы роль в команде. Отклонённые, отозванные и
        отменённые записи не считаются: именно они раньше делали роль
        неудаляемой навсегда, даже после обработки всех откликов.

        Роли без активных откликов в словарь не попадают. Статусы —
        ``ACTIVE_RESPONSE_STATUSES``, тот же набор считает фронтовый
        ``vacancy-sync``: расхождение дало бы 422 на сохранении формы.
        """
        if not vacancy_ids:
            return {}
        result = await self.uow.session.execute(
            select(Response.vacancy_id, func.count(Response.id))
            .where(
                Response.vacancy_id.in_(vacancy_ids),
                Response.status.in_(ACTIVE_RESPONSE_STATUSES),
            )
            .group_by(Response.vacancy_id),
        )
        return {vacancy_id: count for vacancy_id, count in result.all() if vacancy_id is not None}

    async def decrement_vacancy_count(self, vacancy_id: int) -> None:
        await self.uow.session.execute(
            update(ProjectVacancy)
            .where(ProjectVacancy.id == vacancy_id, ProjectVacancy.required_count > 0)
            .values(required_count=ProjectVacancy.required_count - 1),
        )
        await self.uow.session.flush()

    async def increment_vacancy_count(self, vacancy_id: int) -> None:
        await self.uow.session.execute(
            update(ProjectVacancy)
            .where(ProjectVacancy.id == vacancy_id)
            .values(required_count=ProjectVacancy.required_count + 1),
        )
        await self.uow.session.flush()

    async def add_participant(self, project_id: int, user_id: int) -> ProjectParticipation:
        """Добавить участника проекта, если его ещё нет.

        Идемпотентно по контракту: повторный вызов возвращает существующую строку
        участия, а не создаёт вторую. Раньше здесь был голый INSERT, поэтому любой
        повторный путь (двойной клик по кнопке подтверждения, ретрай) добавлял
        в ``project_participation`` ещё одну строку на ту же пару, а список
        участников проекта показывал человека дважды.

        Опора на уникальный индекс ``uq_pp_project_participant`` (см.
        ``model/project.py``) — приложение само по себе ему не доверяет.
        """
        result = await self.uow.session.execute(
            select(ProjectParticipation)
            .where(
                ProjectParticipation.project_id == project_id,
                ProjectParticipation.participant_id == user_id,
            )
            .limit(1),
        )
        existing = result.scalars().first()
        if existing is not None:
            return existing
        participation = ProjectParticipation(
            project_id=project_id,
            participant_id=user_id,
        )
        self.uow.session.add(participation)
        await self.uow.session.flush()
        return participation

    async def update_participant_role(
        self, project_id: int, user_id: int, role: str | None
    ) -> ProjectParticipation | None:
        """Задать или снять ручную роль участника.

        ``None`` возвращается, если пары (проект, участник) нет: вызывающий
        отличает «участника нет» от «роль обновлена». Строку не создаём —
        ручная роль не должна добавлять человека в команду.
        """
        result = await self.uow.session.execute(
            select(ProjectParticipation)
            .where(
                ProjectParticipation.project_id == project_id,
                ProjectParticipation.participant_id == user_id,
            )
            .limit(1),
        )
        participation = result.scalars().first()
        if participation is None:
            return None
        participation.role = role
        await self.uow.session.flush()
        return participation

    async def get_responses_by_project_id(self, project_id: int) -> list[Response]:
        result = await self.uow.session.execute(
            select(Response)
            .where(Response.project_id == project_id)
            .options(
                selectinload(Response.vacancy),
                selectinload(Response.respondent),
            )
        )
        return list(result.scalars().all())

    async def mark_sibling_pending_as_in_team(self, user_id: int, exclude_response_id: int, workspace_id: int) -> int:
        """Пометить остальные ожидающие отклики/приглашения пользователя в пространстве как «уже в команде»."""
        sibling_project_ids = select(Project.id).where(Project.workspace_id == workspace_id)
        stmt = (
            update(Response)
            .where(
                Response.respondent_id == user_id,
                Response.id != exclude_response_id,
                Response.status == "pending",
                Response.project_id.in_(sibling_project_ids),
            )
            .values(status="in_team")
            .execution_options(synchronize_session="fetch")
        )
        result = await self.uow.session.execute(stmt)
        await self.uow.session.flush()
        return result.rowcount or 0

    async def get_workspace_busy_participant_ids(self, workspace_id: int | None, exclude_project_id: int) -> set[int]:
        """Участники, состоящие в любом ДРУГОМ проекте пространства.

        Пустое пространство (``None``) — «никто не занят»: сравнивать не с чем,
        а проектов без пространства в выборке не бывает.
        """
        if not workspace_id:
            return set()
        result = await self.uow.session.execute(
            select(ProjectParticipation.participant_id)
            .join(Project, Project.id == ProjectParticipation.project_id)
            .where(
                Project.workspace_id == workspace_id,
                Project.id != exclude_project_id,
            )
            .distinct()
        )
        return set(result.scalars().all())

    async def get_user_project_scopes(self, user_id: int) -> list[tuple[int, int | None]]:
        """Пары (project_id, workspace_id) всех проектов, в которых состоит участник.

        Нужен, чтобы ответить «занят ли он в другом проекте ЭТОГО пространства»
        для профиля, где отклики смешаны из разных пространств: одним общим
        флагом нельзя, занятость всегда считается внутри пространства отклика.
        """
        result = await self.uow.session.execute(
            select(Project.id, Project.workspace_id)
            .join(ProjectParticipation, ProjectParticipation.project_id == Project.id)
            .where(ProjectParticipation.participant_id == user_id)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def is_user_participant_in_other_project(
        self, user_id: int, workspace_id: int, exclude_project_id: int
    ) -> bool:
        """Участвует ли пользователь в другом проекте пространства (кроме указанного)."""
        result = await self.uow.session.execute(
            select(ProjectParticipation.id)
            .join(Project, Project.id == ProjectParticipation.project_id)
            .where(
                ProjectParticipation.participant_id == user_id,
                Project.workspace_id == workspace_id,
                Project.id != exclude_project_id,
            )
        )
        return result.first() is not None

    async def get_accepted_response_for_participant(self, project_id: int, user_id: int) -> Response | None:
        """Принятый отклик пользователя по проекту.

        ``first()``, а не ``scalar_one_or_none``: автор мог принять две разные
        заявки одного человека (например, отклик и приглашение), и тогда
        ``scalar_one_or_none`` ронял бы 500 вместо возврата одной строки.
        """
        result = await self.uow.session.execute(
            select(Response)
            .where(
                Response.project_id == project_id,
                Response.respondent_id == user_id,
                Response.status == "accepted",
            )
            .limit(1),
        )
        return result.scalars().first()
