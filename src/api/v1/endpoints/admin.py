from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.app_settings_registry import InvalidSettingValueError, UnknownSettingError
from src.core.container import (
    get_admin_service,
    get_app_setting_service,
    get_fixtures_service,
    get_session_service,
)
from src.core.dependencies import admin_required, setup_audit
from src.model.user import User
from src.schema.admin import (
    AdminAuditListResponse,
    AdminFixtureUserInfo,
    AdminFixtureUsersResponse,
    AdminOverview,
    AdminSessionsResponse,
    AdminSessionStats,
)
from src.schema.app_setting import AppSettingPatch, AppSettingsAdminResponse
from src.schema.session import SessionTerminateRequest, SessionTerminateResponse
from src.services.admin_service import AdminService
from src.services.app_setting_service import AppSettingService
from src.services.fixtures_service import FIXTURE_USERS, FixtureService
from src.services.session_service import SessionService

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/overview", response_model=AdminOverview)
async def get_admin_overview(
    admin_service: AdminService = Depends(get_admin_service),
    _current_user: User = Depends(admin_required),
) -> AdminOverview:
    """Обзорная статистика системы для админ-панели"""
    return await admin_service.get_overview()


@admin_router.get("/sessions", response_model=AdminSessionsResponse)
async def get_admin_sessions(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(20, ge=1, le=100, description="Количество сессий на странице"),
    only_active: bool = Query(False, description="Показывать только активные сессии"),
    admin_service: AdminService = Depends(get_admin_service),
    _current_user: User = Depends(admin_required),
) -> AdminSessionsResponse:
    """Список сессий всех пользователей"""
    return await admin_service.get_all_sessions(page=page, limit=limit, only_active=only_active)


@admin_router.get("/sessions/stats", response_model=AdminSessionStats)
async def get_admin_session_stats(
    admin_service: AdminService = Depends(get_admin_service),
    _current_user: User = Depends(admin_required),
) -> AdminSessionStats:
    """Статистика сессий по всей системе"""
    return await admin_service.get_session_stats()


@admin_router.post("/sessions/terminate", response_model=SessionTerminateResponse)
async def terminate_admin_sessions(
    terminate_request: SessionTerminateRequest,
    session_service: SessionService = Depends(get_session_service),
    _current_user: User = Depends(admin_required),
) -> SessionTerminateResponse:
    """Завершить произвольные сессии (административная функция)"""
    return await session_service.terminate_sessions(terminate_request)


@admin_router.get("/audit", response_model=AdminAuditListResponse)
async def get_admin_audit_logs(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(20, ge=1, le=100, description="Количество записей на странице"),
    admin_service: AdminService = Depends(get_admin_service),
    _current_user: User = Depends(admin_required),
) -> AdminAuditListResponse:
    """Audit логи всех пользователей"""
    return await admin_service.get_all_audit_logs(page=page, limit=limit)


@admin_router.post("/fixtures/users", response_model=AdminFixtureUsersResponse)
async def create_fixture_users(
    fixtures_service: FixtureService = Depends(get_fixtures_service),
    _current_user: User = Depends(admin_required),
) -> AdminFixtureUsersResponse:
    """Создать фикстурных (демо) пользователей по ролям

    Идемпотентно: повторный вызов не создаёт дубликаты.
    """
    created_users, already_existed = await fixtures_service.create_fixture_users()
    role_lookup = {ud["email"]: ud["role_name"] for ud in FIXTURE_USERS}

    created_items = [
        AdminFixtureUserInfo(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role_name=role_lookup.get(user.email, ""),
        )
        for user in created_users
    ]

    return AdminFixtureUsersResponse(created=created_items, already_existed=already_existed)


@admin_router.get("/settings", response_model=AppSettingsAdminResponse)
async def get_admin_app_settings(
    app_setting_service: AppSettingService = Depends(get_app_setting_service),
    _current_user: User = Depends(admin_required),
) -> AppSettingsAdminResponse:
    """Все глобальные настройки инстанса с текущими значениями"""
    return AppSettingsAdminResponse(items=await app_setting_service.list_items())


@admin_router.patch("/settings", response_model=AppSettingsAdminResponse)
async def patch_admin_app_settings(
    patch: AppSettingPatch,
    app_setting_service: AppSettingService = Depends(get_app_setting_service),
    current_user: User = Depends(admin_required),
    _audit=Depends(setup_audit),
) -> AppSettingsAdminResponse:
    """Частично обновить глобальные настройки инстанса

    Ключи и типы проверяются по реестру: неизвестный ключ или значение не того
    типа отклоняются с 422, а не молча кладутся в таблицу.
    """
    try:
        items = await app_setting_service.apply_patch(patch.model_dump(), user_id=current_user.id)
    except (UnknownSettingError, InvalidSettingValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return AppSettingsAdminResponse(items=items)
