from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status

from src.core.container import get_kanban_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.models import User
from src.schema.kanban import (
    # Задачи
    TaskResponse, TaskCreate, TaskUpdate, TaskMove,
    TaskListResponse, TaskHistoryResponse, TaskFilter,
    # Колонки
    ColumnResponse, ColumnCreate, ColumnUpdate,
    ColumnListResponse,
    # Прочее
    ProjectBoardResponse, TaskReorder
)
from src.services.kanban_service import KanbanService

kanban_router = APIRouter(prefix="/kanban", tags=["kanban"])


# ========== ЭНДПОЙНТЫ ДЛЯ КАНБАН-ДОСКИ ==========

@kanban_router.get("/{project_id}", response_model=ProjectBoardResponse)
async def get_board(
    project_id: int = Path(..., ge=1, description="ID проекта"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
) -> ProjectBoardResponse:
    """Получить полную канбан-доску проекта"""
    try:
        return await kanban_service.get_board(project_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    

# ========== ЭНДПОЙНТЫ ДЛЯ ЗАДАЧ ==========

@kanban_router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int = Path(..., ge=1, description="ID задачи"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    """Получить задачу по ID"""
    try:
        return await kanban_service.get_task_by_id(task_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@kanban_router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> TaskResponse:
    """Создать новую задачу в указанной колонке"""
    try:
        return await kanban_service.create_task(task_data, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create task: {e!s}")


@kanban_router.put("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int = Path(..., ge=1, description="ID задачи"),
    task_data: TaskUpdate = ...,
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> TaskResponse:
    """Обновить задачу"""
    try:
        return await kanban_service.update_task(task_id, task_data, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update task: {e!s}")


@kanban_router.patch("/tasks/{task_id}/move", response_model=TaskResponse)
async def move_task(
    task_id: int = Path(..., ge=1, description="ID задачи"),
    move_data: TaskMove = ...,
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> TaskResponse:
    """Переместить задачу (drag-and-drop)"""
    try:
        return await kanban_service.move_task(task_id, move_data, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to move task: {e!s}")


@kanban_router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int = Path(..., ge=1, description="ID задачи"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> dict:
    """Удалить задачу"""
    try:
        success = await kanban_service.delete_task(task_id, current_user.id)
        if not success:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Task deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete task: {e!s}")


@kanban_router.post("/tasks/column/{column_id}/reorder", response_model=dict)
async def reorder_tasks_in_column(
    column_id: int = Path(..., ge=1, description="ID колонки"),
    task_orders: TaskReorder = ...,
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> dict:
    """Изменить порядок задач в колонке"""
    try:
        success = await kanban_service.reorder_tasks_in_column(
            column_id=column_id,
            task_orders=task_orders.tasks
        )
        return {"message": "Tasks reordered successfully", "success": success}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to reorder tasks: {e!s}")


@kanban_router.get("/tasks/filter/{project_id}", response_model=TaskListResponse)
async def filter_tasks(
    project_id: int = Path(..., ge=1, description="ID проекта"),
    column_id: Optional[int] = Query(None, description="Фильтр по колонке"),
    priority: Optional[str] = Query(None, description="Фильтр по приоритету"),
    assignee_id: Optional[int] = Query(None, description="Фильтр по ответственному"),
    created_by_id: Optional[int] = Query(None, description="Фильтр по автору"),
    tag: Optional[str] = Query(None, description="Фильтр по тегу"),
    search: Optional[str] = Query(None, description="Поиск по названию/описанию"),
    due_before: Optional[str] = Query(None, description="Дедлайн до"),
    due_after: Optional[str] = Query(None, description="Дедлайн после"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=1, le=100, description="Размер страницы"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
) -> TaskListResponse:
    """Отфильтровать задачи по различным критериям"""
    from datetime import datetime
    
    filters = TaskFilter(
        column_id=column_id,
        priority=priority,
        assignee_id=assignee_id,
        created_by_id=created_by_id,
        tag=tag,
        search=search,
        due_before=datetime.fromisoformat(due_before) if due_before else None,
        due_after=datetime.fromisoformat(due_after) if due_after else None
    )
    
    return await kanban_service.filter_tasks(project_id, filters, page, page_size)


@kanban_router.get("/tasks/{task_id}/history", response_model=List[TaskHistoryResponse])
async def get_task_history(
    task_id: int = Path(..., ge=1, description="ID задачи"),
    limit: int = Query(50, ge=1, le=200, description="Количество записей"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
) -> List[TaskHistoryResponse]:
    """Получить историю изменений задачи"""
    try:
        return await kanban_service.get_task_history(task_id, limit)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get task history: {e!s}")


# ========== ЭНДПОЙНТЫ ДЛЯ КОЛОНОК ==========

@kanban_router.get("/columns/project/{project_id}", response_model=ColumnListResponse)
async def get_project_columns(
    project_id: int = Path(..., ge=1, description="ID проекта"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
) -> ColumnListResponse:
    """Получить все колонки проекта (без задач)"""
    columns = await kanban_service.get_project_columns(project_id)
    return ColumnListResponse(items=columns, total=len(columns))


@kanban_router.post("/columns", response_model=ColumnResponse, status_code=status.HTTP_201_CREATED)
async def create_column(
    column_data: ColumnCreate,
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> ColumnResponse:
    """Создать новую колонку"""
    try:
        return await kanban_service.create_column(column_data, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create column: {e!s}")


@kanban_router.put("/columns/{column_id}", response_model=ColumnResponse)
async def update_column(
    column_id: int = Path(..., ge=1, description="ID колонки"),
    column_data: ColumnUpdate = ...,
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> ColumnResponse:
    """Обновить колонку"""
    try:
        return await kanban_service.update_column(column_id, column_data, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update column: {e!s}")


@kanban_router.delete("/columns/{column_id}")
async def delete_column(
    column_id: int = Path(..., ge=1, description="ID колонки"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> dict:
    """Удалить колонку"""
    try:
        success = await kanban_service.delete_column(column_id, current_user.id)
        if not success:
            raise HTTPException(status_code=404, detail="Column not found")
        return {"message": "Column deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete column: {e!s}")


@kanban_router.post("/columns/project/{project_id}/reorder", response_model=dict)
async def reorder_columns(
    project_id: int = Path(..., ge=1, description="ID проекта"),
    column_orders: TaskReorder = ...,
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> dict:
    """Изменить порядок колонок"""
    try:
        success = await kanban_service.reorder_columns(
            project_id=project_id,
            column_orders=column_orders.tasks,
            current_user_id=current_user.id
        )
        return {"message": "Columns reordered successfully", "success": success}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to reorder columns: {e!s}")

# ========== ЭНДПОЙНТЫ ДЛЯ СТАТИСТИКИ ==========

@kanban_router.get("/stats/{project_id}", response_model=dict)
async def get_project_stats(
    project_id: int = Path(..., ge=1, description="ID проекта"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Получить статистику по задачам проекта"""
    
    try:
        return await kanban_service.get_project_stats(project_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))