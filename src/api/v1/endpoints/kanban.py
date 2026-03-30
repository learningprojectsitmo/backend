from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from src.core.container import get_kanban_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.models import User
from src.schema.kanban import (
    ColumnCreate,
    ColumnListResponse,
    ColumnResponse,
    ColumnUpdate,
    ProjectBoardResponse,
    SubtaskCreate,
    SubtaskListResponse,
    SubtaskReorder,
    SubtaskResponse,
    SubtaskUpdate,
    TaskCreate,
    TaskFilter,
    TaskHistoryResponse,
    TaskListResponse,
    TaskMove,
    TaskReorder,
    TaskResponse,
    TaskUpdate,
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
        raise HTTPException(status_code=404, detail=str(e)) from e


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
        raise HTTPException(status_code=400, detail=f"Failed to create column: {e!s}") from e


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
        raise HTTPException(status_code=400, detail=f"Failed to update column: {e!s}") from e


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

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete column: {e!s}") from e
    else:
        if not success:
            raise HTTPException(status_code=404, detail="Column not found")
        return {"message": "Column deleted successfully"}


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
            project_id=project_id, column_orders=column_orders.tasks, current_user_id=current_user.id
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to reorder columns: {e!s}") from e
    else:
        return {"message": "Columns reordered successfully", "success": success}


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
        raise HTTPException(status_code=404, detail=str(e)) from e


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
        raise HTTPException(status_code=400, detail=f"Failed to create task: {e!s}") from e


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
        raise HTTPException(status_code=400, detail=f"Failed to update task: {e!s}") from e


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
        raise HTTPException(status_code=400, detail=f"Failed to move task: {e!s}") from e


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

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete task: {e!s}") from e
    else:
        if not success:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"message": "Task deleted successfully"}


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
        success = await kanban_service.reorder_tasks_in_column(column_id=column_id, task_orders=task_orders.tasks)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to reorder tasks: {e!s}") from e
    else:
        return {"message": "Tasks reordered successfully", "success": success}


# ========== ЭНДПОЙНТЫ ДЛЯ ПОДЗАДАЧ ==========


@kanban_router.get("/tasks/{task_id}/subtasks", response_model=SubtaskListResponse)
async def get_task_subtasks(
    task_id: int = Path(..., ge=1, description="ID задачи"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
) -> SubtaskListResponse:
    """Получить все подзадачи задачи"""
    try:
        return await kanban_service.get_subtasks_by_task(task_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@kanban_router.get("/subtasks/{subtask_id}", response_model=SubtaskResponse)
async def get_subtask(
    subtask_id: int = Path(..., ge=1, description="ID подзадачи"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
) -> SubtaskResponse:
    """Получить подзадачу по ID"""
    try:
        return await kanban_service.get_subtask_by_id(subtask_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@kanban_router.post("/subtasks", response_model=SubtaskResponse, status_code=status.HTTP_201_CREATED)
async def create_subtask(
    subtask_data: SubtaskCreate = ...,
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> SubtaskResponse:
    """Создать новую подзадачу"""
    try:
        return await kanban_service.create_subtask(subtask_data, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create subtask: {e!s}") from e


@kanban_router.put("/subtasks/{subtask_id}", response_model=SubtaskResponse)
async def update_subtask(
    subtask_id: int = Path(..., ge=1, description="ID подзадачи"),
    subtask_data: SubtaskUpdate = ...,
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> SubtaskResponse:
    """Обновить подзадачу"""
    try:
        return await kanban_service.update_subtask(subtask_id, subtask_data, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update subtask: {e!s}") from e


@kanban_router.delete("/subtasks/{subtask_id}")
async def delete_subtask(
    subtask_id: int = Path(..., ge=1, description="ID подзадачи"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> dict:
    """Удалить подзадачу"""
    try:
        success = await kanban_service.delete_subtask(subtask_id, current_user.id)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete subtask: {e!s}") from e
    else:
        if not success:
            raise HTTPException(status_code=404, detail="Subtask not found")
        return {"message": "Subtask deleted successfully"}


@kanban_router.patch("/subtasks/{subtask_id}/toggle", response_model=SubtaskResponse)
async def toggle_subtask_completion(
    subtask_id: int = Path(..., ge=1, description="ID подзадачи"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> SubtaskResponse:
    """Переключить статус выполнения подзадачи"""
    try:
        return await kanban_service.toggle_subtask_completion(subtask_id, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to toggle subtask: {e!s}") from e


@kanban_router.post("/tasks/{task_id}/subtasks/reorder", response_model=dict)
async def reorder_subtasks(
    task_id: int = Path(..., ge=1, description="ID задачи"),
    subtask_orders: SubtaskReorder = ...,
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> dict:
    """Изменить порядок подзадач"""
    try:
        success = await kanban_service.reorder_subtasks(
            task_id=task_id, subtask_orders=subtask_orders.subtasks, current_user_id=current_user.id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to reorder subtasks: {e!s}") from e
    else:
        return {"message": "Subtasks reordered successfully", "success": success}


# ========== ЭНДПОЙНТЫ ДЛЯ ФИЛЬТРАЦИИ ==========


@kanban_router.get("/tasks/filter/{project_id}", response_model=TaskListResponse)
async def filter_tasks(
    project_id: int = Path(..., ge=1, description="ID проекта"),
    column_id: int | None = Query(None, description="Фильтр по колонке"),
    priority: str | None = Query(None, description="Фильтр по приоритету"),
    assignee_id: int | None = Query(None, description="Фильтр по ответственному"),
    created_by_id: int | None = Query(None, description="Фильтр по автору"),
    tag: str | None = Query(None, description="Фильтр по тегу"),
    search: str | None = Query(None, description="Поиск по названию/описанию"),
    due_before: str | None = Query(None, description="Дедлайн до"),
    due_after: str | None = Query(None, description="Дедлайн после"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=1, le=100, description="Размер страницы"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
) -> TaskListResponse:
    """Отфильтровать задачи по различным критериям"""

    filters = TaskFilter(
        column_id=column_id,
        priority=priority,
        assignee_id=assignee_id,
        created_by_id=created_by_id,
        tag=tag,
        search=search,
        due_before=datetime.fromisoformat(due_before) if due_before else None,
        due_after=datetime.fromisoformat(due_after) if due_after else None,
    )

    return await kanban_service.filter_tasks(project_id, filters, page, page_size)


# ========== ЭНДПОЙНТЫ ДЛЯ ИСТОРИИ ==========


@kanban_router.get("/tasks/{task_id}/history", response_model=list[TaskHistoryResponse])
async def get_task_history(
    task_id: int = Path(..., ge=1, description="ID задачи"),
    limit: int = Query(50, ge=1, le=200, description="Количество записей"),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
) -> list[TaskHistoryResponse]:
    """Получить историю изменений задачи"""
    try:
        return await kanban_service.get_task_history(task_id, limit)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get task history: {e!s}") from e


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
        raise HTTPException(status_code=404, detail=str(e)) from e
