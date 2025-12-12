from __future__ import annotations

from typing import Any, Protocol, TypeVar

from src.core.exceptions import NotFoundError

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class RepositoryProtocol(Protocol):
    """Protocol для типизации репозиториев (асинхронный)"""

    async def get_by_id(self, id: int) -> ModelType | None: ...

    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ModelType]: ...

    async def create(self, obj_data: CreateSchemaType) -> ModelType: ...

    async def update(self, id: int, obj_data: UpdateSchemaType) -> ModelType | None: ...

    async def delete(self, id: int) -> bool: ...

    async def count(self) -> int: ...

    async def bulk_create(self, obj_data_list: list[CreateSchemaType]) -> list[ModelType]: ...

    async def exists(self, id: int) -> bool: ...


class BaseService[ModelType, CreateSchemaType, UpdateSchemaType]:
    """Улучшенный базовый сервис с дополнительными возможностями (асинхронный)"""

    def __init__(self, repository: RepositoryProtocol) -> None:
        self._repository = repository

    async def get_by_id(self, id: int) -> ModelType:
        """Получить объект по ID"""
        result = await self._repository.get_by_id(id)
        if result is None:
            raise NotFoundError(f"Object with id {id} not found")
        return result

    async def get_multi(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """Получить список объектов с пагинацией"""
        return await self._repository.get_multi(skip=skip, limit=limit)

    async def create(self, obj_data: CreateSchemaType) -> ModelType:
        """Создать новый объект"""
        return await self._repository.create(obj_data)

    async def update(self, id: int, obj_data: UpdateSchemaType) -> ModelType:
        """Обновить объект"""
        result = await self._repository.update(id, obj_data)
        if result is None:
            raise NotFoundError(f"Object with id {id} not found")
        return result

    async def delete(self, id: int) -> bool:
        """Удалить объект"""
        result = await self._repository.delete(id)
        if not result:
            raise NotFoundError(f"Object with id {id} not found")
        return result

    async def count(self) -> int:
        """Подсчитать количество объектов"""
        return await self._repository.count()

    async def bulk_create(self, obj_data_list: list[CreateSchemaType]) -> list[ModelType]:
        """Создать несколько объектов за один раз"""
        return await self._repository.bulk_create(obj_data_list)

    async def exists(self, id: int) -> bool:
        """Проверить существование объекта"""
        return await self._repository.exists(id)

    async def get_or_create(self, defaults: dict | None = None, **kwargs) -> tuple[ModelType, bool]:
        """Получить объект или создать новый, если не найден"""
        id = kwargs.get("id", 0)
        existing = await self._repository.get_by_id(id)

        # Если объект не найден по ID, создаем новый
        if existing is None:
            create_data = kwargs.copy()
            if defaults:
                create_data.update(defaults)
            new_obj = await self.create(create_data)
            return new_obj, True

        return existing, False

    async def update_or_create(self, defaults: dict | None = None, **kwargs) -> tuple[ModelType, bool]:
        """Обновить объект или создать новый, если не найден"""
        id = kwargs.get("id", 0)
        existing = await self._repository.get_by_id(id)

        if existing is None:
            create_data = kwargs.copy()
            if defaults:
                create_data.update(defaults)
            new_obj = await self.create(create_data)
            return new_obj, True
        update_data = kwargs.copy()
        if defaults:
            update_data.update(defaults)
        updated_obj = await self.update(id, update_data)
        return updated_obj, False

    async def get_paginated(self, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        """Получить объекты с пагинацией"""
        skip = (page - 1) * page_size
        items = await self._repository.get_multi(skip=skip, limit=page_size)
        total = await self._repository.count()

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
