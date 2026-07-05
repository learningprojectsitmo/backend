from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.model.project import Project


class ParticipantPreview(BaseModel):
    id: int
    full_name: str
    avatar_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ParticipantFull(BaseModel):
    id: int
    user_id: int
    name: str
    role: str = ""
    contacts: str = ""
    resume_url: str = ""
    date_added: str

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


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
    title: str
    tasks: list[str] = []
    required_count: int = 1


class ProjectCreate(BaseModel):
    """Схема для создания проекта"""

    name: str
    author_id: int | None = None
    description: str | None = None
    max_participants: int | None = None
    status_id: int | None = None
    deadline: datetime | None = None
    progress: int | None = None
    tags: list[str] | None = None
    workspace_id: int | None = None
    vacancies: list[VacancyCreate] | None = None


class ApplyRequest(BaseModel):
    vacancy_id: int | None = None
    resume_id: int | None = None


class InviteRequest(BaseModel):
    user_id: int
    vacancy_id: int | None = None
    resume_id: int | None = None


class ProjectUpdate(BaseModel):
    """Схема для обновления проекта"""

    name: str | None = None
    author_id: int | None = None
    description: str | None = None
    max_participants: int | None = None
    status_id: int | None = None
    deadline: datetime | None = None
    progress: int | None = None
    tags: list[str] | None = None
    workspace_id: int | None = None
    vacancies: list[VacancyCreate] | None = None


class ProjectFull(ProjectCreate):
    """Полная схема проекта"""

    id: int
    workspace_id: int | None = None
    created_at: datetime | None = None
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

    model_config = ConfigDict(from_attributes=True)

    @staticmethod
    def from_orm(project: Project, current_user_id: int | None = None) -> ProjectFull:
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

        # Build a lookup: participant_id -> vacancy title from accepted response
        accepted_role_map: dict[int, str] = {}
        for r in all_responses:
            if r.status == "accepted" and r.respondent_id:
                title = getattr(r.vacancy, "title", "") if r.vacancy else ""
                accepted_role_map[r.respondent_id] = title

        members = [
            ParticipantFull(
                id=p.id,
                user_id=p.participant_id,
                name=f"{p.participant.first_name} {p.participant.last_name}",
                role=accepted_role_map.get(p.participant_id, ""),
                contacts=getattr(p.participant, "email", ""),
                date_added=str(p.created_at.date()) if p.created_at else "",
            )
            for p in participants
            if p.participant
        ]

        replycants = [
            ResponseItem(
                id=r.id,
                user_id=r.respondent_id,
                name=f"{r.respondent.first_name} {r.respondent.last_name}",
                contacts=getattr(r.respondent, "email", ""),
                response_date=str(r.created_at.date()) if r.created_at else "",
                vacancy_id=getattr(r.vacancy, "id", None) if r.vacancy else None,
                role=getattr(r.vacancy, "title", "") if r.vacancy else "",
                type=r.type,
                status=r.status,
            )
            for r in all_responses
            if r.respondent
        ]

        try:
            vacancies_list = project.vacancies or []
        except Exception:
            vacancies_list = []

        vacancies = [
            VacancyItem(
                id=v.id,
                title=v.title,
                tasks=v.tasks or [],
                required_count=v.required_count,
            )
            for v in vacancies_list
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

        return ProjectFull(
            id=project.id,
            name=project.name,
            author_id=project.author_id,
            author_name=author_name,
            author_email=author_email,
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
    description: str | None = None
    participants_count: int
    progress: int
    tags: list[str] = []
    participants_preview: list[ParticipantPreview] = []

    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(BaseModel):
    """Схема ответа со списком проектов"""

    items: list[ProjectListItem]
    total: int
    page: int
    limit: int
    total_pages: int


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

    model_config = ConfigDict(from_attributes=True)


class MyInvitationListResponse(BaseModel):
    """Схема ответа со списком приглашений"""

    items: list[MyInvitationItem]
    total: int


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
