from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.container import get_settings_service, get_stage_service, get_workspace_service
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
    WorkspaceParticipantItem,
    WorkspaceParticipantListResponse,
    WorkspaceResumeItem,
    WorkspaceResumeListResponse,
    WorkSpaceUpdate,
)
from src.services.settings_service import SpaceSettingsService
from src.services.stage_service import ProjectStageService
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
        role=current_user.role.name if current_user.role else "member",
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
    stage_service: ProjectStageService = Depends(get_stage_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> WorkSpaceFull:
    """Создать новый workspace"""
    workspace = await workspace_service.create_workspace(workspace_data, current_user.id)
    await settings_service.create_defaults(workspace.id)
    await stage_service.copy_system_types_to_workspace(workspace.id)
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


@workspace_router.get("/{workspace_id}/participants", response_model=WorkspaceParticipantListResponse)
async def get_workspace_participants(
    workspace_id: int,
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество участников на странице"),
    search: str | None = Query(None, description="Поиск по имени/контактам"),
    project_id: int | None = Query(None, description="Фильтр по id проекта"),
    date_from: str | None = Query(None, description="Фильтр от даты (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="Фильтр до даты (YYYY-MM-DD)"),
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    _current_user: User = Depends(get_current_user),
) -> WorkspaceParticipantListResponse:
    """Получить список участников workspace с пагинацией и фильтрацией"""
    workspace = await workspace_service.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    skip = (page - 1) * limit
    items, total = await workspace_service.get_workspace_participants(
        workspace_id,
        skip,
        limit,
        search,
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
    )

    parsed = [WorkspaceParticipantItem.model_validate(item) for item in items]

    return WorkspaceParticipantListResponse(
        items=parsed,
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if limit > 0 else 0,
    )


@workspace_router.get("/{workspace_id}/resumes", response_model=WorkspaceResumeListResponse)
async def get_workspace_resumes(
    workspace_id: int,
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    _current_user: User = Depends(get_current_user),
) -> WorkspaceResumeListResponse:
    """Получить все видимые резюме участников workspace"""
    workspace = await workspace_service.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    items = await workspace_service.get_workspace_resumes(workspace_id)
    parsed = [WorkspaceResumeItem.model_validate(item) for item in items]

    return WorkspaceResumeListResponse(items=parsed, total=len(parsed))


@workspace_router.delete("/{workspace_id}/participants/{user_id}")
async def remove_workspace_participant(
    workspace_id: int,
    user_id: int,
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    _current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Удалить участника из workspace"""
    success = await workspace_service.remove_workspace_participant(workspace_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Participant not found")
    return {"message": "Participant removed successfully"}


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
