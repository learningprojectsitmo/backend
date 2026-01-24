from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.core.container import get_project_service
from src.core.dependencies import get_current_user
from src.model.models import User
from src.schema.project import ProjectCreate, ProjectFull, ProjectListItem, ProjectListResponse, ProjectUpdate
from src.services.project_service import ProjectService
from src.core.audit_context import set_audit_context

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

    return ProjectFull.model_validate(project)


@project_router.get("/", response_model=ProjectListResponse)
async def fetch_projects(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество проектов на странице"),
    project_service: ProjectService = Depends(get_project_service),
    _current_user: User = Depends(get_current_user),
) -> ProjectListResponse:
    """Получить список проектов с пагинацией"""
    projects, total = await project_service.get_projects_paginated(page, limit)
    projects_list = [ProjectListItem.model_validate(project) for project in projects]

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
    request: Request,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> ProjectFull:
    """Создать новый проект"""

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    set_audit_context(
        user_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )

    project = await project_service.create_project(project_data, current_user.id)
    return ProjectFull.model_validate(project)


@project_router.put("/{project_id}", response_model=ProjectFull)
async def update_project(
    project_id: int,
    request: Request,
    project_data: ProjectUpdate = Depends(ProjectUpdate),
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> ProjectFull:
    """Обновить проект (только автор может обновлять)"""

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    set_audit_context(
        user_id=current_user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )

    def _get_project_or_raise_not_found() -> None:
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

    try:
        project = await project_service.update_project(project_id, project_data, current_user.id)
        _get_project_or_raise_not_found()
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update project: {e!s}") from e
    else:
        return ProjectFull.model_validate(project)


@project_router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Удалить проект (только автор может удалять)"""

    def _check_success_or_raise_not_found() -> None:
        if not success:
            raise HTTPException(status_code=404, detail="Project not found")

    try:
        success = await project_service.delete_project(project_id, current_user.id)
        _check_success_or_raise_not_found()
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    else:
        return {"message": "Project deleted successfully"}
