from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.model.project import Project
from src.schema.stage import ProjectStageInfo
from src.util.urls import build_resume_url

if TYPE_CHECKING:
    from src.model.project import ProjectParticipation, Response

#: Потолок длины одной задачи роли. ``project_vacancy.tasks`` — JSON без
#: ограничения на стороне БД, поэтому длина задаётся только здесь.
MAX_VACANCY_TASK_LENGTH = 500

#: Потолок длины ручной роли участника — совпадает с колонкой
#: ``project_participation.role`` (``String(200)``).
MAX_PARTICIPANT_ROLE_LENGTH = 200


def _find_duplicates(values: list[str]) -> list[str]:
    """Повторы в списке строк, в порядке первого появления."""
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


class ParticipantPreview(BaseModel):
    id: int
    full_name: str
    avatar_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


# Роль автора проекта в таблице команды. Автора добавляют в участники при
# создании проекта, без отклика, поэтому роль из принятого отклика ему не
# достаётся — иначе колонка «Роль» выглядит пустой.
PROJECT_AUTHOR_ROLE = "Автор"


class ParticipantFull(BaseModel):
    id: int
    user_id: int
    name: str
    role: str = ""
    contacts: str = ""
    resume_url: str = ""
    date_added: str

    model_config = ConfigDict(from_attributes=True)


class ParticipantRoleUpdate(BaseModel):
    """Тело ручного назначения роли участнику команды.

    Пустая строка (и одни пробелы) неотличима от «снять ручную роль» и
    нормализуется в ``None``: тогда снова работает автоматический вывод роли.
    """

    role: str | None = None

    @field_validator("role")
    @classmethod
    def _normalize_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if len(stripped) > MAX_PARTICIPANT_ROLE_LENGTH:
            raise ValueError("Роль не может быть длиннее 200 символов")
        return stripped or None


class ResponseItem(BaseModel):
    id: int
    user_id: int
    name: str
    contacts: str = ""
    resume_url: str = ""
    response_date: str
    vacancy_id: int | None = None
    role: str = ""
    type: str = "response"
    status: str = "pending"
    #: Причина отказа, если отклик отклонён (и руководитель её указал).
    rejection_reason: str | None = None
    allow_multi_project_participation: bool = True
    busy_in_other_project: bool = False

    model_config = ConfigDict(from_attributes=True)


#: Статусы, которые производный пересчёт может превратить в ``in_team``.
#: ``rejected``/``withdrawn`` — решения сторон, их не пересматриваем.
CLOSABLE_STATUSES = ("pending", "accepted")

#: Статусы отклика, по которым роль участника уже закреплена: ``accepted`` —
#: принятое приглашение, ``in_team`` — подтверждённое вступление по отклику.
#: ``pending`` сюда не входит: человек ещё не в команде, роль не его.
ROLE_RESPONSE_STATUSES = ("accepted", "in_team")


def resolve_status_fields(
    status: str,
    busy: bool,
    allow_multi_project_participation: bool,
) -> dict[str, str | bool]:
    """Готовые поля ``status``/``busy_in_other_project`` для схем отклика.

    Отдельная функция вместо кортежа, потому что call sites передают результат
    через ``**`` в конструктор Pydantic-модели.
    """
    if busy and not allow_multi_project_participation and status in CLOSABLE_STATUSES:
        return {"status": "in_team", "busy_in_other_project": True}
    return {"status": status, "busy_in_other_project": busy}


def resolve_busy_status(
    status: str,
    user_id: int | None,
    busy_user_ids: set[int] | None,
    allow_multi_project_participation: bool,
) -> dict[str, str | bool]:
    """Статус отклика/приглашения с поправкой на участие в другом проекте.

    Хранимое поле обновляется только в момент вступления и только для строк,
    которые тогда были ``pending``. Поэтому принятый, но неподтверждённый отклик
    навсегда остаётся ``accepted``, и кнопка «Подтвердить участие» упрётся в 400
    «вы уже участвуете в другом проекте этого пространства». Здесь статус
    пересчитывается на чтении, и зависшие строки чинятся без миграции данных.

    Пересчёт применяется только когда в пространстве запрещено участие в
    нескольких проектах: в режиме с множественными командами человек, состоящий
    в двух проектах, законен и помечать его «уже в команде» неверно.

    ``busy_user_ids`` — участники, состоящие в другом проекте пространства.
    """
    busy = bool(user_id) and user_id in (busy_user_ids or set())
    return resolve_status_fields(status, busy, allow_multi_project_participation)


class ProjectStatusItem(BaseModel):
    name: str
    color: str

    model_config = ConfigDict(from_attributes=True)


class VacancyItem(BaseModel):
    id: int
    title: str
    tasks: list[str]
    required_count: int

    model_config = ConfigDict(from_attributes=True)


class VacancyCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    tasks: list[str] = Field(..., min_length=1)
    required_count: int = 1

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Роль не может быть пустой")
        return v.strip()

    @field_validator("tasks")
    @classmethod
    def tasks_not_blank(cls, v: list[str]) -> list[str]:
        cleaned = [t.strip() for t in v if t.strip()]
        if not cleaned:
            raise ValueError("У роли должны быть указаны задачи")

        too_long = [t for t in cleaned if len(t) > MAX_VACANCY_TASK_LENGTH]
        if too_long:
            raise ValueError(f"Задача не может быть длиннее {MAX_VACANCY_TASK_LENGTH} символов")

        duplicates = _find_duplicates(cleaned)
        if duplicates:
            listed = ", ".join(f"«{d}»" for d in duplicates[:3])
            raise ValueError(f"Задачи роли не должны повторяться: {listed}")

        return cleaned


class VacancyUpdate(VacancyCreate):
    """Роль в запросе на обновление проекта.

    Обновление синхронизирует список ролей по ``id``, а не пересоздаёт его:
    пересоздание обнуляло бы ``response.vacancy_id`` у уже откликнувшихся, и
    роль пропадала бы из откликов при каждом сохранении проекта.

    ``id`` есть у ролей, пришедших с сервера, и отсутствует у новых — те
    создаются этим же запросом.
    """

    id: int | None = None


class ProjectCreate(BaseModel):
    """Схема для создания проекта"""

    name: str
    author_id: int | None = None
    theme: str | None = None
    description: str | None = None
    max_participants: int | None = None
    status_id: int | None = None
    deadline: datetime | None = None
    progress: int | None = None
    tags: list[str] | None = None
    workspace_id: int | None = None
    vacancies: list[VacancyCreate] | None = None
    project_type_id: int | None = None


class ApplyRequest(BaseModel):
    vacancy_id: int | None = None
    resume_id: int


class InviteRequest(BaseModel):
    user_id: int
    vacancy_id: int | None = None
    resume_id: int | None = None


class ResponseRejectRequest(BaseModel):
    """Тело отказа на отклик: причина опциональна и не длиннее 200 символов."""

    reason: str | None = Field(default=None, max_length=200)

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str | None) -> str | None:
        """Убрать краевые пробелы; пустую строку считать незаполненной причиной."""
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ProjectUpdate(BaseModel):
    """Схема для обновления проекта"""

    name: str | None = None
    author_id: int | None = None
    theme: str | None = None
    description: str | None = None
    max_participants: int | None = None
    status_id: int | None = None
    deadline: datetime | None = None
    progress: int | None = None
    tags: list[str] | None = None
    workspace_id: int | None = None
    vacancies: list[VacancyUpdate] | None = None
    project_type_id: int | None = None


def _stage_entry_times(project: Project) -> dict[int, datetime]:
    """Время входа в каждый этап — момент последнего перехода action="advance" в него."""
    entry_by_stage: dict[int, datetime] = {}
    try:
        for t in project.stage_transitions or []:
            if (
                t.action == "advance"
                and t.stage_id
                and (t.stage_id not in entry_by_stage or t.created_at > entry_by_stage[t.stage_id])
            ):
                entry_by_stage[t.stage_id] = t.created_at
    except Exception:
        entry_by_stage = {}
    return entry_by_stage


class StageRejectionInfo(BaseModel):
    """Комментарий преподавателя при возврате этапа"""

    stage_name: str
    comment: str | None = None
    actor_name: str = ""
    created_at: datetime | None = None


def _latest_rejection(project: Project) -> StageRejectionInfo | None:
    """Присутствует ли у проекта возврат этапа с комментарием (последний reject).

    Возврат не показываем, если после него этап уже был утверждён преподавателем.
    """
    try:
        transitions = project.stage_transitions or []
    except Exception:
        transitions = []

    last_approve_at: datetime | None = None
    for t in transitions:
        if (
            getattr(t, "action", None) == "approve"
            and t.created_at
            and (last_approve_at is None or t.created_at > last_approve_at)
        ):
            last_approve_at = t.created_at

    latest: StageRejectionInfo | None = None
    for t in transitions:
        if getattr(t, "action", None) != "reject":
            continue
        if t.created_at and last_approve_at and last_approve_at > t.created_at:
            continue
        if latest and (not t.created_at or (latest.created_at and t.created_at <= latest.created_at)):
            continue
        actor = getattr(t, "actor", None)
        stage = getattr(t, "stage", None) or getattr(t, "from_stage", None)
        latest = StageRejectionInfo(
            stage_name=stage.name if stage else "",
            comment=t.comment,
            actor_name=f"{actor.first_name} {actor.last_name or ''}".strip() if actor else "",
            created_at=t.created_at,
        )
    return latest


def _member_role(
    participation: ProjectParticipation,
    project: Project,
    accepted_by_participant: dict[int, Response],
) -> str:
    """Роль участника команды: ручная, иначе из отклика, иначе «Автор».

    Приоритет у роли, назначенной руководителем вручную. Без неё роль берётся
    из принятого отклика (``accepted``/``in_team``); у автора проекта отклика
    нет, поэтому он «Автор». Пустая строка остаётся только у участника без
    отклика и без ручной роли.
    """
    if participation.role:
        return participation.role
    if participation.participant_id == project.author_id:
        return PROJECT_AUTHOR_ROLE
    response = accepted_by_participant.get(participation.participant_id)
    if response is None or response.vacancy is None:
        return ""
    return response.vacancy.title or ""


def _member_resume_url(
    participation: ProjectParticipation,
    accepted_by_participant: dict[int, Response],
    *,
    workspace_id: int | None = None,
) -> str:
    """Ссылка на резюме участника из принятого отклика.

    У участника без принятого отклика (автор проекта, добавленный вручную)
    резюма нет, и колонка остаётся пустой — это ожидаемо.
    """
    response = accepted_by_participant.get(participation.participant_id)
    if response is None:
        return ""
    return build_resume_url(response.resume_id, workspace_id=workspace_id)


class ProjectFull(ProjectCreate):
    """Полная схема проекта"""

    id: int
    workspace_id: int | None = None
    created_at: datetime | None = None
    theme: str | None = None
    status: ProjectStatusItem | None = None
    tags: list[str] = []
    participants_count: int | None = None
    participants_preview: list[ParticipantPreview] = []
    members: list[ParticipantFull] = []
    replycants: list[ResponseItem] = []
    vacancies: list[VacancyItem] = []
    author_name: str = ""
    author_email: str | None = None
    has_user_applied: bool = False
    project_type_id: int | None = None
    current_stage_id: int | None = None
    stage_pending_approval: bool = False
    stages: list[ProjectStageInfo] = []
    stage_rejection: StageRejectionInfo | None = None

    model_config = ConfigDict(from_attributes=True)

    @staticmethod
    def from_orm(
        project: Project,
        current_user_id: int | None = None,
        allow_multi_project_participation: bool = True,
        busy_user_ids: set[int] | None = None,
    ) -> ProjectFull:
        try:
            project_tags = project.tags or []
        except Exception:
            project_tags = []
        tags = [tag.name for tag in project_tags]

        try:
            project_status = project.status
        except Exception:
            project_status = None
        status = ProjectStatusItem(name=project_status.name, color=project_status.color) if project_status else None

        try:
            participants = project.participants or []
        except Exception:
            participants = []

        participants_preview = [
            ParticipantPreview(
                id=p.participant_id,
                full_name=f"{p.participant.first_name} {p.participant.last_name}",
                avatar_url=getattr(p.participant, "avatar_url", None),
            )
            for p in participants
            if p.participant
        ]

        try:
            all_responses = project.responses or []
        except Exception:
            all_responses = []

        # Роль и резюме участника берём из отклика, закрепившего его в команде:
        # это либо принятое приглашение (``accepted``), либо подтверждённое
        # вступление по отклику (``in_team``). Учитывать только ``accepted``
        # нельзя: подтверждение переводит отклик в ``in_team``, и участник
        # оставался без роли. Раньше резюме не подставлялось вовсе, колонка
        # «Резюме» была пустой у всех.
        accepted_by_participant: dict[int, Response] = {}
        for r in all_responses:
            if r.status in ROLE_RESPONSE_STATUSES and r.respondent_id:
                accepted_by_participant[r.respondent_id] = r

        members = [
            ParticipantFull(
                id=p.id,
                user_id=p.participant_id,
                name=f"{p.participant.first_name} {p.participant.last_name}",
                role=_member_role(p, project, accepted_by_participant),
                contacts=getattr(p.participant, "email", ""),
                resume_url=_member_resume_url(p, accepted_by_participant, workspace_id=project.workspace_id),
                date_added=str(p.created_at.date()) if p.created_at else "",
            )
            for p in participants
            if p.participant
        ]

        replycants = []
        for r in all_responses:
            if not r.respondent:
                continue
            replycants.append(
                ResponseItem(
                    id=r.id,
                    user_id=r.respondent_id,
                    name=f"{r.respondent.first_name} {r.respondent.last_name}",
                    contacts=getattr(r.respondent, "email", ""),
                    resume_url=build_resume_url(r.resume_id, workspace_id=project.workspace_id),
                    response_date=str(r.created_at.date()) if r.created_at else "",
                    vacancy_id=getattr(r.vacancy, "id", None) if r.vacancy else None,
                    role=getattr(r.vacancy, "title", "") if r.vacancy else "",
                    type=r.type,
                    rejection_reason=r.rejection_reason,
                    allow_multi_project_participation=allow_multi_project_participation,
                    **resolve_busy_status(
                        r.status,
                        r.respondent_id,
                        busy_user_ids,
                        allow_multi_project_participation,
                    ),
                )
            )

        try:
            vacancies_list = project.vacancies or []
        except Exception:
            vacancies_list = []

        # Архивные роли (снятые из проекта) наружу не отдаются: в форме
        # правки, диалогах отклика и приглашения их быть не должно. Строки
        # в базе остаются — на них ссылается `response.vacancy_id`.
        vacancies = [
            VacancyItem(
                id=v.id,
                title=v.title,
                tasks=v.tasks or [],
                required_count=v.required_count,
            )
            for v in vacancies_list
            if not v.archived
        ]

        try:
            author = project.author
            author_name = f"{author.first_name} {author.last_name}".strip() if author else ""
            author_email = author.email if author else None
        except Exception:
            author_name = ""
            author_email = None

        has_user_applied = False
        if current_user_id is not None:
            has_user_applied = any(
                r.respondent_id == current_user_id and r.status == "pending" for r in all_responses if r.respondent
            )

        stages: list[ProjectStageInfo] = []
        try:
            project_type = project.project_type
            type_stages = getattr(project_type, "stages", []) or [] if project_type else []
        except Exception:
            type_stages = []
        current_stage_id = getattr(project, "current_stage_id", None)
        entry_by_stage = _stage_entry_times(project)
        project_created_at = getattr(project, "created_at", None)

        stages = [
            ProjectStageInfo(
                id=s.id,
                name=s.name,
                order=s.order,
                requires_approval=s.requires_approval,
                visible_to_participants=s.visible_to_participants,
                is_current=(s.id == current_stage_id),
                duration_days=s.duration_days,
                deadline=(
                    (entry_by_stage.get(s.id) or project_created_at) + timedelta(days=s.duration_days)
                    if s.duration_days
                    else None
                ),
            )
            for s in type_stages
        ]

        return ProjectFull(
            id=project.id,
            name=project.name,
            author_id=project.author_id,
            author_name=author_name,
            author_email=author_email,
            theme=project.theme,
            description=project.description,
            max_participants=project.max_participants,
            status_id=project.status_id,
            deadline=project.deadline,
            progress=project.progress,
            tags=tags,
            workspace_id=project.workspace_id,
            created_at=project.created_at,
            status=status,
            participants_count=len(members),
            participants_preview=participants_preview,
            members=members,
            replycants=replycants,
            vacancies=vacancies,
            has_user_applied=has_user_applied,
            project_type_id=project.project_type_id,
            current_stage_id=current_stage_id,
            stage_pending_approval=getattr(project, "stage_pending_approval", False),
            stages=stages,
            stage_rejection=_latest_rejection(project),
        )


class ProjectResponse(BaseModel):
    """Схема ответа с проектом"""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class ProjectListItem(BaseModel):
    """Схема элемента списка проектов"""

    id: int
    name: str
    status: ProjectStatusItem
    deadline: datetime | None = None
    theme: str | None = None
    description: str | None = None
    participants_count: int
    progress: int
    tags: list[str] = []
    participants_preview: list[ParticipantPreview] = []
    author_id: int
    current_stage_id: int | None = None
    current_stage_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(BaseModel):
    """Схема ответа со списком проектов"""

    items: list[ProjectListItem]
    total: int
    page: int
    limit: int
    total_pages: int


class ProjectFilterMember(BaseModel):
    """Участник проектов пространства — вариант фильтра «Участники»"""

    id: int
    full_name: str


class ProjectFilterOption(BaseModel):
    """Проект пространства — вариант фильтра по проектам"""

    id: int
    name: str


class ProjectFilterFacetsResponse(BaseModel):
    """Справочники для фильтров списка проектов пространства

    Отдельный ответ, а не поля в :class:`ProjectListResponse`: набор вариантов
    не должен зависеть от того, какая страница проектов сейчас открыта.
    """

    #: Названия этапов, а не статусов: у всех проектов статус «draft», а реальный
    #: жизненный цикл проекта задаётся его текущим этапом.
    stages: list[str]
    tags: list[str]
    members: list[ProjectFilterMember]
    projects: list[ProjectFilterOption]


class MyResponseItem(BaseModel):
    """Схема отклика текущего пользователя"""

    id: int
    project_id: int
    project_name: str
    description: str = ""
    role: str = ""
    resume_id: int | None = None
    resume_url: str = ""
    resume_title: str = ""
    date: str
    status: str
    #: Причина отказа при статусе ``rejected``, если её указал руководитель.
    rejection_reason: str | None = None
    busy_in_other_project: bool = False

    model_config = ConfigDict(from_attributes=True)


class MyResponseListResponse(BaseModel):
    """Схема ответа со списком откликов"""

    items: list[MyResponseItem]
    total: int


class MyInvitationItem(BaseModel):
    """Схема приглашения для текущего пользователя"""

    id: int
    project_id: int
    project_name: str
    description: str = ""
    inviter_name: str
    role: str = ""
    resume_id: int | None = None
    resume_url: str = ""
    resume_title: str = ""
    date: str
    status: str
    allow_multi_project_participation: bool = True
    busy_in_other_project: bool = False

    model_config = ConfigDict(from_attributes=True)


class MyInvitationListResponse(BaseModel):
    """Схема ответа со списком приглашений"""

    items: list[MyInvitationItem]
    total: int


class ResponseListItem(BaseModel):
    """Отклик или приглашение в общем списке по проектам.

    Плоская строка с контекстом проекта: группировку по проектам делает клиент,
    поэтому ``project_id``/``project_name`` идут рядом с самой записью.
    Поля повторяют :class:`ResponseItem`, но отдаются с производным статусом
    «уже в другой команде» — как в карточке проекта.
    """

    id: int
    project_id: int
    project_name: str = ""
    workspace_id: int | None = None
    workspace_name: str | None = None
    user_id: int
    name: str = ""
    respondent_email: str | None = None
    inviter_name: str | None = None
    vacancy_id: int | None = None
    role: str = ""
    resume_url: str = ""
    response_date: str = ""
    type: str = "response"
    status: str = "pending"
    rejection_reason: str | None = None
    allow_multi_project_participation: bool = True
    busy_in_other_project: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ResponseListResponse(BaseModel):
    """Страница общего списка откликов и приглашений"""

    items: list[ResponseListItem]
    total: int
    page: int
    limit: int
    total_pages: int


class MyProjectItem(BaseModel):
    """Схема проекта для страницы профиля"""

    id: int
    title: str
    description: str | None = None
    status: str
    progress: int
    start_date: str = ""
    members_count: int = 0
    roles: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class MyProjectListResponse(BaseModel):
    """Схема ответа со списком проектов пользователя"""

    items: list[MyProjectItem]
    total: int
