from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any, Protocol, TypeVar, cast

from sqlalchemy import Row, RowMapping, func, select

from src.core.logging_config import get_logger
from src.core.uow import IUnitOfWork

ModelType_co = TypeVar("ModelType_co", bound="Any", covariant=True)
CreateType_contra = TypeVar("CreateType_contra", contravariant=True)
UpdateType_contra = TypeVar("UpdateType_contra", contravariant=True)


class RepositoryProtocol(Protocol[ModelType_co, CreateType_contra, UpdateType_contra]):
    """Протокол репозитория для базовых CRUD операций."""

    async def get_by_id(self, id: int) -> ModelType_co | None: ...
    async def get_multi(self, skip: int = 0, limit: int = 100) -> Sequence[Row[Any] | RowMapping | Any]: ...
    async def count(self) -> int: ...
    async def create(self, obj_data: CreateType_contra) -> ModelType_co: ...
    async def update(self, id: int, obj_data: UpdateType_contra) -> ModelType_co | None: ...
    async def delete(self, id: int) -> bool: ...


class BaseRepository(RepositoryProtocol[ModelType_co, CreateType_contra, UpdateType_contra]):
    """Базовый CRUD-репозиторий с транзакциями.

    Предоставляет базовые операции для работы с базой данных:
    создание, чтение, обновление и удаление объектов.

    Транзакции управляются через Unit of Work (UoW).

    Наследники должны устанавливать атрибут _model для указания
    соответствующей модели базы данных.

    Attributes:
        uow: Unit of Work для управления транзакциями
        _model: Класс модели базы данных (должен быть установлен наследником)
        _logger: Логгер для записи операций
    """

    def __init__(self, uow: IUnitOfWork) -> None:
        """Инициализация базового репозитория.

        Args:
            uow: Unit of Work для управления транзакциями и сессией БД
        """
        self.uow = uow
        self._model: type[ModelType_co]  # наследник заполняет
        self._logger = get_logger(self.__class__.__name__)

    async def get_by_id(self, id: int) -> ModelType_co | None:
        """Получить объект модели по идентификатору.

        Выполняет поиск объекта в базе данных по его первичному ключу.

        Args:
            id: Идентификатор объекта для поиска

        Returns:
            Объект модели, если найден, иначе None

        Raises:
            Exception: При ошибке выполнения запроса к базе данных

        Note:
            Метод логирует время выполнения операции и результат поиска
        """
        start_time = time.time()
        self._logger.debug(f"Getting {self._model.__name__} by ID: {id}")

        try:
            result = await self.uow.session.get(cast("type[ModelType_co]", self._model), id)
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

    async def get_multi(self, skip: int = 0, limit: int = 100) -> list[ModelType_co]:
        """Получить список объектов с пагинацией.

        Извлекает объекты из базы данных с возможностью пропуска
        определенного количества записей и ограничения количества результатов.

        Args:
            skip: Количество записей для пропуска (пагинация)
            limit: Максимальное количество возвращаемых запитей

        Returns:
            Список объектов модели

        Raises:
            Exception: При ошибке выполнения запроса к базе данных

        Note:
            Метод логирует количество извлеченных объектов и время выполнения
        """
        start_time = time.time()
        self._logger.debug(f"Getting {self._model.__name__} list - skip: {skip}, limit: {limit}")

        try:
            result = await self.uow.session.execute(
                select(cast("type[ModelType_co]", self._model)).offset(skip).limit(limit)
            )
            objects = list(result.scalars().all())
            duration = time.time() - start_time

            self._logger.info(f"Retrieved {len(objects)} {self._model.__name__} objects in {duration:.3f}s")
            return objects
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting {self._model.__name__} list in {duration:.3f}s")
            raise

    async def count(self) -> int:
        """Подсчитать общее количество объектов модели в базе данных.

        Выполняет SQL COUNT запрос для подсчета всех записей
        соответствующей модели в базе данных.

        Returns:
            Общее количество объектов в базе данных

        Raises:
            Exception: При ошибке выполнения запроса к базе данных

        Note:
            Метод логирует подсчитанное количество и время выполнения
        """
        start_time = time.time()
        self._logger.debug(f"Counting {self._model.__name__} objects")

        try:
            result = await self.uow.session.execute(
                select(func.count()).select_from(cast("type[ModelType_co]", self._model))
            )
            count = result.scalar_one()
            duration = time.time() - start_time

            self._logger.info(f"Counted {count} {self._model.__name__} objects in {duration:.3f}s")
            return count
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error counting {self._model.__name__} objects in {duration:.3f}s")
            raise

    async def create(self, obj_data: CreateType_contra) -> ModelType_co:
        """Создать новый объект в базе данных.

        Добавляет новый объект в сессию базы данных и выполняет flush
        для получения сгенерированного ID.

        Args:
            obj_data: Данные для создания объекта. Может быть Pydantic моделью
                     или словарем с атрибутами объекта

        Returns:
            Созданный объект модели с присвоенным ID

        Raises:
            Exception: При ошибке создания объекта

        Note:
            Метод автоматически извлекает данные из Pydantic модели
            или использует словарь напрямую
        """
        start_time = time.time()

        try:
            data = obj_data.model_dump(exclude_unset=True) if hasattr(obj_data, "model_dump") else obj_data
            db_obj = self._model(**data)  # type: ignore[arg-type]
            self.uow.session.add(db_obj)
            await self.uow.session.flush()

            duration = time.time() - start_time
            self._logger.info(f"Created {self._model.__name__} with ID {db_obj.id} in {duration:.3f}s")

            return db_obj
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error creating {self._model.__name__} in {duration:.3f}s")
            raise

    async def update(self, id: int, obj_data: UpdateType_contra) -> ModelType_co | None:
        """Обновить существующий объект в базе данных.

        Находит объект по ID и обновляет его поля переданными данными.

        Args:
            id: Идентификатор объекта для обновления
            obj_data: Новые данные для объекта. Может быть Pydantic моделью
                     или словарем с атрибутами объекта

        Returns:
            Обновленный объект модели, если найден, иначе None

        Raises:
            Exception: При ошибке обновления объекта

        Note:
            - Обновляются только поля, присутствующие в obj_data
            - Метод логирует список обновленных полей
        """
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

    async def delete(self, id: int) -> bool:
        """Удалить объект из базы данных.

        Находит объект по ID и удаляет его из сессии базы данных.

        Args:
            id: Идентификатор объекта для удаления

        Returns:
            True, если объект был успешно удален, False если объект не найден

        Raises:
            Exception: При ошибке удаления объекта
        """
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
