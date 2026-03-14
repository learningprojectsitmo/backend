from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from src.model.models import TaskStatus, TaskPriority

from pydantic import BaseModel, Field, validator


# Базовые схемы
class TaskBase(BaseModel):
    """Базовая схема задачи"""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: Optional[datetime] = None
    tags: Optional[List[str]] = None


class TaskCreate(TaskBase):
    """Схема создания задачи"""
    project_id: int
    assignee_ids: Optional[List[int]] = []


class TaskUpdate(BaseModel):
    """Схема обновления задачи"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[datetime] = None
    tags: Optional[List[str]] = None
    assignee_ids: Optional[List[int]] = None


class TaskStatusUpdate(BaseModel):
    """Схема обновления статуса задачи"""
    status: TaskStatus
    order: int


# Схемы для ответов
class TaskAssigneeInfo(BaseModel):
    """Информация об ответственном за задачу"""
    id: int
    first_name: str
    last_name: str
    middle_name: Optional[str] = None
    email: Optional[str] = None

    class Config:
        from_attributes = True


class TaskResponse(TaskBase):
    """Схема ответа с задачей"""
    id: int
    status: TaskStatus
    order: int
    project_id: int
    created_by_id: int
    created_at: datetime
    updated_at: datetime
    
    # Вложенные объекты
    assignees: List[TaskAssigneeInfo] = []
    created_by: Optional[TaskAssigneeInfo] = None

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
    changed_by: TaskAssigneeInfo
    old_status: Optional[TaskStatus] = None
    new_status: Optional[TaskStatus] = None
    change_type: str
    created_at: datetime

    class Config:
        from_attributes = True


# Схемы для колонок
class ColumnTemplateBase(BaseModel):
    """Базовая схема колонки"""
    name: str = Field(..., min_length=1, max_length=50)
    color: str = Field(..., description="Hex color or color name")
    task_status: TaskStatus
    allowed_roles: str = "bachelor"


class ColumnTemplateCreate(ColumnTemplateBase):
    """Схема создания колонки"""
    project_id: int


class ColumnTemplateUpdate(BaseModel):
    """Схема обновления колонки"""
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    color: Optional[str] = None
    task_status: Optional[TaskStatus] = None
    allowed_roles: Optional[List[str]] = None
    order: Optional[int] = None


class ColumnTemplateResponse(ColumnTemplateBase):
    """Схема ответа с колонкой"""
    id: int
    project_id: int
    order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ColumnTemplateListResponse(BaseModel):
    """Схема списка колонок"""
    items: List[ColumnTemplateResponse]
    total: int


class ColumnWithTasksResponse(ColumnTemplateResponse):
    """Схема колонки с задачами"""
    tasks: List[TaskResponse] = []
    task_count: int = 0


# Схемы для поиска и фильтрации
class TaskFilter(BaseModel):
    """Схема фильтрации задач"""
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    assignee_id: Optional[int] = None
    created_by_id: Optional[int] = None
    tag: Optional[str] = None
    search: Optional[str] = None
    project_id: Optional[int] = None


class TaskReorder(BaseModel):
    """Схема для изменения порядка задач"""
    tasks: List[dict]  # [{"id": 1, "order": 0}, ...]