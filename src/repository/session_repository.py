from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select

from src.core.logging_config import get_logger
from src.core.uow import IUnitOfWork
from src.model.models import Session
from src.schema.session import SessionCreate, SessionUpdate


class SessionRepository:
    """Репозиторий для работы с сессиями пользователей"""

    def __init__(self, uow: IUnitOfWork) -> None:
        self.uow = uow
        self._logger = get_logger(self.__class__.__name__)

    async def get_by_id(self, session_id: str) -> Session | None:
        """Получить сессию по ID"""
        self._logger.debug(f"Getting session by ID: {session_id}")

        try:
            result = await self.uow.session.get(Session, session_id)
        except Exception:
            self._logger.exception(f"Error getting session {session_id}")
            raise
        else:
            if result:
                self._logger.info(f"Retrieved session {session_id}")
            else:
                self._logger.warning(f"Session {session_id} not found")
            return result

    async def get_by_user_id(self, user_id: int) -> Sequence[Session]:
        """Получить все сессии пользователя"""
        self._logger.debug(f"Getting sessions for user {user_id}")

        try:
            result = await self.uow.session.execute(
                select(Session).where(Session.user_id == user_id).order_by(Session.last_activity.desc())
            )
            sessions = result.scalars().all()
        except Exception:
            self._logger.exception(f"Error getting sessions for user {user_id}")
            raise
        else:
            self._logger.info(f"Retrieved {len(sessions)} sessions for user {user_id}")
            return sessions

    async def get_active_sessions_by_user_id(self, user_id: int) -> Sequence[Session]:
        """Получить активные сессии пользователя"""
        self._logger.debug(f"Getting active sessions for user {user_id}")

        try:
            result = await self.uow.session.execute(
                select(Session)
                .where(and_(Session.user_id == user_id, Session.is_active))
                .order_by(Session.last_activity.desc())
            )
            sessions = result.scalars().all()
        except Exception:
            self._logger.exception(f"Error getting active sessions for user {user_id}")
            raise
        else:
            self._logger.info(f"Retrieved {len(sessions)} active sessions for user {user_id}")
            return sessions

    async def get_current_session(self, user_id: int) -> Session | None:
        """Получить текущую сессию пользователя"""
        self._logger.debug(f"Getting current session for user {user_id}")

        try:
            result = await self.uow.session.execute(
                select(Session).where(and_(Session.user_id == user_id, Session.is_current, Session.is_active))
            )
            session = result.scalar_one_or_none()
        except Exception:
            self._logger.exception(f"Error getting current session for user {user_id}")
            raise
        else:
            if session:
                self._logger.info(f"Found current session for user {user_id}: {session.id}")
            else:
                self._logger.warning(f"No current session found for user {user_id}")
            return session

    async def create(self, session_data: SessionCreate) -> Session:
        """Создать новую сессию"""
        self._logger.debug(f"Creating session for user {session_data.user_id}")

        try:
            # Генерируем уникальный ID для сессии
            session_id = str(uuid.uuid4())

            # Создаем объект сессии
            session_dict = session_data.model_dump(exclude_unset=True)
            session_dict["id"] = session_id

            # Если не указано время истечения, устанавливаем на 30 дней
            if not session_dict.get("expires_at"):
                session_dict["expires_at"] = datetime.utcnow() + timedelta(days=30)

            db_session = Session(**session_dict)
            self.uow.session.add(db_session)
            await self.uow.session.flush()
        except Exception:
            self._logger.exception(f"Error creating session for user {session_data.user_id}")
            raise
        else:
            self._logger.info(f"Created session {session_id} for user {session_data.user_id}")
            return db_session

    async def update(self, session_id: str, session_data: SessionUpdate) -> Session | None:
        """Обновить сессию"""
        self._logger.debug(f"Updating session {session_id}")

        def _check_session_exists() -> None:
            if not db_session:
                self._logger.warning(f"Session {session_id} not found for update")

        try:
            db_session = await self.get_by_id(session_id)
            _check_session_exists()
        except Exception:
            self._logger.exception(f"Error updating session {session_id}")
            raise
        else:
            update_data = session_data.model_dump(exclude_unset=True)
            updated_fields = list(update_data.keys())

            for field, value in update_data.items():
                setattr(db_session, field, value)

            self._logger.info(f"Updated session {session_id} - fields: {updated_fields}")
            return db_session

    async def update_last_activity(self, session_id: str) -> Session | None:
        """Обновить время последней активности сессии"""
        self._logger.debug(f"Updating last activity for session {session_id}")

        def _check_session_exists() -> None:
            if not db_session:
                self._logger.warning(f"Session {session_id} not found for activity update")

        try:
            db_session = await self.get_by_id(session_id)
            _check_session_exists()
        except Exception:
            self._logger.exception(f"Error updating last activity for session {session_id}")
            raise
        else:
            db_session.last_activity = datetime.utcnow()
            self._logger.debug(f"Updated last activity for session {session_id}")
            return db_session

    async def set_current_session(self, user_id: int, session_id: str) -> bool:
        """Установить сессию как текущую для пользователя"""
        self._logger.debug(f"Setting session {session_id} as current for user {user_id}")

        try:
            # Сначала сбрасываем флаг is_current для всех сессий пользователя
            await self.uow.session.execute(select(Session).where(Session.user_id == user_id))
            sessions = await self.get_by_user_id(user_id)

            for session in sessions:
                session.is_current = False

            # Устанавливаем текущую сессию
            current_session = await self.get_by_id(session_id)
            if current_session and current_session.user_id == user_id:
                current_session.is_current = True
                current_session.last_activity = datetime.utcnow()
                self._logger.info(f"Set session {session_id} as current for user {user_id}")
                return True
            else:
                self._logger.warning(f"Session {session_id} not found or doesn't belong to user {user_id}")
                return False
        except Exception:
            self._logger.exception(f"Error setting current session for user {user_id}")
            raise

    async def terminate_session(self, session_id: str) -> bool:
        """Завершить сессию"""
        self._logger.debug(f"Terminating session {session_id}")

        try:
            db_session = await self.get_by_id(session_id)
        except Exception:
            self._logger.exception(f"Error terminating session {session_id}")
            raise
        else:
            if not db_session:
                self._logger.warning(f"Session {session_id} not found for termination")
                return False

            db_session.is_active = False
            db_session.is_current = False
            self._logger.info(f"Terminated session {session_id}")
            return True

    async def terminate_sessions(self, session_ids: list[str]) -> list[str]:
        """Завершить несколько сессий"""
        self._logger.debug(f"Terminating {len(session_ids)} sessions")

        terminated_sessions = []
        try:
            for session_id in session_ids:
                if await self.terminate_session(session_id):
                    terminated_sessions.append(session_id)
        except Exception:
            self._logger.exception("Error terminating sessions")
            raise
        else:
            self._logger.info(f"Terminated {len(terminated_sessions)} sessions")
            return terminated_sessions

    async def terminate_all_sessions_except(self, user_id: int, except_session_id: str) -> int:
        """Завершить все сессии пользователя кроме указанной"""
        self._logger.debug(f"Terminating all sessions for user {user_id} except {except_session_id}")

        try:
            result = await self.uow.session.execute(
                select(Session).where(
                    and_(Session.user_id == user_id, Session.id != except_session_id, Session.is_active)
                )
            )
            sessions_to_terminate = result.scalars().all()

            terminated_count = 0
            for session in sessions_to_terminate:
                session.is_active = False
                session.is_current = False
                terminated_count += 1
        except Exception:
            self._logger.exception(f"Error terminating sessions for user {user_id}")
            raise
        else:
            self._logger.info(f"Terminated {terminated_count} sessions for user {user_id}")
            return terminated_count

    async def cleanup_expired_sessions(self) -> int:
        """Очистить истекшие сессии"""
        self._logger.debug("Cleaning up expired sessions")

        try:
            result = await self.uow.session.execute(
                select(Session).where(and_(Session.expires_at < datetime.utcnow(), Session.is_active))
            )
            expired_sessions = result.scalars().all()

            for session in expired_sessions:
                session.is_active = False
                session.is_current = False
        except Exception:
            self._logger.exception("Error cleaning up expired sessions")
            raise
        else:
            self._logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
            return len(expired_sessions)

    async def count_user_sessions(self, user_id: int) -> int:
        """Подсчитать количество сессий пользователя"""
        self._logger.debug(f"Counting sessions for user {user_id}")

        try:
            result = await self.uow.session.execute(
                select(func.count()).select_from(Session).where(Session.user_id == user_id)
            )
            count = result.scalar_one()
        except Exception:
            self._logger.exception(f"Error counting sessions for user {user_id}")
            raise
        else:
            self._logger.info(f"User {user_id} has {count} sessions")
            return count

    async def count_active_user_sessions(self, user_id: int) -> int:
        """Подсчитать количество активных сессий пользователя"""
        self._logger.debug(f"Counting active sessions for user {user_id}")

        try:
            result = await self.uow.session.execute(
                select(func.count()).select_from(Session).where(and_(Session.user_id == user_id, Session.is_active))
            )
            count = result.scalar_one()
        except Exception:
            self._logger.exception(f"Error counting active sessions for user {user_id}")
            raise
        else:
            self._logger.info(f"User {user_id} has {count} active sessions")
            return count
