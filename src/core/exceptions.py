from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from src.core.logging_config import get_logger, security_logger


class BaseAppException(HTTPException):
    """Базовый класс для всех исключений приложения"""

    def __init__(
        self,
        status_code: int,
        detail: Any = None,
        headers: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)

        # Логирование исключения
        logger = get_logger(__name__)
        logger.error(
            f"Application exception - Status: {status_code}, Detail: {detail}, "
            f"Exception type: {self.__class__.__name__}"
        )


class NotFoundError(BaseAppException):
    """Исключение для не найденных объектов"""

    def __init__(self, detail: Any = "Resource not found", headers: dict[str, Any] | None = None) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, detail, headers)


class DuplicatedError(BaseAppException):
    """Исключение для дублирования данных"""

    def __init__(self, detail: Any = "Resource already exists", headers: dict[str, Any] | None = None) -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, detail, headers)


class ValidationError(BaseAppException):
    """Исключение для ошибок валидации"""

    def __init__(self, detail: Any = "Validation failed", headers: dict[str, Any] | None = None) -> None:
        super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, detail, headers)


class AuthError(BaseAppException):
    """Исключение для ошибок аутентификации"""

    def __init__(self, detail: Any = "Authentication failed", headers: dict[str, Any] | None = None) -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail, headers)

        # Специальное логирование для ошибок аутентификации
        security_logger.logger.warning(f"Authentication error - Detail: {detail}")


class PermissionError(BaseAppException):
    """Исключение для ошибок прав доступа"""

    def __init__(self, detail: Any = "Permission denied", headers: dict[str, Any] | None = None) -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, detail, headers)

        # Специальное логирование для ошибок доступа
        security_logger.logger.warning(f"Permission denied - Detail: {detail}")


class DatabaseError(BaseAppException):
    """Исключение для ошибок базы данных"""

    def __init__(self, detail: Any = "Database operation failed", headers: dict[str, Any] | None = None) -> None:
        super().__init__(status.HTTP_500_INTERNAL_SERVER_ERROR, detail, headers)

        # Специальное логирование для ошибок базы данных
        logger = get_logger(__name__)
        logger.critical(f"Database error - Detail: {detail}", exc_info=True)


class BusinessLogicError(BaseAppException):
    """Исключение для ошибок бизнес-логики"""

    def __init__(self, detail: Any = "Business logic error", headers: dict[str, Any] | None = None) -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail, headers)
