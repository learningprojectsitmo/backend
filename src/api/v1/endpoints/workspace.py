from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.container import get_settings_service, get_workspace_service
from src.core.dependencies import get_current_user, setup_audit
from src.core.exceptions import PermissionError
from src.model.user import User
from src.schema.workspace import (
    Category as SpaceCategory,
)
from src.schema.workspace import (
    Space,
    SpacesListResponse,
    WorkSpaceCreate,
    WorkSpaceFull,
    WorkSpaceUpdate,
)
from src.services.settings_service import SpaceSettingsService
from src.services.workspace_service import WorkSpaceService

workspace_router = APIRouter(prefix="/workspaces", tags=["workspace"])


@workspace_router.get("/menu", response_model=SpacesListResponse)
async def get_workspace_menu(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество workspace на странице"),
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    current_user: User = Depends(get_current_user),
) -> SpacesListResponse:
    """Получить меню workspace (только видимые пользователю)"""
    skip = (page - 1) * limit
    spaces_data, total = await workspace_service.get_workspaces_menu_data(current_user.id, skip, limit)

    # Получаем реальные категории из БД
    categories = await workspace_service.get_all_categories()

    # Формируем список категорий для ответа
    categories_response = [SpaceCategory(id=cat.id, name=cat.name, color=cat.color or "#6366f1") for cat in categories]

    spaces = [Space.model_validate(item) for item in spaces_data]

    return SpacesListResponse(
        categories=categories_response,
        spaces=spaces,
        page=page,
        limit=limit,
        total=total,
    )


@workspace_router.get("/{workspace_id}", response_model=WorkSpaceFull)
async def fetch_workspace(
    workspace_id: int,
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    _current_user: User = Depends(get_current_user),
) -> WorkSpaceFull:
    """Получить workspace по ID"""
    workspace = await workspace_service.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="There is no workspace with that id!")

    return WorkSpaceFull.model_validate(workspace)


@workspace_router.get("/", response_model=list[WorkSpaceFull])
async def fetch_workspaces(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество workspace на странице"),
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    _current_user: User = Depends(get_current_user),
) -> list[WorkSpaceFull]:
    """Получить список workspace с пагинацией"""
    workspaces, _ = await workspace_service.get_workspaces_paginated(page, limit)
    return [WorkSpaceFull.model_validate(workspace) for workspace in workspaces]


@workspace_router.post("/", response_model=WorkSpaceFull)
async def create_workspace(
    workspace_data: WorkSpaceCreate,
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    settings_service: SpaceSettingsService = Depends(get_settings_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> WorkSpaceFull:
    """Создать новый workspace"""
    workspace = await workspace_service.create_workspace(workspace_data, current_user.id)
    await settings_service.create_defaults(workspace.id)
    return WorkSpaceFull.model_validate(workspace)


@workspace_router.put("/{workspace_id}", response_model=WorkSpaceFull)
async def update_workspace(
    workspace_id: int,
    workspace_data: WorkSpaceUpdate,
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> WorkSpaceFull:
    """Обновить workspace (только автор может обновлять)"""

    def _get_workspace_or_raise_not_found() -> None:
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

    try:
        workspace = await workspace_service.update_workspace(workspace_id, workspace_data, current_user.id)
        _get_workspace_or_raise_not_found()
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update workspace: {e!s}") from e
    else:
        return WorkSpaceFull.model_validate(workspace)


@workspace_router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: int,
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Удалить workspace (только автор может удалять)"""

    def _check_success_or_raise_not_found() -> None:
        if not success:
            raise HTTPException(status_code=404, detail="Workspace not found")

    try:
        success = await workspace_service.delete_workspace(workspace_id, current_user.id)
        _check_success_or_raise_not_found()
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    else:
        return {"message": "Workspace deleted successfully"}
