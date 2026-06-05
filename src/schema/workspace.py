from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WorkSpaceCreate(BaseModel):
    """Схема для создания workspace"""

    name: str
    author_id: int | None = None
    status_id: int | None = None
    category_id: int | None = None
    color: str | None = None
    description: str | None = None


class WorkSpaceUpdate(BaseModel):
    """Схема для обновления workspace"""

    name: str | None = None
    status_id: int | None = None
    category_id: int | None = None
    color: str | None = None
    description: str | None = None


class WorkSpaceFull(WorkSpaceCreate):
    """Полная схема workspace"""

    id: int
    author_id: int
    status_id: int
    category_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class WorkSpaceResponse(BaseModel):
    """Схема ответа с workspace"""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class Space(BaseModel):
    """Схема workspace для списка с расширенными данными"""

    id: int
    title: str
    projectsCount: int
    membersCount: int
    color: str
    category: str
    category_id: int | None = None
    description: str | None = None
    icon_url: str | None = None
    author_id: int


class Category(BaseModel):
    """Схема категории workspace"""

    id: int
    name: str
    color: str | None = None


class SpacesListResponse(BaseModel):
    """Схема ответа со списком workspace"""

    categories: list[Category]
    spaces: list[Space]
    page: int | None = None
    limit: int | None = None
    total: int | None = None
    role: str


class ProjectRef(BaseModel):
    """Краткая ссылка на проект"""

    id: int
    title: str

    model_config = ConfigDict(from_attributes=True)


class ParticipantContact(BaseModel):
    """Контакты участника"""

    telegram: str | None = None
    email: str | None = None
    linkedin: str | None = None


class WorkspaceParticipantItem(BaseModel):
    """Участник рабочего пространства"""

    id: int
    user_id: int
    name: str
    avatar_url: str | None = None
    projects: list[ProjectRef] = []
    role: str = ""
    contacts: ParticipantContact = ParticipantContact()
    resume_url: str = ""
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class WorkspaceParticipantListResponse(BaseModel):
    """Список участников workspace с пагинацией"""

    items: list[WorkspaceParticipantItem]
    total: int
    page: int
    limit: int
    total_pages: int


class WorkspaceResumeItem(BaseModel):
    """Резюме участника workspace (упрощённое, для карточек)"""

    id: int
    header: str
    skills: list[str] = []
    interests: list[str] = []
    participant_name: str
    participant_id: int

    model_config = ConfigDict(from_attributes=True)


class WorkspaceResumeListResponse(BaseModel):
    """Список резюме участников workspace"""

    items: list[WorkspaceResumeItem]
    total: int
