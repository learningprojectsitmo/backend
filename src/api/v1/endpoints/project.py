import math

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.container import Container
from src.core.dependencies import get_current_user
from src.core.middleware import inject
from src.model.models import User
from src.schemas import *
from src.services.project_service import ProjectService

project_router = APIRouter(prefix="/projects", tags=['project'])


@project_router.get("/{project_id}", response_model=ProjectFull)
@inject
async def fetch_project(
    project_id: int,
    project_service: ProjectService = Depends(Provide[Container.project_service]),
    current_user: User = Depends(get_current_user)
):
    """Получить проект по ID"""
    project = project_service.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="There is no project with that id!")

    return ProjectFull.model_validate(project)


@project_router.patch("/{project_id}", response_model=ProjectFull)
@inject
async def update_project(
    project_id: int,
    project_data: ProjectUpdate,
    project_service: ProjectService = Depends(Provide[Container.project_service]),
    current_user: User = Depends(get_current_user)
):
    """Обновить проект (только автор может обновлять)"""
    try:
        project = project_service.update_project(project_id, project_data, current_user.id)
        if not project:
            raise HTTPException(status_code=404, detail="There is no project with that id!")

        return ProjectFull.model_validate(project)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@project_router.delete("/{project_id}", response_model=DeleteResponse)
@inject
async def delete_project(
    project_id: int,
    project_service: ProjectService = Depends(Provide[Container.project_service]),
    current_user: User = Depends(get_current_user)
):
    """Удалить проект (только автор может удалять)"""
    try:
        success = project_service.delete_project(project_id, current_user.id)
        if not success:
            raise HTTPException(status_code=404, detail="There is no project with that id!")

        return {"message": "Project Deleted"}
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@project_router.post("/", response_model=ProjectResponse, status_code=201)
@inject
async def create_project(
    project_data: ProjectCreate,
    project_service: ProjectService = Depends(Provide[Container.project_service]),
    current_user: User = Depends(get_current_user)
):
    """Создать новый проект"""
    project = project_service.create_project(project_data, current_user.id)
    return ProjectResponse.model_validate(project)


@project_router.get("/", response_model=ProjectListResponse)
@inject
async def fetch_projects(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество проектов на странице"),
    project_service: ProjectService = Depends(Provide[Container.project_service]),
    current_user: User = Depends(get_current_user)
):
    """Получить список проектов с пагинацией"""
    projects, total = project_service.get_projects_paginated(page, limit)
    projects_list = [ProjectListItem.model_validate(project) for project in projects]

    total_pages = math.ceil(total / limit) if total > 0 else 0

    return ProjectListResponse(
        items=projects_list,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages
    )
