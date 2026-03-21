from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

from src.schema.user import UserResponse


# ========== Базовые типы ==========

class TaskPriority(str):
    """Приоритет задачи (опционально)"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

# ========== Схемы для задач ==========

class TaskBase(BaseModel):
    """Базовая схема задачи"""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    priority: Optional[str] = Field(None, pattern="^(low|medium|high|urgent)$")
    due_date: Optional[datetime] = None
    tags: Optional[List[str]] = None

class TaskCreate(TaskBase):
    """Схема создания задачи"""
    column_id: int = Field(..., description="ID колонки, куда поместить задачу")
    assignee_ids: Optional[List[int]] = []

class TaskUpdate(BaseModel):
    """Схема обновления задачи"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    priority: Optional[str] = Field(None, pattern="^(low|medium|high|urgent)$")
    column_id: Optional[int] = Field(None, description="ID новой колонки (для перемещения)")
    position: Optional[int] = Field(None, description="Новая позиция в колонке")
    due_date: Optional[datetime] = None
    tags: Optional[List[str]] = None
    assignee_ids: Optional[List[int]] = None

class TaskMove(BaseModel):
    """Схема для перемещения задачи (drag-and-drop)"""
    column_id: int = Field(..., description="ID целевой колонки")
    position: int = Field(..., description="Новая позиция в колонке")

class TaskReorder(BaseModel):
    """Схема для изменения порядка задач в колонке"""
    tasks: List[dict] = Field(..., description='[{"id": 1, "position": 0}, ...]')

# ========== Схемы для ответов ==========

class TaskResponse(BaseModel):
    """Схема ответа с задачей"""
    id: int
    title: str
    description: Optional[str] = None
    priority: Optional[str] = None
    position: int
    column_id: int
    project_id: int
    created_by_id: int
    due_date: Optional[datetime] = None
    tags: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    # Вложенные объекты — используем существующие схемы пользователя
    assignees: List[UserResponse] = []
    created_by: Optional[UserResponse] = None

    class Config:
        from_attributes = True

class TaskListResponse(BaseModel):
    """Схема списка задач"""
    items: List[TaskResponse]
    total: int

class TaskHistoryResponse(BaseModel):
    """Схема истории изменений задачи"""
    id: int
    task_id: int
    changed_by: UserResponse
    old_column_id: Optional[int] = None
    new_column_id: Optional[int] = None
    change_type: str  # "move", "title", "description", "assignees"
    change_data: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True

# ========== Схемы для колонок ==========

class ColumnBase(BaseModel):
    """Базовая схема колонки"""
    name: str = Field(..., min_length=1, max_length=50)
    color: str = Field("gray", description="Цвет колонки (hex или имя)")
    wip_limit: Optional[int] = Field(None, ge=1, description="Лимит задач в колонке")

class ColumnCreate(ColumnBase):
    """Схема создания колонки"""
    project_id: int

class ColumnUpdate(BaseModel):
    """Схема обновления колонки"""
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    color: Optional[str] = None
    position: Optional[int] = Field(None, ge=0)
    wip_limit: Optional[int] = Field(None, ge=1)

class ColumnResponse(ColumnBase):
    """Схема ответа с колонкой"""
    id: int
    project_id: int
    position: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ColumnWithTasksResponse(ColumnResponse):
    """Схема колонки с задачами"""
    tasks: List[TaskResponse] = []
    task_count: int = 0

class ColumnListResponse(BaseModel):
    """Схема списка колонок"""
    items: List[ColumnResponse]
    total: int

# ========== Схемы для проектов ==========

class ProjectBoardResponse(BaseModel):
    """Схема канбан-доски проекта"""
    project_id: int
    project_name: str
    columns: List[ColumnWithTasksResponse]

# ========== Схемы для фильтрации ==========

class TaskFilter(BaseModel):
    """Схема фильтрации задач"""
    column_id: Optional[int] = None
    priority: Optional[str] = Field(None, pattern="^(low|medium|high|urgent)$")
    assignee_id: Optional[int] = None
    created_by_id: Optional[int] = None
    tag: Optional[str] = None
    search: Optional[str] = None
    due_before: Optional[datetime] = None
    due_after: Optional[datetime] = None