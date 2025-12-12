from __future__ import annotations

from typing import Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DatabaseError

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class BaseRepository[ModelType, CreateSchemaType, UpdateSchemaType]:
    """Упрощенный базовый репозиторий для работы с базой данных (асинхронный)"""

    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._model = None

    async def _get_session(self) -> AsyncSession:
        """Получить сессию базы данных"""
        async with self._session_factory() as session:
            return session

    async def _commit_session(self, session: AsyncSession):
        """Зафиксировать изменения в базе данных"""
        try:
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            raise

    async def _refresh_session(self, session: AsyncSession, obj: ModelType):
        """Обновить объект из базы данных"""
        await session.refresh(obj)

    async def get_by_id(self, id: int) -> ModelType | None:
        """Получить объект по ID"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(self._model).where(self._model.id == id),
            )
            return result.scalar_one_or_none()
        finally:
            await session.close()

    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ModelType]:
        """Получить список объектов с пагинацией"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(self._model).offset(skip).limit(limit),
            )
            return result.scalars().all()
        finally:
            await session.close()

    async def create(self, obj_data: CreateSchemaType) -> ModelType:
        """Создать новый объект"""
        session = await self._get_session()
        try:
            # Поддержка как dict, так и Pydantic models
            obj_dict = obj_data.model_dump(exclude_unset=True) if hasattr(obj_data, "model_dump") else obj_data

            db_obj = self._model(**obj_dict)
            session.add(db_obj)
            await self._commit_session(session)
            await self._refresh_session(session, db_obj)
            return db_obj
        except IntegrityError as e:
            await session.rollback()
            raise DatabaseError(f"Error creating object: {e}") from e
        finally:
            await session.close()

    async def update(self, id: int, obj_data: UpdateSchemaType) -> ModelType | None:
        """Обновить объект"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(self._model).where(self._model.id == id),
            )
            db_obj = result.scalar_one_or_none()

            if not db_obj:
                return None

            # Поддержка как dict, так и Pydantic models
            update_data = obj_data.model_dump(exclude_unset=True) if hasattr(obj_data, "model_dump") else obj_data

            for field, value in update_data.items():
                if hasattr(db_obj, field):
                    setattr(db_obj, field, value)

            await self._commit_session(session)
            await self._refresh_session(session, db_obj)
            return db_obj
        except SQLAlchemyError as e:
            await session.rollback()
            raise DatabaseError(f"Error updating object: {e}") from e
        finally:
            await session.close()

    async def delete(self, id: int) -> bool:
        """Удалить объект"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(self._model).where(self._model.id == id),
            )
            db_obj = result.scalar_one_or_none()

            if not db_obj:
                return False

            await session.delete(db_obj)
            await self._commit_session(session)
            return True
        except SQLAlchemyError as e:
            await session.rollback()
            raise DatabaseError(f"Error deleting object: {e}") from e
        finally:
            await session.close()

    async def count(self) -> int:
        """Подсчитать количество объектов"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(self._model).count(),
            )
            return result.scalar()
        finally:
            await session.close()

    async def bulk_create(self, obj_data_list: list[CreateSchemaType]) -> list[ModelType]:
        """Создать несколько объектов за один раз"""
        session = await self._get_session()
        db_objects = []

        try:
            for obj_data in obj_data_list:
                # Поддержка как dict, так и Pydantic models
                obj_dict = obj_data.model_dump(exclude_unset=True) if hasattr(obj_data, "model_dump") else obj_data

                db_obj = self._model(**obj_dict)
                db_objects.append(db_obj)

            session.add_all(db_objects)
            await self._commit_session(session)
            for db_obj in db_objects:
                await self._refresh_session(session, db_obj)
            return db_objects
        except IntegrityError as e:
            await session.rollback()
            raise DatabaseError(f"Error creating objects: {e}") from e
        finally:
            await session.close()

    async def exists(self, id: int) -> bool:
        """Проверить существование объекта"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(self._model.id).where(self._model.id == id).limit(1),
            )
            return result.first() is not None
        finally:
            await session.close()


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
