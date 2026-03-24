from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.schema.user import UserResponse

# ========== Базовые типы ==========


class TaskPriority(str):
    """Приоритет задачи (опционально)"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


# ========== Схемы для проектов ==========


class ProjectBoardResponse(BaseModel):
    """Схема канбан-доски проекта"""

    project_id: int
    project_name: str
    columns: list[ColumnWithTasksAndSubtasksResponse]


# ========== Схемы для колонок ==========


class ColumnBase(BaseModel):
    """Базовая схема колонки"""

    name: str = Field(..., min_length=1, max_length=50)
    color: str = Field("gray", description="Цвет колонки (hex или имя)")
    wip_limit: int | None = Field(None, ge=1, description="Лимит задач в колонке")


class ColumnCreate(ColumnBase):
    """Схема создания колонки"""

    project_id: int


class ColumnUpdate(BaseModel):
    """Схема обновления колонки"""

    name: str | None = Field(None, min_length=1, max_length=50)
    color: str | None = None
    position: int | None = Field(None, ge=0)
    wip_limit: int | None = Field(None, ge=1)


class ColumnResponse(ColumnBase):
    """Схема ответа с колонкой"""

    id: int
    project_id: int
    position: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ColumnWithTasksAndSubtasksResponse(ColumnResponse):
    """Схема колонки с задачами"""

    tasks: list[TaskWithSubtasksResponse] = []
    task_count: int = 0


class ColumnListResponse(BaseModel):
    """Схема списка колонок"""

    items: list[ColumnResponse]
    total: int


# ========== Схемы для задач ==========


class TaskBase(BaseModel):
    """Базовая схема задачи"""

    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    priority: str | None = Field(None, pattern="^(low|medium|high|urgent)$")
    due_date: datetime | None = None
    tags: list[str] | None = None


class TaskCreate(TaskBase):
    """Схема создания задачи"""

    column_id: int = Field(..., description="ID колонки, куда поместить задачу")
    assignee_ids: list[int] | None = []


class TaskUpdate(BaseModel):
    """Схема обновления задачи"""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    priority: str | None = Field(None, pattern="^(low|medium|high|urgent)$")
    column_id: int | None = Field(None, description="ID новой колонки (для перемещения)")
    position: int | None = Field(None, description="Новая позиция в колонке")
    due_date: datetime | None = None
    tags: list[str] | None = None
    assignee_ids: list[int] | None = None


class TaskMove(BaseModel):
    """Схема для перемещения задачи (drag-and-drop)"""

    column_id: int = Field(..., description="ID целевой колонки")
    position: int = Field(..., description="Новая позиция в колонке")


class TaskReorder(BaseModel):
    """Схема для изменения порядка задач в колонке"""

    tasks: list[dict] = Field(..., description='[{"id": 1, "position": 0}, ...]')


class TaskResponse(BaseModel):
    """Схема ответа с задачей"""

    id: int
    title: str
    description: str | None = None
    priority: str | None = None
    position: int
    column_id: int
    project_id: int
    created_by_id: int
    due_date: datetime | None = None
    tags: str | None = None
    created_at: datetime
    updated_at: datetime

    # Вложенные объекты — используем существующие схемы пользователя
    assignees: list[UserResponse] = []
    created_by: UserResponse | None = None

    class Config:
        from_attributes = True


class TaskWithSubtasksResponse(TaskResponse):
    """Схема задачи с подзадачами"""

    subtasks: list[SubtaskResponse] = []
    subtask_count: int = 0


class TaskListResponse(BaseModel):
    """Схема списка задач"""

    items: list[TaskResponse]
    total: int


class TaskHistoryResponse(BaseModel):
    """Схема истории изменений задачи"""

    id: int
    task_id: int
    changed_by: UserResponse
    old_column_id: int | None = None
    new_column_id: int | None = None
    change_type: str  # "move", "title", "description", "assignees"
    change_data: dict | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# ========== Схемы для подзадач ==========


class SubtaskBase(BaseModel):
    """Базовая схема подзадачи"""

    title: str = Field(..., min_length=1, max_length=200)
    is_completed: bool = False


class SubtaskCreate(SubtaskBase):
    """Схема создания подзадачи"""

    task_id: int = Field(..., description="ID родительской задачи")


class SubtaskUpdate(BaseModel):
    """Схема обновления подзадачи"""

    title: str | None = Field(None, min_length=1, max_length=200)
    is_completed: bool | None = None
    position: int | None = Field(None, ge=0, description="Новая позиция в списке")


class SubtaskReorder(BaseModel):
    """Схема для изменения порядка подзадач"""

    subtasks: list[dict] = Field(..., description='[{"id": 1, "position": 0}, ...]')


class SubtaskResponse(SubtaskBase):
    """Схема ответа с подзадачей"""

    id: int
    task_id: int
    position: int
    created_by_id: int
    created_by: UserResponse | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubtaskListResponse(BaseModel):
    """Схема списка подзадач"""

    items: list[SubtaskResponse]
    total: int


# ========== Схемы для фильтрации ==========


class TaskFilter(BaseModel):
    """Схема фильтрации задач"""

    column_id: int | None = None
    priority: str | None = Field(None, pattern="^(low|medium|high|urgent)$")
    assignee_id: int | None = None
    created_by_id: int | None = None
    tag: str | None = None
    search: str | None = None
    due_before: datetime | None = None
    due_after: datetime | None = None
