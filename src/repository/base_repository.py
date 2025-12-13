from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, TypeVar

from sqlalchemy import Row, RowMapping, func, select

from core.uow import IUnitOfWork

ModelType = TypeVar("ModelType")
CreateType = TypeVar("CreateType")
UpdateType = TypeVar("UpdateType")


# ----------- контракт -----------
class RepositoryProtocol(Protocol[ModelType, CreateType, UpdateType]):
    async def get_by_id(self, id: int) -> ModelType | None: ...
    async def get_multi(self, skip: int = 0, limit: int = 100) -> Sequence[Row[Any] | RowMapping | Any]: ...
    async def count(self) -> int: ...
    async def create(self, obj_data: CreateType) -> ModelType: ...
    async def update(self, id: int, obj_data: UpdateType) -> ModelType | None: ...
    async def delete(self, id: int) -> bool: ...


# ----------- реализация -----------
class BaseRepository(RepositoryProtocol[ModelType, CreateType, UpdateType]):
    """Базовый CRUD-репозиторий. С транзакциями им занимается UoW."""

    def __init__(self, uow: IUnitOfWork) -> None:
        self.uow = uow
        self._model: type[ModelType] | None = None  # наследник заполняет

    # ---------- чтение ----------
    async def get_by_id(self, id: int) -> ModelType | None:
        return await self.uow.session.get(self._model, id)

    async def get_multi(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        result = await self.uow.session.execute(select(self._model).offset(skip).limit(limit))
        return result.scalars().all()

    async def count(self) -> int:
        result = await self.uow.session.execute(select(func.count()).select_from(self._model))
        return result.scalar_one()

    # ---------- создание ----------
    async def create(self, obj_data: CreateType) -> ModelType:
        data = obj_data.model_dump(exclude_unset=True) if hasattr(obj_data, "model_dump") else obj_data
        db_obj = self._model(**data)
        self.uow.session.add(db_obj)
        await self.uow.session.flush()
        return db_obj

    # ---------- обновление ----------
    async def update(self, id: int, obj_data: UpdateType) -> ModelType | None:
        db_obj = await self.get_by_id(id)
        if not db_obj:
            return None
        data = obj_data.model_dump(exclude_unset=True) if hasattr(obj_data, "model_dump") else obj_data
        for field, value in data.items():
            setattr(db_obj, field, value)
        return db_obj

    # ---------- удаление ----------
    async def delete(self, id: int) -> bool:
        db_obj = await self.get_by_id(id)
        if not db_obj:
            return False
        await self.uow.session.delete(db_obj)
        return True
