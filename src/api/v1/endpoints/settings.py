from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.core.container import get_app_setting_service, get_settings_service, get_workspace_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.user import User
from src.schema.settings import SpaceSettingsFull, SpaceSettingsUpdate
from src.services.app_setting_service import AppSettingService
from src.services.settings_service import SpaceSettingsService
from src.services.workspace_service import WorkSpaceService

settings_router = APIRouter(tags=["settings"])


@settings_router.get("/settings/public", response_model=dict[str, Any])
async def get_public_app_settings(
    app_setting_service: AppSettingService = Depends(get_app_setting_service),
) -> dict[str, Any]:
    """Публичная выборка глобальных настроек инстанса.

    Аутентификация не требуется намеренно: настройки отсюда читает в том числе
    анонимный посетитель (декорация рисуется на лендинге и до входа). Поэтому
    состав ключей ограничен тем, что в реестре помечено как public, — серверные
    параметры в этот ответ попасть не могут.
    """
    return await app_setting_service.get_public_values()


@settings_router.get("/workspaces/{workspace_id}/settings", response_model=SpaceSettingsFull)
async def get_space_settings(
    workspace_id: int,
    settings_service: SpaceSettingsService = Depends(get_settings_service),
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    current_user: User = Depends(get_current_user),
) -> SpaceSettingsFull:
    """Получить настройки пространства (только автор)"""
    workspace = await workspace_service.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only workspace author can view settings")

    settings = await settings_service.get_by_space_id(workspace_id)
    if not settings:
        settings = await settings_service.create_defaults(workspace_id)

    return SpaceSettingsFull.model_validate(settings)


@settings_router.put("/workspaces/{workspace_id}/settings", response_model=SpaceSettingsFull)
async def update_space_settings(
    workspace_id: int,
    settings_data: SpaceSettingsUpdate,
    settings_service: SpaceSettingsService = Depends(get_settings_service),
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> SpaceSettingsFull:
    """Обновить настройки пространства (только автор)"""
    workspace = await workspace_service.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only workspace author can update settings")

    settings = await settings_service.create_or_update(workspace_id, settings_data)
    return SpaceSettingsFull.model_validate(settings)
