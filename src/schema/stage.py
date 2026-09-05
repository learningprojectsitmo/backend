from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectTypeCreate(BaseModel):
    """Схема для создания типа проекта"""

    name: str
    description: str | None = None
    workspace_id: int | None = None


class ProjectTypeUpdate(BaseModel):
    """Схема для обновления типа проекта"""

    name: str | None = None
    description: str | None = None


class ProjectStageCreate(BaseModel):
    """Схема для создания этапа"""

    name: str
    order: int
    requires_approval: bool = False
    duration_days: int | None = None


class ProjectStageUpdate(BaseModel):
    """Схема для обновления этапа"""

    name: str | None = None
    order: int | None = None
    requires_approval: bool | None = None
    duration_days: int | None = None


class ProjectStageItem(BaseModel):
    id: int
    name: str
    order: int
    requires_approval: bool
    duration_days: int | None = None

    model_config = ConfigDict(from_attributes=True)


class ProjectTypeFull(BaseModel):
    id: int
    name: str
    description: str | None = None
    stages: list[ProjectStageItem] = []

    model_config = ConfigDict(from_attributes=True)


class ProjectStageInfo(BaseModel):
    """Информация об этапах проекта в ответе ProjectFull"""

    id: int
    name: str
    order: int
    requires_approval: bool
    is_current: bool
    duration_days: int | None = None
    deadline: datetime | None = None


class StageTransitionItem(BaseModel):
    id: int
    project_id: int
    stage_name: str
    from_stage_name: str | None = None
    action: str
    comment: str | None = None
    actor_name: str = ""
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class StageHistoryResponse(BaseModel):
    items: list[StageTransitionItem]
    total: int


class RejectStageRequest(BaseModel):
    comment: str | None = None
