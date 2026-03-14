from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Path

from src.core.container import get_task_service, get_project_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.models import User
from src.schema.task import (
    TaskResponse, TaskCreate, TaskUpdate, TaskStatusUpdate,
    TaskListResponse, TaskHistoryResponse, TaskFilter,
    ColumnTemplateResponse, ColumnTemplateCreate, ColumnTemplateUpdate,
    ColumnTemplateListResponse, ColumnWithTasksResponse,
    TaskReorder
)
from src.services.task_service import TaskService
from src.services.project_service import ProjectService

task_router = APIRouter(prefix="/tasks", tags=["tasks"])


# === Эндпоинты для задач ===

@task_router.get("/project/{project_id}", response_model=TaskListResponse)
async def get_project_tasks(
    project_id: int = Path(..., ge=1, description="ID проекта"),
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    priority: Optional[str] = Query(None, description="Фильтр по приоритету"),
    assignee_id: Optional[int] = Query(None, description="Фильтр по ответственному"),
    created_by_id: Optional[int] = Query(None, description="Фильтр по автору"),
    tag: Optional[str] = Query(None, description="Фильтр по тегу"),
    search: Optional[str] = Query(None, description="Поиск по названию/описанию"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=1, le=100, description="Размер страницы"),
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
) -> TaskListResponse:
    """Получить задачи проекта с фильтрацией и пагинацией"""
    
    # Создаем объект фильтрации
    filters = TaskFilter(
        status=status,
        priority=priority,
        assignee_id=assignee_id,
        created_by_id=created_by_id,
        tag=tag,
        search=search
    )
    
    result = await task_service.get_tasks_by_project(
        project_id=project_id,
        filters=filters,
        page=page,
        page_size=page_size
    )
    
    return TaskListResponse(
        items=result["items"],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"]
    )


@task_router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int = Path(..., ge=1, description="ID задачи"),
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
) -> TaskResponse:
    """Получить задачу по ID"""
    
    try:
        task = await task_service.get_by_id(task_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    
    return TaskResponse.model_validate(task)


@task_router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(
    task_data: TaskCreate,
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> TaskResponse:
    """Создать новую задачу"""
    
    try:
        task = await task_service.create_task(task_data, current_user.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create task: {e!s}") from e
    
    return TaskResponse.model_validate(task)


@task_router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int = Path(..., ge=1, description="ID задачи"),
    task_data: TaskUpdate = ...,
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> TaskResponse:
    """Обновить задачу"""
    
    try:
        task = await task_service.update_task(task_id, task_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update task: {e!s}") from e
    
    return TaskResponse.model_validate(task)


@task_router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: int = Path(..., ge=1, description="ID задачи"),
    status_update: TaskStatusUpdate = ...,
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> TaskResponse:
    """Обновить статус задачи (для drag-and-drop)"""
    
    try:
        task = await task_service.update_task_status(
            task_id, 
            status_update, 
            current_user.id
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update task status: {e!s}") from e
    
    return TaskResponse.model_validate(task)


@task_router.post("/project/{project_id}/reorder", response_model=dict)
async def reorder_tasks(
    project_id: int = Path(..., ge=1, description="ID проекта"),
    status: TaskStatusUpdate = ...,
    task_orders: TaskReorder = ...,
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> dict:
    """Изменить порядок задач в колонке (только для магистров/преподавателей)"""
    
    try:
        success = await task_service.reorder_tasks(
            project_id=project_id,
            status=status.status,
            task_orders=task_orders.tasks,
            current_user_id=current_user.id
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to reorder tasks: {e!s}") from e
    
    return {"message": "Tasks reordered successfully", "success": success}


@task_router.delete("/{task_id}")
async def delete_task(
    task_id: int = Path(..., ge=1, description="ID задачи"),
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> dict:
    """Удалить задачу"""
    
    try:
        success = await task_service.delete_task(task_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete task: {e!s}") from e
    
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {"message": "Task deleted successfully"}


# === Эндпоинты для истории задач ===

@task_router.get("/{task_id}/history", response_model=List[TaskHistoryResponse])
async def get_task_history(
    task_id: int = Path(..., ge=1, description="ID задачи"),
    limit: int = Query(50, ge=1, le=200, description="Количество записей"),
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
) -> List[TaskHistoryResponse]:
    """Получить историю изменений задачи"""
    
    try:
        history = await task_service.get_task_history(task_id, current_user.id, limit)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get task history: {e!s}") from e
    
    return [TaskHistoryResponse.model_validate(h) for h in history]


# === Эндпоинты для колонок ===

@task_router.get("/columns/project/{project_id}", response_model=ColumnTemplateListResponse)
async def get_project_columns(
    project_id: int = Path(..., ge=1, description="ID проекта"),
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
) -> ColumnTemplateListResponse:
    """Получить все колонки проекта"""
    
    columns = await task_service.get_project_columns(project_id)
    
    return ColumnTemplateListResponse(
        items=columns,
        total=len(columns)
    )


@task_router.get("/columns/project/{project_id}/with-tasks", response_model=List[ColumnWithTasksResponse])
async def get_project_columns_with_tasks(
    project_id: int = Path(..., ge=1, description="ID проекта"),
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
) -> List[ColumnWithTasksResponse]:
    """Получить колонки проекта с задачами внутри (для канбан-доски)"""
    
    # Получаем колонки
    columns = await task_service.get_project_columns(project_id)
    
    # Получаем задачи проекта
    tasks_result = await task_service.get_tasks_by_project(project_id)
    tasks = tasks_result["items"]
    
    # Группируем задачи по статусам
    tasks_by_status = {}
    for task in tasks:
        status = task.status.value
        if status not in tasks_by_status:
            tasks_by_status[status] = []
        tasks_by_status[status].append(task)
    
    # Собираем результат
    result = []
    for column in columns:
        column_tasks = tasks_by_status.get(column.task_status.value, [])
        result.append(
            ColumnWithTasksResponse(
                **column.__dict__,
                tasks=column_tasks,
                task_count=len(column_tasks)
            )
        )
    
    return result


@task_router.post("/columns/", response_model=ColumnTemplateResponse, status_code=201)
async def create_column(
    column_data: ColumnTemplateCreate,
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> ColumnTemplateResponse:
    """Создать новую колонку (только магистр/преподаватель)"""
    
    try:
        column = await task_service.create_column(column_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create column: {e!s}") from e
    
    return ColumnTemplateResponse.model_validate(column)


@task_router.put("/columns/{column_id}", response_model=ColumnTemplateResponse)
async def update_column(
    column_id: int = Path(..., ge=1, description="ID колонки"),
    column_data: ColumnTemplateUpdate = ...,
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> ColumnTemplateResponse:
    """Обновить колонку (только магистр/преподаватель)"""
    
    try:
        column = await task_service.update_column(column_id, column_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update column: {e!s}") from e
    
    return ColumnTemplateResponse.model_validate(column)


@task_router.delete("/columns/{column_id}")
async def delete_column(
    column_id: int = Path(..., ge=1, description="ID колонки"),
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> dict:
    """Удалить колонку (только магистр/преподаватель)"""
    
    try:
        success = await task_service.delete_column(column_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to delete column: {e!s}") from e
    
    if not success:
        raise HTTPException(status_code=404, detail="Column not found")
    
    return {"message": "Column deleted successfully"}


@task_router.post("/columns/project/{project_id}/reorder", response_model=dict)
async def reorder_columns(
    project_id: int = Path(..., ge=1, description="ID проекта"),
    column_orders: TaskReorder = ...,
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> dict:
    """Изменить порядок колонок (только магистр/преподаватель)"""
    
    try:
        success = await task_service.reorder_columns(
            project_id=project_id,
            column_orders=column_orders.tasks,
            current_user_id=current_user.id
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to reorder columns: {e!s}") from e
    
    return {"message": "Columns reordered successfully", "success": success}


# === Эндпоинты для статистики ===

@task_router.get("/project/{project_id}/stats", response_model=dict)
async def get_project_task_stats(
    project_id: int = Path(..., ge=1, description="ID проекта"),
    task_service: TaskService = Depends(get_task_service),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Получить статистику по задачам проекта"""
    
    tasks = await task_service.get_tasks_by_project(project_id)
    
    # Подсчитываем задачи по статусам
    stats = {
        "total": tasks["total"],
        "by_status": {},
        "by_priority": {},
        "overdue": 0
    }
    
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    
    for task in tasks["items"]:
        # По статусам
        status = task.status.value
        if status not in stats["by_status"]:
            stats["by_status"][status] = 0
        stats["by_status"][status] += 1
        
        # По приоритетам
        priority = task.priority.value
        if priority not in stats["by_priority"]:
            stats["by_priority"][priority] = 0
        stats["by_priority"][priority] += 1
        
        # Просроченные
        if task.due_date and task.due_date < now and task.status != TaskStatus.DONE:
            stats["overdue"] += 1
    
    return stats