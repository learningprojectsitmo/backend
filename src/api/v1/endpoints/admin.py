from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.core.container import get_admin_service, get_session_service
from src.core.dependencies import admin_required
from src.model.user import User
from src.schema.admin import AdminAuditListResponse, AdminOverview, AdminSessionsResponse, AdminSessionStats
from src.schema.session import SessionTerminateRequest, SessionTerminateResponse
from src.services.admin_service import AdminService
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
