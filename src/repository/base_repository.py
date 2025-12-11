from typing import Any, Generic, Protocol, TypeVar

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

ModelType = TypeVar('ModelType', bound=Any)
CreateSchemaType = TypeVar('CreateSchemaType', bound=Any)
UpdateSchemaType = TypeVar('UpdateSchemaType', bound=Any)


class RepositoryProtocol(Protocol):
    """Protocol для типизации репозиториев"""
    def get_by_id(self, id: int) -> ModelType | None:
        """Получить объект по ID"""
        ...

    def get_multi(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> list[ModelType]:
        """Получить список объектов с пагинацией"""
        ...

    def create(self, obj_data: CreateSchemaType) -> ModelType:
        """Создать новый объект"""
        ...

    def update(self, id: int, obj_data: UpdateSchemaType) -> ModelType | None:
        """Обновить объект"""
        ...

    def delete(self, id: int) -> bool:
        """Удалить объект"""
        ...

    def count(self) -> int:
        """Подсчитать количество объектов"""
        ...


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """Упрощенный базовый репозиторий для работы с базой данных"""
    
    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._session = None
        self._model = None

    def _get_session(self) -> Session:
        """Получить сессию базы данных"""
        if self._session is None:
            self._session = self._session_factory()
        return self._session

    def close_scoped_session(self):
        """Закрыть scoped сессию"""
        if self._session:
            try:
                self._session.close()
            except Exception as e:
                # Логируем ошибку, но не прерываем выполнение
                print(f"Error closing session: {e}")
            finally:
                self._session = None

    def _commit_session(self):
        """Зафиксировать изменения в базе данных"""
        try:
            self._session.commit()
        except SQLAlchemyError as e:
            self._session.rollback()
            raise e

    def _refresh_session(self, obj: ModelType):
        """Обновить объект из базы данных"""
        self._session.refresh(obj)

    def get_by_id(self, id: int) -> ModelType | None:
        """Получить объект по ID"""
        db = self._get_session()
        return db.query(self._model).filter(self._model.id == id).first() if self._model else None

    def get_multi(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> list[ModelType]:
        """Получить список объектов с пагинацией"""
        db = self._get_session()
        return db.query(self._model).offset(skip).limit(limit).all() if self._model else []

    def create(self, obj_data: CreateSchemaType) -> ModelType:
        """Создать новый объект"""
        db = self._get_session()
        
        # Поддержка как dict, так и Pydantic models
        if hasattr(obj_data, 'model_dump'):
            obj_dict = obj_data.model_dump(exclude_unset=True)
        else:
            obj_dict = obj_data
            
        db_obj = self._model(**obj_dict)
        db.add(db_obj)
        
        try:
            self._commit_session()
            self._refresh_session(db_obj)
            return db_obj
        except IntegrityError as e:
            db.rollback()
            raise ValueError(f"Error creating object: {e}")

    def update(self, id: int, obj_data: UpdateSchemaType) -> ModelType | None:
        """Обновить объект"""
        db = self._get_session()
        db_obj = db.query(self._model).filter(self._model.id == id).first() if self._model else None
        
        if not db_obj:
            return None

        # Поддержка как dict, так и Pydantic models
        if hasattr(obj_data, 'model_dump'):
            update_data = obj_data.model_dump(exclude_unset=True)
        else:
            update_data = obj_data
            
        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        try:
            self._commit_session()
            self._refresh_session(db_obj)
            return db_obj
        except SQLAlchemyError as e:
            db.rollback()
            raise ValueError(f"Error updating object: {e}")

    def delete(self, id: int) -> bool:
        """Удалить объект"""
        db = self._get_session()
        db_obj = db.query(self._model).filter(self._model.id == id).first() if self._model else None
        
        if not db_obj:
            return False

        try:
            db.delete(db_obj)
            self._commit_session()
            return True
        except SQLAlchemyError as e:
            db.rollback()
            raise ValueError(f"Error deleting object: {e}")

    def count(self) -> int:
        """Подсчитать количество объектов"""
        db = self._get_session()
        return db.query(self._model).count() if self._model else 0

    def bulk_create(self, obj_data_list: list[CreateSchemaType]) -> list[ModelType]:
        """Создать несколько объектов за один раз"""
        db = self._get_session()
        db_objects = []
        
        for obj_data in obj_data_list:
            # Поддержка как dict, так и Pydantic models
            if hasattr(obj_data, 'model_dump'):
                obj_dict = obj_data.model_dump(exclude_unset=True)
            else:
                obj_dict = obj_data
                
            db_obj = self._model(**obj_dict)
            db_objects.append(db_obj)
        
        try:
            db.add_all(db_objects)
            self._commit_session()
            for db_obj in db_objects:
                self._refresh_session(db_obj)
            return db_objects
        except IntegrityError as e:
            db.rollback()
            raise ValueError(f"Error creating objects: {e}")

    def exists(self, id: int) -> bool:
        """Проверить существование объекта с данным ID"""
        db = self._get_session()
        return db.query(self._model.id).filter(self._model.id == id).first() is not None if self._model else False