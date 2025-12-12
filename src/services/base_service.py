from abc import ABC
from typing import Any, Generic, Protocol, TypeVar

ModelType = TypeVar('ModelType', bound=Any)
CreateSchemaType = TypeVar('CreateSchemaType', bound=Any)
UpdateSchemaType = TypeVar('UpdateSchemaType', bound=Any)


class RepositoryProtocol(Protocol):
    """Protocol для типизации репозиториев"""
    def get_by_id(self, id: int) -> Any: ...
    def get_multi(self, skip: int = 0, limit: int = 100): ...
    def create(self, obj_data: CreateSchemaType): ...
    def update(self, id: int, obj_data: UpdateSchemaType): ...
    def delete(self, id: int): ...
    def count(self) -> int: ...
    def bulk_create(self, obj_data_list: list[CreateSchemaType]) -> list[ModelType]: ...
    def exists(self, id: int) -> bool: ...


class BaseService(ABC, Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """Улучшенный базовый сервис с дополнительными возможностями"""

    def __init__(self, repository: RepositoryProtocol) -> None:
        self._repository = repository

    def get_by_id(self, id: int) -> ModelType:
        """Получить объект по ID"""
        return self._repository.get_by_id(id)

    def get_multi(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """Получить список объектов с пагинацией"""
        return self._repository.get_multi(skip=skip, limit=limit)

    def create(self, obj_data: CreateSchemaType) -> ModelType:
        """Создать новый объект"""
        return self._repository.create(obj_data)

    def update(self, id: int, obj_data: UpdateSchemaType) -> ModelType:
        """Обновить объект"""
        return self._repository.update(id, obj_data)

    def delete(self, id: int) -> bool:
        """Удалить объект"""
        return self._repository.delete(id)

    def count(self) -> int:
        """Подсчитать количество объектов"""
        return self._repository.count()

    def bulk_create(self, obj_data_list: list[CreateSchemaType]) -> list[ModelType]:
        """Создать несколько объектов за один раз"""
        return self._repository.bulk_create(obj_data_list)

    def exists(self, id: int) -> bool:
        """Проверить существование объекта"""
        return self._repository.exists(id)

    def get_or_create(self, defaults: dict | None = None, **kwargs) -> tuple[ModelType, bool]:
        """Получить объект или создать новый, если не найден"""
        existing = self._repository.get_by_id(kwargs.get('id', 0))

        # Если объект не найден по ID, создаем новый
        if existing is None:
            create_data = kwargs.copy()
            if defaults:
                create_data.update(defaults)
            new_obj = self.create(create_data)
            return new_obj, True

        return existing, False

    def update_or_create(self, defaults: dict | None = None, **kwargs) -> tuple[ModelType, bool]:
        """Обновить объект или создать новый, если не существует"""
        obj_id = kwargs.get('id')

        if obj_id and self.exists(obj_id):
            updated_obj = self.update(obj_id, kwargs)
            return updated_obj, False
        else:
            create_data = kwargs.copy()
            if defaults:
                create_data.update(defaults)
            new_obj = self.create(create_data)
            return new_obj, True

    def get_paginated(self, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        """Получить пагинированные данные с метаданными"""
        skip = (page - 1) * page_size
        items = self.get_multi(skip=skip, limit=page_size)
        total = self.count()

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size  # ceiling division
        }

    def close_scoped_session(self):
        """Закрыть scoped сессию"""
        self._repository.close_scoped_session()
