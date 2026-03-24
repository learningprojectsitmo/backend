from __future__ import annotations

import time
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import selectinload

from src.core.logging_config import get_logger
from src.core.uow import IUnitOfWork
from src.model.kanban_models import Column, Subtask, Task, TaskAssignee, TaskHistory
from src.model.models import User
from src.repository.base_repository import BaseRepository
from src.schema.kanban import (
    ColumnCreate,
    ColumnUpdate,
    SubtaskCreate,
    SubtaskUpdate,
    TaskCreate,
    TaskFilter,
    TaskMove,
    TaskUpdate,
)


class KanbanColumnRepository(BaseRepository[Column, ColumnCreate, ColumnUpdate]):
    """Репозиторий для работы с колонками канбан-доски."""

    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Column
        self._logger = get_logger(__name__)

    async def get_columns_by_project(self, project_id: int) -> list[Column]:
        """Получить все колонки проекта с задачами и связанными данными."""
        start_time = time.time()
        self._logger.debug(f"Getting columns for project {project_id}")

        try:
            query = (
                select(self._model)
                .where(self._model.project_id == project_id)
                .options(
                    selectinload(self._model.tasks).selectinload(Task.assignees),
                    selectinload(self._model.tasks).selectinload(Task.created_by),
                    selectinload(self._model.tasks).selectinload(Task.column),
                    selectinload(self._model.tasks).selectinload(Task.subtasks),
                )
                .order_by(self._model.position)
            )

            result = await self.uow.session.execute(query)
            columns = list(result.scalars().all())

            duration = time.time() - start_time
            self._logger.info(f"Retrieved {len(columns)} columns for project {project_id} in {duration:.3f}s")

        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting columns for project {project_id}")
            raise
        else:
            return columns

    async def create(self, obj_data: ColumnCreate) -> Column:
        """Создать новую колонку."""
        start_time = time.time()
        self._logger.info(f"Creating new Column in project {obj_data.project_id}")

        try:
            # Определяем следующую позицию
            query = select(func.max(self._model.position)).where(self._model.project_id == obj_data.project_id)
            result = await self.uow.session.execute(query)
            max_pos = result.scalar_one()
            next_position = (max_pos + 1) if max_pos is not None else 0

            data = obj_data.model_dump(exclude_unset=True)
            db_obj = self._model(**data, position=next_position)
            self.uow.session.add(db_obj)
            await self.uow.session.flush()

            duration = time.time() - start_time
            self._logger.info(f"Created Column with ID {db_obj.id}")

        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error creating Column in {duration:.3f}s")
            raise
        else:
            return db_obj

    async def reorder_columns(self, project_id: int, column_orders: list[dict[str, Any]]) -> bool:
        """Изменить порядок колонок."""
        start_time = time.time()
        self._logger.info(f"Reordering columns in project {project_id}")

        try:
            for item in column_orders:
                stmt = (
                    update(self._model)
                    .where(and_(self._model.id == item["id"], self._model.project_id == project_id))
                    .values(position=item["position"])
                )
                await self.uow.session.execute(stmt)

            duration = time.time() - start_time
            self._logger.info(f"Reordered {len(column_orders)} columns")

        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error reordering columns in {duration:.3f}s")
            raise
        else:
            return True


class KanbanTaskRepository(BaseRepository[Task, TaskCreate, TaskUpdate]):
    """Репозиторий для работы с задачами канбан-доски."""

    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Task
        self._logger = get_logger(__name__)

    #   ========== Базовые методы ==========

    async def get_by_id(self, id: int) -> Task | None:
        """Получить задачу по ID с загрузкой связанных данных."""
        start_time = time.time()
        self._logger.debug(f"Getting Task by ID: {id} with relations")

        try:
            query = (
                select(self._model)
                .where(self._model.id == id)
                .options(
                    selectinload(self._model.assignees),
                    selectinload(self._model.created_by),
                    selectinload(self._model.column),
                    selectinload(self._model.project),
                )
            )
            result = await self.uow.session.execute(query)
            task = result.scalar_one_or_none()

            duration = time.time() - start_time
            if task:
                self._logger.info(f"Retrieved Task with ID {id} in {duration:.3f}s")
            else:
                self._logger.warning(f"Task with ID {id} not found in {duration:.3f}s")

        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting Task with ID {id} in {duration:.3f}s")
            raise
        else:
            return task

    async def create(self, obj_data: TaskCreate, created_by_id: int) -> Task:
        """Создать новую задачу в указанной колонке."""
        start_time = time.time()
        self._logger.info(f"Creating new Task in column {obj_data.column_id}")

        try:
            next_position = await self._get_next_position(obj_data.column_id)
            project_id = await self._get_project_id(obj_data.column_id)
            data = obj_data.model_dump(exclude_unset=True, exclude={"assignee_ids"})

            if "tags" in data and isinstance(data["tags"], list):
                data["tags"] = ",".join(data["tags"])

            db_obj = self._model(**data, position=next_position, created_by_id=created_by_id, project_id=project_id)
            self.uow.session.add(db_obj)
            await self.uow.session.flush()

            if obj_data.assignee_ids:
                users = await self._get_users_by_ids(obj_data.assignee_ids)
                db_obj.assignees = users
                await self.uow.session.flush()

            duration = time.time() - start_time
            self._logger.info(f"Created Task with ID {db_obj.id} in {duration:.3f}s")

            return await self.get_by_id(db_obj.id)
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error creating Task in {duration:.3f}s")
            raise

    async def update(self, id: int, obj_data: TaskUpdate) -> Task | None:
        """Изменить задачу"""
        start_time = time.time()
        self._logger.info(f"Updating Task with ID {id}")

        try:
            db_obj = await self.get_by_id(id)
            if not db_obj:
                duration = time.time() - start_time
                self._logger.warning(f"Task with ID {id} not found for update")
                return None

            data = obj_data.model_dump(exclude_unset=True, exclude={"assignee_ids"})

            if "tags" in data and isinstance(data["tags"], list):
                data["tags"] = ",".join(data["tags"])

            updated_fields = list(data.keys())

            for field, value in data.items():
                setattr(db_obj, field, value)

            if obj_data.assignee_ids is not None:
                users = await self._get_users_by_ids(obj_data.assignee_ids)
                db_obj.assignees = users
                updated_fields.append("assignees")

            await self.uow.session.flush()

            duration = time.time() - start_time
            self._logger.info(f"Updated Task with ID {id} - fields: {updated_fields}")

            return await self.get_by_id(id)
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error updating Task with ID {id} in {duration:.3f}s")
            raise

    async def delete(self, id: int) -> bool:
        """Удалить задачу."""
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
                self._logger.info(f"Deleted Task with ID {id}")
                return True
            else:
                self._logger.warning(f"Task with ID {id} not found for deletion")
                return False
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error deleting Task with ID {id} in {duration:.3f}s")
            raise

    #   ========== Специфические методы для канбан-доски ==========

    async def move_task(self, id: int, move_data: TaskMove, changed_by_id: int) -> Task | None:
        """Переместить задачу в другую колонку или изменить позицию."""
        start_time = time.time()
        self._logger.info(f"Moving Task {id} to column {move_data.column_id} at position {move_data.position}")

        try:
            db_obj = await self.get_by_id(id)
            if not db_obj:
                self._logger.warning(f"Task with ID {id} not found for move")
                return None

            old_column_id = db_obj.column_id

            # Обновляем позиции задач в старой колонке (сдвигаем)
            if old_column_id != move_data.column_id:
                await self._shift_positions(old_column_id, db_obj.position, -1)

            # Обновляем позиции в новой колонке (раздвигаем)
            await self._shift_positions(move_data.column_id, move_data.position, 1)

            # Обновляем саму задачу
            db_obj.column_id = move_data.column_id
            db_obj.position = move_data.position

            # Записываем в историю
            history = TaskHistory(
                task_id=id,
                changed_by_id=changed_by_id,
                old_column_id=old_column_id,
                new_column_id=move_data.column_id,
                change_type="move",
            )
            self.uow.session.add(history)

            await self.uow.session.flush()

            duration = time.time() - start_time
            self._logger.info(f"Moved Task {id} in {duration:.3f}s")

            return await self.get_by_id(id)
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error moving Task {id}")
            raise

    async def reorder_tasks(self, column_id: int, task_orders: list[dict[str, Any]]) -> bool:
        """Изменить порядок задач в колонке."""
        start_time = time.time()
        self._logger.info(f"Reordering tasks in column {column_id}")

        try:
            for item in task_orders:
                stmt = (
                    update(self._model)
                    .where(and_(self._model.id == item["id"], self._model.column_id == column_id))
                    .values(position=item["position"])
                )
                await self.uow.session.execute(stmt)

            duration = time.time() - start_time
            self._logger.info(f"Reordered {len(task_orders)} tasks in {duration:.3f}s")

        except Exception:
            duration = time.time() - start_time
            self._logger.exception("Error reordering tasks")
            raise
        else:
            return True

    async def get_tasks_by_column(self, column_id: int) -> list[Task]:
        """Получить все задачи в конкретной колонке, отсортированные по позиции."""
        start_time = time.time()
        self._logger.debug(f"Getting tasks for column {column_id}")

        try:
            query = select(self._model).where(self._model.column_id == column_id).order_by(self._model.position)
            result = await self.uow.session.execute(query)
            tasks = list(result.scalars().all())

            duration = time.time() - start_time
            self._logger.info(f"Retrieved {len(tasks)} tasks for column {column_id} in {duration:.3f}s")

        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting tasks for column {column_id} in {duration:.3f}s")
            raise
        else:
            return tasks

    async def get_tasks_by_project(self, project_id: int) -> list[Task]:
        """Получить все задачи проекта (без разбивки по колонкам)."""
        start_time = time.time()
        self._logger.debug(f"Getting tasks for project {project_id}")

        try:
            query = (
                select(self._model)
                .where(self._model.project_id == project_id)
                .options(
                    selectinload(self._model.assignees),
                    selectinload(self._model.created_by),
                    selectinload(self._model.column),
                )
                .order_by(self._model.column_id, self._model.position)
            )
            result = await self.uow.session.execute(query)
            tasks = list(result.scalars().all())

            duration = time.time() - start_time
            self._logger.info(f"Retrieved {len(tasks)} tasks for project {project_id} in {duration:.3f}s")

        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting tasks for project {project_id} in {duration:.3f}s")
            raise
        else:
            return tasks

    async def get_task_history(self, task_id: int, limit: int = 50) -> list[TaskHistory]:
        """Получить историю изменений задачи."""
        start_time = time.time()
        self._logger.debug(f"Getting history for Task {task_id}")

        try:
            query = (
                select(TaskHistory)
                .where(TaskHistory.task_id == task_id)
                .options(
                    selectinload(TaskHistory.changed_by),
                    selectinload(TaskHistory.old_column),
                    selectinload(TaskHistory.new_column),
                )
                .order_by(TaskHistory.created_at.desc())
                .limit(limit)
            )
            result = await self.uow.session.execute(query)
            history = list(result.scalars().all())

            duration = time.time() - start_time
            self._logger.info(f"Retrieved {len(history)} history records for Task {task_id} in {duration:.3f}s")

        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting history for Task {task_id} in {duration:.3f}s")
            raise
        else:
            return history

    #   ========== Методы для фильтрации и поиска ==========

    async def filter_tasks(
        self, project_id: int, filters: TaskFilter, page: int, page_size: int
    ) -> tuple[list[Task], int]:
        """Отфильтровать задачи проекта по критериям."""
        start_time = time.time()
        self._logger.debug(f"Filtering tasks for project {project_id} with filters: {filters}")

        try:
            query = (
                select(self._model)
                .where(self._model.project_id == project_id)
                .options(
                    selectinload(self._model.assignees),
                    selectinload(self._model.created_by),
                    selectinload(self._model.column),
                )
            )

            # Применяем фильтры
            if filters.column_id is not None:
                query = query.where(self._model.column_id == filters.column_id)

            if filters.priority is not None:
                query = query.where(self._model.priority == filters.priority)

            if filters.assignee_id is not None:
                query = query.join(TaskAssignee).where(TaskAssignee.user_id == filters.assignee_id)

            if filters.created_by_id is not None:
                query = query.where(self._model.created_by_id == filters.created_by_id)

            if filters.tag is not None:
                query = query.where(self._model.tags.like(f"%{filters.tag}%"))

            if filters.search is not None:
                search_term = f"%{filters.search}%"
                query = query.where(
                    or_(self._model.title.ilike(search_term), self._model.description.ilike(search_term))
                )

            if filters.due_before is not None:
                query = query.where(self._model.due_date <= filters.due_before)

            if filters.due_after is not None:
                query = query.where(self._model.due_date >= filters.due_after)

            # Получаем общее количество
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await self.uow.session.execute(count_query)
            total = total_result.scalar_one()

            # Пагинация
            query = query.offset((page - 1) * page_size).limit(page_size)

            # Сортировка
            query = query.order_by(self._model.position)

            result = await self.uow.session.execute(query)
            tasks = list(result.scalars().all())

            duration = time.time() - start_time
            self._logger.info(
                f"Filtered {len(tasks)} tasks (total {total}) for project {project_id} in {duration:.3f}s"
            )

        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error filtering tasks for project {project_id} in {duration:.3f}s")
            raise
        else:
            return tasks, total

    #   ========== Вспомогательные методы ==========

    async def _get_users_by_ids(self, user_ids: list[int]) -> list[User]:
        """Получить пользователей по списку ID."""
        query = select(User).where(User.id.in_(user_ids))
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def _get_next_position(self, column_id: int) -> int:
        """Получить следующую позицию для задачи в колонке."""
        query = select(func.max(self._model.position)).where(self._model.column_id == column_id)
        result = await self.uow.session.execute(query)
        max_pos = result.scalar_one()
        return (max_pos + 1) if max_pos is not None else 0

    async def _get_project_id(self, column_id: int) -> int:
        """Получить project_id через колонку."""
        query = select(Column.project_id).where(Column.id == column_id)
        result = await self.uow.session.execute(query)
        return result.scalar_one()

    async def _shift_positions(self, column_id: int, from_position: int, delta: int) -> None:
        """Сдвинуть позиции задач в колонке (delta = 1 для раздвижки, -1 для сдвижки)."""
        stmt = (
            update(self._model)
            .where(and_(self._model.column_id == column_id, self._model.position >= from_position))
            .values(position=self._model.position + delta)
        )
        await self.uow.session.execute(stmt)


class KanbanSubtaskRepository(BaseRepository[Subtask, SubtaskCreate, SubtaskUpdate]):
    """Репозиторий для работы с подзадачами канбан-доски"""

    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Subtask
        self._logger = get_logger(__name__)

    async def get_by_id(self, id: int) -> Subtask | None:
        """Получить подзадачу по ID с загрузкой связанных данных"""
        start_time = time.time()
        self._logger.debug(f"Getting Subtask by ID: {id}")

        try:
            query = (
                select(self._model)
                .where(self._model.id == id)
                .options(selectinload(self._model.created_by), selectinload(self._model.task))
            )
            result = await self.uow.session.execute(query)
            subtask = result.scalar_one_or_none()

            duration = time.time() - start_time
            if subtask:
                self._logger.info(f"Retrieved Subtask with ID {id} in {duration:.3f}s")
            else:
                self._logger.warning(f"Subtask with ID {id} not found in {duration:.3f}s")

        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting Subtask with ID {id} in {duration:.3f}s")
            raise
        else:
            return subtask

    async def get_subtasks_by_task(self, task_id: int) -> list[Subtask]:
        """Получить все подзадачи задачи"""
        start_time = time.time()
        self._logger.debug(f"Getting subtasks for task {task_id}")

        try:
            query = (
                select(self._model)
                .where(self._model.task_id == task_id)
                .order_by(self._model.position)
                .options(selectinload(self._model.created_by))
            )
            result = await self.uow.session.execute(query)
            subtasks = list(result.scalars().all())

            duration = time.time() - start_time
            self._logger.info(f"Retrieved {len(subtasks)} subtasks for task {task_id} in {duration:.3f}s")

        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error getting subtasks for task {task_id} in {duration:.3f}s")
            raise
        else:
            return subtasks

    async def create(self, obj_data: SubtaskCreate, created_by_id: int) -> Subtask:
        """Создать новую подзадачу"""
        start_time = time.time()
        self._logger.info(f"Creating new Subtask for task {obj_data.task_id}")

        try:
            # Определяем следующую позицию
            next_position = await self._get_next_position(obj_data.task_id)

            data = obj_data.model_dump(exclude_unset=True)

            db_obj = self._model(**data, position=next_position, created_by_id=created_by_id)
            self.uow.session.add(db_obj)
            await self.uow.session.flush()

            duration = time.time() - start_time
            self._logger.info(f"Created Subtask with ID {db_obj.id} in {duration:.3f}s")

            return await self.get_by_id(db_obj.id)
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error creating Subtask in {duration:.3f}s")
            raise

    async def update(self, id: int, obj_data: SubtaskUpdate) -> Subtask | None:
        """Изменить подзадачу"""
        start_time = time.time()
        self._logger.info(f"Updating Subtask with ID {id}")

        try:
            db_obj = await self.get_by_id(id)
            if not db_obj:
                duration = time.time() - start_time
                self._logger.warning(f"Subtask with ID {id} not found for update")
                return None

            data = obj_data.model_dump(exclude_unset=True)
            updated_fields = list(data.keys())

            for field, value in data.items():
                setattr(db_obj, field, value)

            await self.uow.session.flush()

            duration = time.time() - start_time
            self._logger.info(f"Updated Subtask with ID {id} - fields: {updated_fields}")

            return await self.get_by_id(id)
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error updating Subtask with ID {id} in {duration:.3f}s")
            raise

    async def delete(self, id: int) -> bool:
        """Удалить подзадачу"""
        start_time = time.time()
        self._logger.info(f"Deleting Subtask with ID {id}")

        try:
            stmt = delete(self._model).where(self._model.id == id)
            result = await self.uow.session.execute(stmt)

            duration = time.time() - start_time
            if result.rowcount > 0:
                self._logger.info(f"Deleted Subtask with ID {id}")
                return True
            else:
                self._logger.warning(f"Subtask with ID {id} not found for deletion")
                return False
        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error deleting Subtask with ID {id} in {duration:.3f}s")
            raise

    async def reorder_subtasks(self, task_id: int, subtask_orders: list[dict[str, Any]]) -> bool:
        """Изменить порядок подзадачи"""
        start_time = time.time()
        self._logger.info(f"Reordering subtasks in task {task_id}")

        try:
            for item in subtask_orders:
                stmt = (
                    update(self._model)
                    .where(and_(self._model.id == item["id"], self._model.task_id == task_id))
                    .values(position=item["position"])
                )
                await self.uow.session.execute(stmt)

            duration = time.time() - start_time
            self._logger.info(f"Reordered {len(subtask_orders)} subtasks in {duration:.3f}s")

        except Exception:
            duration = time.time() - start_time
            self._logger.exception(f"Error reordering subtasks in {duration:.3f}s")
            raise
        else:
            return True

    async def _get_next_position(self, task_id: int) -> int:
        """Получить следующую позицию для подзадачи"""
        query = select(func.max(self._model.position)).where(self._model.task_id == task_id)
        result = await self.uow.session.execute(query)
        max_pos = result.scalar_one()
        return (max_pos + 1) if max_pos is not None else 0
