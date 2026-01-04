from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from src.core.container import get_session_service
from src.core.dependencies import get_current_user
from src.core.logging_config import api_logger
from src.model.models import User
from src.schema.session import (
    SessionListResponse,
    SessionResponse,
    SessionStats,
    SessionTerminateRequest,
    SessionTerminateResponse,
    SessionUpdate,
)
from src.services.session_service import SessionService

sessions_router = APIRouter(prefix="/sessions", tags=["sessions"])


@sessions_router.get("", response_model=SessionListResponse)
async def get_user_sessions(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session_service: SessionService = Depends(get_session_service),
) -> SessionListResponse:
    """Получить список сессий пользователя"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    try:
        result = await session_service.get_user_sessions(current_user.id)

        api_logger.log_request(
            method="GET",
            path="/sessions",
            user_id=current_user.id,
            ip_address=client_ip,
            status_code=200,
            response_time=0.0,
            user_agent=user_agent,
        )

        return result
    except Exception as e:
        api_logger.log_error(method="GET", path="/sessions", error=e, user_id=current_user.id)
        raise


@sessions_router.get("/stats", response_model=SessionStats)
async def get_session_stats(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session_service: SessionService = Depends(get_session_service),
) -> SessionStats:
    """Получить статистику сессий пользователя"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    try:
        result = await session_service.get_session_stats(current_user.id)

        api_logger.log_request(
            method="GET",
            path="/sessions/stats",
            user_id=current_user.id,
            ip_address=client_ip,
            status_code=200,
            response_time=0.0,
            user_agent=user_agent,
        )

        return result
    except Exception as e:
        api_logger.log_error(method="GET", path="/sessions/stats", error=e, user_id=current_user.id)
        raise


@sessions_router.get("/summary")
async def get_sessions_summary(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session_service: SessionService = Depends(get_session_service),
) -> dict[str, object]:
    """Получить краткую информацию о сессиях пользователя"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    try:
        result = await session_service.get_sessions_summary(current_user.id)

        api_logger.log_request(
            method="GET",
            path="/sessions/summary",
            user_id=current_user.id,
            ip_address=client_ip,
            status_code=200,
            response_time=0.0,
            user_agent=user_agent,
        )

        return result
    except Exception as e:
        api_logger.log_error(method="GET", path="/sessions/summary", error=e, user_id=current_user.id)
        raise


@sessions_router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    request: Request,
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session_service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    """Получить информацию о конкретной сессии"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    try:
        result = await session_service.get_session_by_id(session_id)

        # Проверяем, что сессия принадлежит пользователю
        if result.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Session not found")

        api_logger.log_request(
            method="GET",
            path=f"/sessions/{session_id}",
            user_id=current_user.id,
            ip_address=client_ip,
            status_code=200,
            response_time=0.0,
            user_agent=user_agent,
        )

        return result
    except Exception as e:
        api_logger.log_error(method="GET", path=f"/sessions/{session_id}", error=e, user_id=current_user.id)
        raise


@sessions_router.put("/{session_id}", response_model=SessionResponse)
async def update_session(
    request: Request,
    session_id: str,
    session_data: SessionUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session_service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    """Обновить информацию о сессии"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    try:
        # Сначала проверяем, что сессия принадлежит пользователю
        existing_session = await session_service.get_session_by_id(session_id)
        if existing_session.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Session not found")

        result = await session_service.update_session(session_id, session_data)

        api_logger.log_request(
            method="PUT",
            path=f"/sessions/{session_id}",
            user_id=current_user.id,
            ip_address=client_ip,
            status_code=200,
            response_time=0.0,
            user_agent=user_agent,
        )

        return result
    except Exception as e:
        api_logger.log_error(method="PUT", path=f"/sessions/{session_id}", error=e, user_id=current_user.id)
        raise


@sessions_router.post("/terminate", response_model=SessionTerminateResponse)
async def terminate_sessions(
    request: Request,
    terminate_request: SessionTerminateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session_service: SessionService = Depends(get_session_service),
) -> SessionTerminateResponse:
    """Завершить сессии"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    try:
        result = await session_service.terminate_sessions(terminate_request)

        api_logger.log_request(
            method="POST",
            path="/sessions/terminate",
            user_id=current_user.id,
            ip_address=client_ip,
            status_code=200,
            response_time=0.0,
            user_agent=user_agent,
        )

        return result
    except Exception as e:
        api_logger.log_error(method="POST", path="/sessions/terminate", error=e, user_id=current_user.id)
        raise


@sessions_router.post("/set-current/{session_id}")
async def set_current_session(
    request: Request,
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session_service: SessionService = Depends(get_session_service),
) -> dict[str, str]:
    """Установить сессию как текущую"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    try:
        # Сначала проверяем, что сессия принадлежит пользователю
        existing_session = await session_service.get_session_by_id(session_id)
        if existing_session.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Session not found")

        success = await session_service.set_current_session(current_user.id, session_id)

        if not success:
            raise HTTPException(status_code=400, detail="Failed to set current session")

        api_logger.log_request(
            method="POST",
            path=f"/sessions/set-current/{session_id}",
            user_id=current_user.id,
            ip_address=client_ip,
            status_code=200,
            response_time=0.0,
            user_agent=user_agent,
        )

        return {"message": "Current session updated successfully"}
    except Exception as e:
        api_logger.log_error(
            method="POST", path=f"/sessions/set-current/{session_id}", error=e, user_id=current_user.id
        )
        raise


@sessions_router.post("/validate/{session_id}")
async def validate_session(
    request: Request,
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session_service: SessionService = Depends(get_session_service),
) -> dict[str, bool]:
    """Проверить валидность сессии"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    try:
        is_valid = await session_service.validate_session(session_id, current_user.id)

        api_logger.log_request(
            method="POST",
            path=f"/sessions/validate/{session_id}",
            user_id=current_user.id,
            ip_address=client_ip,
            status_code=200,
            response_time=0.0,
            user_agent=user_agent,
        )

        return {"is_valid": is_valid}
    except Exception as e:
        api_logger.log_error(method="POST", path=f"/sessions/validate/{session_id}", error=e, user_id=current_user.id)
        raise


@sessions_router.post("/cleanup")
async def cleanup_expired_sessions(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session_service: SessionService = Depends(get_session_service),
) -> dict[str, int]:
    """Очистить истекшие сессии (административная функция)"""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")

    try:
        # В реальном приложении здесь должна быть проверка прав администратора
        cleaned_count = await session_service.cleanup_expired_sessions()

        api_logger.log_request(
            method="POST",
            path="/sessions/cleanup",
            user_id=current_user.id,
            ip_address=client_ip,
            status_code=200,
            response_time=0.0,
            user_agent=user_agent,
        )

        return {"cleaned_sessions": cleaned_count}
    except Exception as e:
        api_logger.log_error(method="POST", path="/sessions/cleanup", error=e, user_id=current_user.id)
        raise
