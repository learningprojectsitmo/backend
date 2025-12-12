from typing import Any

from fastapi import HTTPException, status


class BaseAppException(HTTPException):
    """Базовый класс для всех исключений приложения"""
    def __init__(
        self,
        status_code: int,
        detail: Any = None,
        headers: dict[str, Any] | None = None
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)


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


class PermissionError(BaseAppException):
    """Исключение для ошибок прав доступа"""
    def __init__(self, detail: Any = "Permission denied", headers: dict[str, Any] | None = None) -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, detail, headers)


class DatabaseError(BaseAppException):
    """Исключение для ошибок базы данных"""
    def __init__(self, detail: Any = "Database operation failed", headers: dict[str, Any] | None = None) -> None:
        super().__init__(status.HTTP_500_INTERNAL_SERVER_ERROR, detail, headers)


class BusinessLogicError(BaseAppException):
    """Исключение для ошибок бизнес-логики"""
    def __init__(self, detail: Any = "Business logic error", headers: dict[str, Any] | None = None) -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail, headers)
