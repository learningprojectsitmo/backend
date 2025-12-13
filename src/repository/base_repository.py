from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any, Protocol, TypeVar

from sqlalchemy import Row, RowMapping, func, select

from core.uow import IUnitOfWork
from src.core.logging_config import get_logger

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
        self._logger = get_logger(self.__class__.__name__)

    # ---------- чтение ----------
    async def get_by_id(self, id: int) -> ModelType | None:
        start_time = time.time()
        self._logger.debug(f"Getting {self._model.__name__} by ID: {id}")

        try:
            result = await self.uow.session.get(self._model, id)
            duration = time.time() - start_time

            if result:
                self._logger.info(f"Successfully retrieved {self._model.__name__} with ID {id} in {duration:.3f}s")
            else:
                self._logger.warning(f"{self._model.__name__} with ID {id} not found in {duration:.3f}s")

            return result
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting {self._model.__name__} by ID {id} in {duration:.3f}s")
            raise

    async def get_multi(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        start_time = time.time()
        self._logger.debug(f"Getting {self._model.__name__} list - skip: {skip}, limit: {limit}")

        try:
            result = await self.uow.session.execute(select(self._model).offset(skip).limit(limit))
            objects = result.scalars().all()
            duration = time.time() - start_time

            self._logger.info(f"Retrieved {len(objects)} {self._model.__name__} objects in {duration:.3f}s")
            return objects
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting {self._model.__name__} list in {duration:.3f}s")
            raise

    async def count(self) -> int:
        start_time = time.time()
        self._logger.debug(f"Counting {self._model.__name__} objects")

        try:
            result = await self.uow.session.execute(select(func.count()).select_from(self._model))
            count = result.scalar_one()
            duration = time.time() - start_time

            self._logger.info(f"Counted {count} {self._model.__name__} objects in {duration:.3f}s")
            return count
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error counting {self._model.__name__} objects in {duration:.3f}s")
            raise

    # ---------- создание ----------
    async def create(self, obj_data: CreateType) -> ModelType:
        start_time = time.time()

        try:
            data = obj_data.model_dump(exclude_unset=True) if hasattr(obj_data, "model_dump") else obj_data
            db_obj = self._model(**data)
            self.uow.session.add(db_obj)
            await self.uow.session.flush()

            duration = time.time() - start_time
            self._logger.info(f"Created {self._model.__name__} with ID {db_obj.id} in {duration:.3f}s")

            return db_obj
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error creating {self._model.__name__} in {duration:.3f}s")
            raise

    # ---------- обновление ----------
    async def update(self, id: int, obj_data: UpdateType) -> ModelType | None:
        start_time = time.time()
        self._logger.info(f"Updating {self._model.__name__} with ID {id}")

        try:
            db_obj = await self.get_by_id(id)
            if not db_obj:
                duration = time.time() - start_time
                self._logger.warning(f"{self._model.__name__} with ID {id} not found for update in {duration:.3f}s")
                return None

            data = obj_data.model_dump(exclude_unset=True) if hasattr(obj_data, "model_dump") else obj_data
            updated_fields = list(data.keys())

            for field, value in data.items():
                setattr(db_obj, field, value)

            duration = time.time() - start_time
            self._logger.info(
                f"Updated {self._model.__name__} with ID {id} - fields: {updated_fields} in {duration:.3f}s"
            )

            return db_obj
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error updating {self._model.__name__} with ID {id} in {duration:.3f}s")
            raise

    # ---------- удаление ----------
    async def delete(self, id: int) -> bool:
        start_time = time.time()
        self._logger.info(f"Deleting {self._model.__name__} with ID {id}")

        try:
            db_obj = await self.get_by_id(id)
            if not db_obj:
                duration = time.time() - start_time
                self._logger.warning(f"{self._model.__name__} with ID {id} not found for deletion in {duration:.3f}s")
                return False

            await self.uow.session.delete(db_obj)
            duration = time.time() - start_time

            self._logger.info(f"Deleted {self._model.__name__} with ID {id} in {duration:.3f}s")
            return True
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error deleting {self._model.__name__} with ID {id} in {duration:.3f}s")
            raise
