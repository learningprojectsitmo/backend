from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.container import get_kanban_service, get_project_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.user import User
from src.schema.project import ProjectCreate, ProjectFull, ProjectListResponse, ProjectUpdate
from src.services.kanban_service import KanbanService
from src.services.project_service import ProjectService

project_router = APIRouter(prefix="/projects", tags=["project"])


@project_router.get("/{project_id}", response_model=ProjectFull)
async def fetch_project(
    project_id: int,
    project_service: ProjectService = Depends(get_project_service),
    _current_user: User = Depends(get_current_user),
) -> ProjectFull:
    """Получить проект по ID"""
    project = await project_service.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="There is no project with that id!")

    return ProjectFull.from_orm(project)


@project_router.get("/", response_model=ProjectListResponse)
async def fetch_projects(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество проектов на странице"),
    workspace_id: int | None = Query(None, description="ID пространства для фильтрации"),
    project_service: ProjectService = Depends(get_project_service),
    _current_user: User = Depends(get_current_user),
) -> ProjectListResponse:
    """Получить список проектов с пагинацией"""

    if workspace_id is not None:
        projects, total = await project_service.get_projects_by_workspace(workspace_id, page, limit)
    else:
        projects, total = await project_service.get_projects_paginated(page, limit)

    projects_list = [project_service.to_project_list_item(project) for project in projects]

    total_pages = (total + limit - 1) // limit if total > 0 else 0

    return ProjectListResponse(
        items=projects_list,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@project_router.post("/", response_model=ProjectFull)
async def create_project(
    project_data: ProjectCreate,
    project_service: ProjectService = Depends(get_project_service),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> ProjectFull:
    """Создать новый проект"""

    project = await project_service.create_project(project_data, current_user.id)
    await kanban_service.create_default_columns(project.id)
    return ProjectFull.from_orm(project)


@project_router.put("/{project_id}", response_model=ProjectFull)
async def update_project(
    project_id: int,
    project_data: ProjectUpdate,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> ProjectFull:
    """Обновить проект (только автор может обновлять)"""

    project = await project_service.update_project(project_id, project_data, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectFull.from_orm(project)


@project_router.delete("/{project_id}/participants/{user_id}")
async def remove_participant(
    project_id: int,
    user_id: int,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> dict[str, str]:
    """Удалить участника из проекта (только автор)"""
    success = await project_service.remove_participant(project_id, user_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Participant not found")
    return {"message": "Participant removed successfully"}


@project_router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Удалить проект (только автор может удалять)"""

    success = await project_service.delete_project(project_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")

    return {"message": "Project deleted successfully"}
