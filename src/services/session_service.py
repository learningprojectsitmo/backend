from __future__ import annotations

from datetime import datetime

from src.core.exceptions import NotFoundError
from src.core.logging_config import get_logger
from src.repository.session_repository import SessionRepository
from src.schema.session import (
    CurrentSessionInfo,
    SessionBase,
    SessionCreate,
    SessionListResponse,
    SessionResponse,
    SessionStats,
    SessionTerminateRequest,
    SessionTerminateResponse,
    SessionUpdate,
)


class SessionService:
    """Сервис для управления сессиями пользователей"""

    def __init__(self, session_repository: SessionRepository) -> None:
        self._repository = session_repository
        self._logger = get_logger(self.__class__.__name__)

    async def create_session(self, session_data: SessionCreate) -> SessionResponse:
        """Создать новую сессию"""
        self._logger.info(f"Creating session for user {session_data.user_id}")

        try:
            session = await self._repository.create(session_data)
            return SessionResponse.model_validate(session)
        except Exception:
            self._logger.exception(f"Error creating session for user {session_data.user_id}")
            raise

    async def get_user_sessions(self, user_id: int) -> SessionListResponse:
        """Получить список сессий пользователя"""
        self._logger.info(f"Getting sessions for user {user_id}")

        try:
            sessions = await self._repository.get_active_sessions_by_user_id(user_id)
            current_session = await self._repository.get_current_session(user_id)

            session_responses = [SessionResponse.model_validate(session) for session in sessions]

            return SessionListResponse(
                sessions=session_responses,
                total=len(session_responses),
                current_session_id=current_session.id if current_session else None,
            )
        except Exception:
            self._logger.exception(f"Error getting sessions for user {user_id}")
            raise

    async def get_session_by_id(self, session_id: str) -> SessionResponse:
        """Получить сессию по ID"""
        self._logger.debug(f"Getting session {session_id}")

        try:
            session = await self._repository.get_by_id(session_id)
            if not session:
                raise NotFoundError(f"Session with id {session_id} not found")
            return SessionResponse.model_validate(session)
        except NotFoundError:
            raise
        except Exception:
            self._logger.exception(f"Error getting session {session_id}")
            raise

    async def update_session(self, session_id: str, session_data: SessionUpdate) -> SessionResponse:
        """Обновить сессию"""
        self._logger.info(f"Updating session {session_id}")

        try:
            session = await self._repository.update(session_id, session_data)
            if not session:
                raise NotFoundError(f"Session with id {session_id} not found")
            return SessionResponse.model_validate(session)
        except NotFoundError:
            raise
        except Exception:
            self._logger.exception(f"Error updating session {session_id}")
            raise

    async def update_session_activity(self, session_id: str) -> SessionResponse:
        """Обновить время последней активности сессии"""
        self._logger.debug(f"Updating activity for session {session_id}")

        try:
            session = await self._repository.update_last_activity(session_id)
            if not session:
                raise NotFoundError(f"Session with id {session_id} not found")
            return SessionResponse.model_validate(session)
        except NotFoundError:
            raise
        except Exception:
            self._logger.exception(f"Error updating session activity {session_id}")
            raise

    async def set_current_session(self, user_id: int, session_id: str) -> bool:
        """Установить сессию как текущую для пользователя"""
        self._logger.info(f"Setting session {session_id} as current for user {user_id}")

        try:
            return await self._repository.set_current_session(user_id, session_id)
        except Exception:
            self._logger.exception(f"Error setting current session for user {user_id}")
            raise

    async def terminate_session(self, session_id: str) -> bool:
        """Завершить сессию"""
        self._logger.info(f"Terminating session {session_id}")

        try:
            return await self._repository.terminate_session(session_id)
        except Exception:
            self._logger.exception(f"Error terminating session {session_id}")
            raise

    async def terminate_sessions(self, request: SessionTerminateRequest) -> SessionTerminateResponse:
        """Завершить сессии согласно запросу"""
        self._logger.info(f"Terminating sessions: {len(request.session_ids)} specified")

        try:
            if request.terminate_all_except_current:
                # Если нужно завершить все сессии кроме текущей
                current_session = None
                # Получаем текущую сессию пользователя из первой сессии в списке (если есть)
                if request.session_ids:
                    first_session = await self._repository.get_by_id(request.session_ids[0])
                    if first_session:
                        current_session = await self._repository.get_current_session(first_session.user_id)

                        if current_session:
                            terminated_count = await self._repository.terminate_all_sessions_except(
                                first_session.user_id, current_session.id
                            )
                            return SessionTerminateResponse(
                                terminated_sessions=[
                                    current_session.id
                                ],  # Возвращаем текущую сессию как "не завершенную"
                                message=f"Завершено {terminated_count} сессий кроме текущей",
                            )
                # Если не удалось найти текущую сессию, завершаем все указанные
                terminated_sessions = await self._repository.terminate_sessions(request.session_ids)
            else:
                # Завершаем только указанные сессии
                terminated_sessions = await self._repository.terminate_sessions(request.session_ids)

            return SessionTerminateResponse(
                terminated_sessions=terminated_sessions, message=f"Завершено {len(terminated_sessions)} сессий"
            )
        except Exception:
            self._logger.exception("Error terminating sessions")
            raise

    async def get_session_stats(self, user_id: int) -> SessionStats:
        """Получить статистику сессий пользователя"""
        self._logger.debug(f"Getting session stats for user {user_id}")

        try:
            total_sessions = await self._repository.count_user_sessions(user_id)
            active_sessions = await self._repository.count_active_user_sessions(user_id)
            current_session = await self._repository.get_current_session(user_id)

            current_session_info = None
            if current_session:
                current_session_info = CurrentSessionInfo(
                    session_id=current_session.id,
                    device_info=SessionBase(
                        device_name=current_session.device_name,
                        browser_name=current_session.browser_name,
                        browser_version=current_session.browser_version,
                        operating_system=current_session.operating_system,
                        device_type=current_session.device_type,
                        ip_address=current_session.ip_address,
                        country=current_session.country,
                        city=current_session.city,
                        user_agent=current_session.user_agent,
                        fingerprint=current_session.fingerprint,
                    ),
                    created_at=current_session.created_at,
                    last_activity=current_session.last_activity,
                    expires_at=current_session.expires_at,
                )

            return SessionStats(
                total_sessions=total_sessions, active_sessions=active_sessions, current_session=current_session_info
            )
        except Exception:
            self._logger.exception(f"Error getting session stats for user {user_id}")
            raise

    async def cleanup_expired_sessions(self) -> int:
        """Очистить истекшие сессии"""
        self._logger.info("Cleaning up expired sessions")

        try:
            return await self._repository.cleanup_expired_sessions()
        except Exception:
            self._logger.exception("Error cleaning up expired sessions")
            raise

    async def validate_session(self, session_id: str, user_id: int) -> bool:
        """Проверить валидность сессии"""
        self._logger.debug(f"Validating session {session_id} for user {user_id}")

        try:
            session = await self._repository.get_by_id(session_id)
            if not session:
                return False

            # Проверяем, что сессия принадлежит пользователю и активна
            if session.user_id != user_id or not session.is_active:
                return False

            # Проверяем, не истекла ли сессия
            if session.expires_at and session.expires_at < datetime.utcnow():
                # Автоматически завершаем истекшую сессию
                await self._repository.terminate_session(session_id)
                return False

            # Обновляем время последней активности
            await self._repository.update_last_activity(session_id)
            return True
        except Exception:
            self._logger.exception(f"Error validating session {session_id}")
            return False

    async def get_sessions_summary(self, user_id: int) -> dict:
        """Получить краткую информацию о сессиях пользователя"""
        self._logger.debug(f"Getting sessions summary for user {user_id}")

        try:
            sessions = await self._repository.get_active_sessions_by_user_id(user_id)
            current_session = await self._repository.get_current_session(user_id)

            summary = {
                "total_active": len(sessions),
                "current_session_id": current_session.id if current_session else None,
                "sessions": [],
            }

            for session in sessions:
                session_info = {
                    "id": session.id,
                    "device_name": session.device_name or "Unknown Device",
                    "browser_name": session.browser_name or "Unknown Browser",
                    "operating_system": session.operating_system or "Unknown OS",
                    "is_current": session.is_current,
                    "last_activity": session.last_activity.isoformat(),
                    "location": f"{session.city}, {session.country}"
                    if session.city and session.country
                    else "Unknown Location",
                }
                summary["sessions"].append(session_info)

            return summary
        except Exception:
            self._logger.exception(f"Error getting sessions summary for user {user_id}")
            raise
