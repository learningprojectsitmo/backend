from __future__ import annotations

import time
from typing import Any, List, Optional, Dict, Sequence
from sqlalchemy import and_, or_, func, select, update, delete
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql import Select

from src.core.logging_config import get_logger
from src.core.uow import IUnitOfWork
from src.repository.base_repository import BaseRepository
from src.model.models import Task, TaskAssignee, TaskHistory, ColumnTemplate, TaskStatus, User
from src.schema.task import TaskCreate, TaskUpdate, TaskStatusUpdate, ColumnTemplateCreate, ColumnTemplateUpdate


class TaskRepository(BaseRepository[Task, TaskCreate, TaskUpdate]):
    """Репозиторий для работы с задачами канбан-доски.

    Предоставляет методы для CRUD операций с задачами, а также
    специфические методы для работы с канбан-доской:
    - Обновление статуса с записью в историю
    - Переупорядочивание задач в колонках
    - Фильтрация задач по различным критериям
    - Работа с колонками
    """

    def __init__(self, uow: IUnitOfWork) -> None:
        """Инициализация репозитория задач."""
        super().__init__(uow)
        self._model = Task
        self._logger = get_logger(__name__)

    async def get_by_id(self, id: int) -> Task | None:
        """Получить задачу по ID с загрузкой связанных данных.

        Args:
            id: Идентификатор задачи

        Returns:
            Task | None: Задача с загруженными ответственными и автором
        """
        start_time = time.time()
        self._logger.debug(f"Getting Task by ID: {id} with relations")

        try:
            query = (
                select(self._model)
                .where(self._model.id == id)
                .options(
                    selectinload(self._model.assignees).selectinload(TaskAssignee.user),
                    selectinload(self._model.created_by),
                    selectinload(self._model.project)
                )
            )
            result = await self.uow.session.execute(query)
            task = result.scalar_one_or_none()

            duration = time.time() - start_time
            if task:
                self._logger.info(f"Retrieved Task with ID {id} in {duration:.3f}s")
            else:
                self._logger.warning(f"Task with ID {id} not found in {duration:.3f}s")

            return task
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting Task with ID {id} in {duration:.3f}s")
            raise

    async def get_tasks_by_project(
        self, 
        project_id: int, 
        filters: Optional[Dict[str, Any]] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Task]:
        """Получить задачи проекта с фильтрацией и пагинацией.

        Args:
            project_id: ID проекта
            filters: Словарь с фильтрами (status, priority, assignee_id и т.д.)
            skip: Количество записей для пропуска
            limit: Максимальное количество возвращаемых записей

        Returns:
            List[Task]: Список задач, отсортированных по статусу и порядку
        """
        start_time = time.time()
        self._logger.debug(f"Getting tasks for project {project_id} with filters: {filters}")

        try:
            query = (
                select(self._model)
                .where(self._model.project_id == project_id)
                .options(
                    selectinload(self._model.assignees).selectinload(TaskAssignee.user),
                    selectinload(self._model.created_by)
                )
            )

            # Применяем фильтры
            if filters:
                query = self._apply_filters(query, filters)

            # Сортировка по статусу и порядку
            query = query.order_by(self._model.status, self._model.order)

            # Пагинация
            query = query.offset(skip).limit(limit)

            result = await self.uow.session.execute(query)
            tasks = list(result.scalars().all())

            duration = time.time() - start_time
            self._logger.info(f"Retrieved {len(tasks)} tasks for project {project_id} in {duration:.3f}s")

            return tasks
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting tasks for project {project_id} in {duration:.3f}s")
            raise

    async def count_by_project(self, project_id: int, filters: Optional[Dict[str, Any]] = None) -> int:
        """Подсчитать количество задач в проекте с учетом фильтров.

        Args:
            project_id: ID проекта
            filters: Словарь с фильтрами

        Returns:
            int: Количество задач
        """
        start_time = time.time()
        self._logger.debug(f"Counting tasks for project {project_id}")

        try:
            query = select(func.count()).select_from(self._model).where(self._model.project_id == project_id)

            if filters:
                # Для count не нужно загружать связи, только условия
                count_query = self._apply_filters(query, filters, for_count=True)
            else:
                count_query = query

            result = await self.uow.session.execute(count_query)
            count = result.scalar_one()

            duration = time.time() - start_time
            self._logger.info(f"Counted {count} tasks for project {project_id} in {duration:.3f}s")

            return count
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error counting tasks for project {project_id} in {duration:.3f}s")
            raise

    async def create(self, obj_data: TaskCreate) -> Task:
        """Создать новую задачу.

        Args:
            obj_data: Данные для создания задачи

        Returns:
            Task: Созданная задача
        """
        start_time = time.time()
        self._logger.info(f"Creating new Task in project {obj_data.project_id}")

        try:
            # Определяем следующий порядковый номер
            next_order = await self._get_next_order(obj_data.project_id, TaskStatus.NOT_STARTED)

            # Создаем задачу без assignee_ids
            data = obj_data.model_dump(exclude_unset=True, exclude={'assignee_ids'})
            db_obj = self._model(**data, order=next_order)
            self.uow.session.add(db_obj)
            await self.uow.session.flush()

            # Добавляем ответственных, если есть
            if obj_data.assignee_ids:
                for user_id in obj_data.assignee_ids:
                    assignee = TaskAssignee(task_id=db_obj.id, user_id=user_id)
                    self.uow.session.add(assignee)
                await self.uow.session.flush()

            duration = time.time() - start_time
            self._logger.info(f"Created Task with ID {db_obj.id} in {duration:.3f}s")

            # Возвращаем задачу со всеми связями
            return await self.get_by_id(db_obj.id)  # type: ignore
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error creating Task in {duration:.3f}s")
            raise

    async def update(self, id: int, obj_data: TaskUpdate) -> Task | None:
        """Обновить задачу.

        Args:
            id: ID задачи
            obj_data: Данные для обновления

        Returns:
            Task | None: Обновленная задача или None
        """
        start_time = time.time()
        self._logger.info(f"Updating Task with ID {id}")

        try:
            db_obj = await self.get_by_id(id)
            if not db_obj:
                duration = time.time() - start_time
                self._logger.warning(f"Task with ID {id} not found for update in {duration:.3f}s")
                return None

            # Обновляем поля
            data = obj_data.model_dump(exclude_unset=True, exclude={'assignee_ids'})
            updated_fields = list(data.keys())
            for field, value in data.items():
                setattr(db_obj, field, value)

            # Обновляем ответственных, если указаны
            if obj_data.assignee_ids is not None:
                # Удаляем старых
                await self.uow.session.execute(
                    delete(TaskAssignee).where(TaskAssignee.task_id == id)
                )

                # Добавляем новых
                for user_id in obj_data.assignee_ids:
                    assignee = TaskAssignee(task_id=id, user_id=user_id)
                    self.uow.session.add(assignee)

                updated_fields.append('assignees')

            await self.uow.session.flush()

            duration = time.time() - start_time
            self._logger.info(f"Updated Task with ID {id} - fields: {updated_fields} in {duration:.3f}s")

            return await self.get_by_id(id)
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error updating Task with ID {id} in {duration:.3f}s")
            raise

    async def update_status(self, id: int, status_update: TaskStatusUpdate, changed_by_id: int) -> Task | None:
        """Обновить статус задачи с записью в историю.

        Args:
            id: ID задачи
            status_update: Новый статус и порядок
            changed_by_id: ID пользователя, изменившего статус

        Returns:
            Task | None: Обновленная задача или None
        """
        start_time = time.time()
        self._logger.info(f"Updating status of Task {id} to {status_update.status}")

        try:
            db_obj = await self.get_by_id(id)
            if not db_obj:
                duration = time.time() - start_time
                self._logger.warning(f"Task with ID {id} not found for status update in {duration:.3f}s")
                return None

            old_status = db_obj.status

            # Обновляем статус и порядок
            db_obj.status = status_update.status
            db_obj.order = status_update.order

            # Записываем в историю
            history = TaskHistory(
                task_id=id,
                changed_by_id=changed_by_id,
                old_status=old_status,
                new_status=status_update.status,
                change_type='status'
            )
            self.uow.session.add(history)

            await self.uow.session.flush()

            duration = time.time() - start_time
            self._logger.info(f"Updated status of Task {id} from {old_status} to {status_update.status} in {duration:.3f}s")

            return await self.get_by_id(id)
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error updating status of Task {id} in {duration:.3f}s")
            raise

    async def reorder_tasks(self, project_id: int, status: TaskStatus, task_orders: List[Dict[str, Any]]) -> bool:
        """Изменить порядок задач в колонке.

        Args:
            project_id: ID проекта
            status: Статус задач (колонка)
            task_orders: Список словарей с id и новым order

        Returns:
            bool: True если успешно
        """
        start_time = time.time()
        self._logger.info(f"Reordering tasks in project {project_id}, status {status}")

        try:
            for item in task_orders:
                stmt = (
                    update(self._model)
                    .where(
                        and_(
                            self._model.id == item['id'],
                            self._model.project_id == project_id,
                            self._model.status == status
                        )
                    )
                    .values(order=item['order'])
                )
                await self.uow.session.execute(stmt)

            duration = time.time() - start_time
            self._logger.info(f"Reordered {len(task_orders)} tasks in {duration:.3f}s")

            return True
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error reordering tasks in {duration:.3f}s")
            raise

    async def get_task_history(self, task_id: int, limit: int = 50) -> List[TaskHistory]:
        """Получить историю изменений задачи.

        Args:
            task_id: ID задачи
            limit: Максимальное количество записей

        Returns:
            List[TaskHistory]: Список записей истории
        """
        start_time = time.time()
        self._logger.debug(f"Getting history for Task {task_id}")

        try:
            query = (
                select(TaskHistory)
                .where(TaskHistory.task_id == task_id)
                .options(selectinload(TaskHistory.changed_by))
                .order_by(TaskHistory.created_at.desc())
                .limit(limit)
            )
            result = await self.uow.session.execute(query)
            history = list(result.scalars().all())

            duration = time.time() - start_time
            self._logger.info(f"Retrieved {len(history)} history records for Task {task_id} in {duration:.3f}s")

            return history
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting history for Task {task_id} in {duration:.3f}s")
            raise

    async def delete(self, id: int) -> bool:
        """Удалить задачу.

        Args:
            id: ID задачи

        Returns:
            bool: True если успешно
        """
        start_time = time.time()
        self._logger.info(f"Deleting Task with ID {id}")

        try:
            # Сначала удаляем связанные записи
            await self.uow.session.execute(delete(TaskAssignee).where(TaskAssignee.task_id == id))
            await self.uow.session.execute(delete(TaskHistory).where(TaskHistory.task_id == id))

            # Затем удаляем задачу
            stmt = delete(self._model).where(self._model.id == id)
            result = await self.uow.session.execute(stmt)

            duration = time.time() - start_time
            if result.rowcount > 0:
                self._logger.info(f"Deleted Task with ID {id} in {duration:.3f}s")
                return True
            else:
                self._logger.warning(f"Task with ID {id} not found for deletion in {duration:.3f}s")
                return False
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error deleting Task with ID {id} in {duration:.3f}s")
            raise

    async def _get_next_order(self, project_id: int, status: TaskStatus) -> int:
        """Получить следующий порядковый номер для задачи в колонке.

        Args:
            project_id: ID проекта
            status: Статус задачи (колонка)

        Returns:
            int: Следующий порядковый номер
        """
        query = (
            select(func.max(self._model.order))
            .where(
                and_(
                    self._model.project_id == project_id,
                    self._model.status == status
                )
            )
        )
        result = await self.uow.session.execute(query)
        max_order = result.scalar_one()
        return (max_order + 1) if max_order is not None else 0

    def _apply_filters(self, query: Select, filters: Dict[str, Any], for_count: bool = False) -> Select:
        """Применить фильтры к запросу.

        Args:
            query: SQLAlchemy Select запрос
            filters: Словарь с фильтрами
            for_count: Флаг, что запрос для подсчета (не загружать связи)

        Returns:
            Select: Запрос с примененными фильтрами
        """
        if filters.get('status'):
            query = query.where(self._model.status == filters['status'])

        if filters.get('priority'):
            query = query.where(self._model.priority == filters['priority'])

        if filters.get('assignee_id') and not for_count:
            # Для фильтрации по ответственному нужно присоединить таблицу
            query = query.join(TaskAssignee).where(TaskAssignee.user_id == filters['assignee_id'])

        if filters.get('created_by_id'):
            query = query.where(self._model.created_by_id == filters['created_by_id'])

        if filters.get('tag'):
            query = query.where(self._model.tags.like(f"%{filters['tag']}%"))

        if filters.get('search'):
            search_term = f"%{filters['search']}%"
            query = query.where(
                or_(
                    self._model.title.ilike(search_term),
                    self._model.description.ilike(search_term)
                )
            )

        return query


class ColumnTemplateRepository(BaseRepository[ColumnTemplate, ColumnTemplateCreate, ColumnTemplateUpdate]):
    """Репозиторий для работы с шаблонами колонок."""

    def __init__(self, uow: IUnitOfWork) -> None:
        """Инициализация репозитория колонок."""
        super().__init__(uow)
        self._model = ColumnTemplate
        self._logger = get_logger(__name__)

    async def get_columns_by_project(self, project_id: int) -> List[ColumnTemplate]:
        """Получить все колонки проекта.

        Args:
            project_id: ID проекта

        Returns:
            List[ColumnTemplate]: Список колонок, отсортированных по порядку
        """
        start_time = time.time()
        self._logger.debug(f"Getting columns for project {project_id}")

        try:
            query = (
                select(self._model)
                .where(self._model.project_id == project_id)
                .order_by(self._model.order)
            )
            result = await self.uow.session.execute(query)
            columns = list(result.scalars().all())

            duration = time.time() - start_time
            self._logger.info(f"Retrieved {len(columns)} columns for project {project_id} in {duration:.3f}s")

            return columns
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting columns for project {project_id} in {duration:.3f}s")
            raise

    async def create(self, obj_data: ColumnTemplateCreate) -> ColumnTemplate:
        """Создать новую колонку.

        Args:
            obj_data: Данные для создания колонки

        Returns:
            ColumnTemplate: Созданная колонка
        """
        start_time = time.time()
        self._logger.info(f"Creating new Column in project {obj_data.project_id}")

        try:
            # Определяем следующий порядковый номер
            query = (
                select(func.max(self._model.order))
                .where(self._model.project_id == obj_data.project_id)
            )
            result = await self.uow.session.execute(query)
            max_order = result.scalar_one()
            next_order = (max_order + 1) if max_order is not None else 0

            # Создаем колонку
            data = obj_data.model_dump(exclude_unset=True)
            db_obj = self._model(**data, order=next_order)
            self.uow.session.add(db_obj)
            await self.uow.session.flush()

            duration = time.time() - start_time
            self._logger.info(f"Created Column with ID {db_obj.id} in {duration:.3f}s")

            return db_obj
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error creating Column in {duration:.3f}s")
            raise

    async def reorder_columns(self, project_id: int, column_orders: List[Dict[str, Any]]) -> bool:
        """Изменить порядок колонок.

        Args:
            project_id: ID проекта
            column_orders: Список словарей с id и новым order

        Returns:
            bool: True если успешно
        """
        start_time = time.time()
        self._logger.info(f"Reordering columns in project {project_id}")

        try:
            for item in column_orders:
                stmt = (
                    update(self._model)
                    .where(
                        and_(
                            self._model.id == item['id'],
                            self._model.project_id == project_id
                        )
                    )
                    .values(order=item['order'])
                )
                await self.uow.session.execute(stmt)

            duration = time.time() - start_time
            self._logger.info(f"Reordered {len(column_orders)} columns in {duration:.3f}s")

            return True
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error reordering columns in {duration:.3f}s")
            raise