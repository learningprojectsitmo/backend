from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from src.core.exceptions import NotFoundError, ValidationError
from src.core.logging_config import get_logger
from src.model.kanban_models import Subtask, Task
from src.schema.kanban import (
    ColumnCreate,
    ColumnResponse,
    ColumnUpdate,
    ColumnWithTasksAndSubtasksResponse,
    ProjectBoardResponse,
    SubtaskCreate,
    SubtaskListResponse,
    SubtaskResponse,
    SubtaskUpdate,
    TaskCreate,
    TaskFilter,
    TaskHistoryResponse,
    TaskListResponse,
    TaskMove,
    TaskResponse,
    TaskUpdate,
)
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.kanban_repository import KanbanColumnRepository, KanbanSubtaskRepository, KanbanTaskRepository
    from src.repository.project_repository import ProjectRepository
    from src.repository.user_repository import UserRepository


class KanbanService(BaseService[Task, TaskCreate, TaskUpdate]):
    def __init__(
        self,
        kanban_column_repository: KanbanColumnRepository,
        kanban_task_repository: KanbanTaskRepository,
        kanban_subtask_repository: KanbanSubtaskRepository,
        user_repository: UserRepository,
        project_repository: ProjectRepository,
    ):
        super().__init__(kanban_task_repository)
        self._kanban_column_repository = kanban_column_repository
        self._kanban_task_repository = kanban_task_repository
        self._kanban_subtask_repository = kanban_subtask_repository
        self._user_repository = user_repository
        self._project_repository = project_repository
        self._logger = get_logger(__name__)

    #   === Метод для проектов ===

    async def get_board(self, project_id: int) -> ProjectBoardResponse:
        """Получить полную канбан-доску проекта"""
        project = await self._project_repository.get_by_id(project_id)
        if not project:
            raise NotFoundError(f"Project with id {project_id} not found")

        columns = await self._kanban_column_repository.get_columns_by_project(project_id)

        return ProjectBoardResponse(
            project_id=project.id,
            project_name=project.name,
            columns=[ColumnWithTasksAndSubtasksResponse.model_validate(col) for col in columns],
        )

    #   === Методы для колонок ===

    async def create_column(self, column_data: ColumnCreate) -> ColumnResponse:
        """Создать новую колонку."""
        project = await self._project_repository.get_by_id(column_data.project_id)
        if not project:
            raise NotFoundError(f"Project with id {column_data.project_id} not found")

        column = await self._kanban_column_repository.create(column_data)
        return ColumnResponse.model_validate(column)

    async def update_column(self, column_id: int, column_data: ColumnUpdate) -> ColumnResponse:
        """Обновить колонку."""
        column = await self._kanban_column_repository.get_by_id(column_id)
        if not column:
            raise NotFoundError(f"Column with id {column_id} not found")

        updated_column = await self._kanban_column_repository.update(column_id, column_data)
        if not updated_column:
            raise NotFoundError(f"Column with id {column_id} not found")

        return ColumnResponse.model_validate(updated_column)

    async def delete_column(self, column_id: int) -> bool:
        """Удалить колонку."""
        column = await self._kanban_column_repository.get_by_id(column_id)
        if not column:
            raise NotFoundError(f"Column with id {column_id} not found")

        # TODO: Решить, что делать с задачами в удаляемой колонке
        # Варианты: удалить все задачи, переместить в первую колонку, запретить удаление если есть задачи

        return await self._kanban_column_repository.delete(column_id)

    async def reorder_columns(self, project_id: int, column_orders: list[dict[str, Any]]) -> bool:
        """Изменить порядок колонок."""
        columns = await self._kanban_column_repository.get_columns_by_project(project_id)
        column_ids = {col.id for col in columns}

        for item in column_orders:
            if item["id"] not in column_ids:
                raise NotFoundError(f"Column with id {item['id']} not found in project {project_id}")

        return await self._kanban_column_repository.reorder_columns(project_id, column_orders)

    async def get_project_columns(self, project_id: int) -> list[ColumnResponse]:
        columns = await self._kanban_column_repository.get_columns_by_project(project_id)
        return [ColumnResponse.model_validate(col) for col in columns]

    #   === Методы для задач ===

    async def get_task_by_id(self, task_id: int) -> TaskResponse:
        """Получить задачу по ID."""
        task = await self._kanban_task_repository.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with id {task_id} not found")
        return TaskResponse.model_validate(task)

    async def create_task(self, task_data: TaskCreate, created_by_id: int) -> TaskResponse:
        """Создать новую задачу в указанной колонке"""
        column = await self._kanban_column_repository.get_by_id(task_data.column_id)
        if not column:
            raise NotFoundError(f"Column with id {task_data.column_id} not found")

        if column.wip_limit:
            tasks_in_column = await self._kanban_task_repository.get_tasks_by_column(column.id)
            if len(tasks_in_column) >= column.wip_limit:
                raise ValidationError(f"Column '{column.name}' has reached its WIP limit ({column.wip_limit})")

        if task_data.assignee_ids:
            for user_id in task_data.assignee_ids:
                user = await self._user_repository.get_by_id(user_id)
                if not user:
                    raise NotFoundError(f"User with id {user_id} not found")

        task = await self._kanban_task_repository.create(task_data, created_by_id)

        # TODO: Отправить уведомления
        await self._notify_task_created(task, created_by_id)

        return TaskResponse.model_validate(task)

    async def update_task(self, task_id: int, task_data: TaskUpdate, current_user_id: int) -> TaskResponse:
        """Обновить задачу"""
        task = await self._kanban_task_repository.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with id {task_id} not found")

        if task_data.column_id is not None and task_data.column_id != task.column_id:
            new_column = await self._kanban_column_repository.get_by_id(task_data.column_id)
            if not new_column:
                raise NotFoundError(f"Column with id {task_data.column_id} not found")

        if task_data.assignee_ids:
            for user_id in task_data.assignee_ids:
                user = await self._user_repository.get_by_id(user_id)
                if not user:
                    raise NotFoundError(f"User with id {user_id} not found")

        updated_task = await self._kanban_task_repository.update(task_id, task_data)
        if not updated_task:
            raise NotFoundError(f"Task with id {task_id} not found")

        # TODO: Отправить уведомления об изменениях
        await self._notify_task_updated(task, updated_task, current_user_id)

        return TaskResponse.model_validate(updated_task)

    async def move_task(self, task_id: int, move_data: TaskMove, current_user_id: int) -> TaskResponse:
        """Переместить задачу (drag-and-drop)"""
        task = await self._kanban_task_repository.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with id {task_id} not found")

        target_column = await self._kanban_column_repository.get_by_id(move_data.column_id)
        if not target_column:
            raise NotFoundError(f"Column with id {move_data.column_id} not found")

        if target_column.wip_limit and move_data.column_id != task.column_id:
            tasks_in_column = await self._kanban_task_repository.get_tasks_by_column(target_column.id)
            if len(tasks_in_column) >= target_column.wip_limit:
                raise ValidationError(
                    f"Column '{target_column.name}' has reached its WIP limit ({target_column.wip_limit})"
                )

        moved_task = await self._kanban_task_repository.move_task(task_id, move_data, current_user_id)
        if not moved_task:
            raise NotFoundError(f"Task with id {task_id} not found")

        # TODO: Отправить уведомление о перемещении
        await self._notify_task_moved(task, moved_task, current_user_id)

        return TaskResponse.model_validate(moved_task)

    async def delete_task(self, task_id: int, current_user_id: int) -> bool:
        """Удалить задачу."""
        task = await self._kanban_task_repository.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with id {task_id} not found")

        result = await self._kanban_task_repository.delete(task_id)

        # TODO: Отправить уведомление об удалении
        if result:
            await self._notify_task_deleted(task, current_user_id)

        return result

    async def get_task_history(self, task_id: int, limit: int = 50) -> list[TaskHistoryResponse]:
        """Получить историю изменений задачи."""
        task = await self._kanban_task_repository.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with id {task_id} not found")

        history = await self._kanban_task_repository.get_task_history(task_id, limit)

        return [TaskHistoryResponse.model_validate(h) for h in history]

    #   === Методы для подзадач ===

    async def get_subtask_by_id(self, subtask_id: int) -> SubtaskResponse:
        """Получить подзадачу по ID."""
        subtask = await self._kanban_subtask_repository.get_by_id(subtask_id)
        if not subtask:
            raise NotFoundError(f"Subtask with id {subtask_id} not found")
        return SubtaskResponse.model_validate(subtask)

    async def get_subtasks_by_task(self, task_id: int) -> SubtaskListResponse:
        """Получить все подзадачи задачи."""
        task = await self._kanban_task_repository.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with id {task_id} not found")

        subtasks = await self._kanban_subtask_repository.get_subtasks_by_task(task_id)

        return SubtaskListResponse(items=[SubtaskResponse.model_validate(s) for s in subtasks], total=len(subtasks))

    async def create_subtask(self, subtask_data: SubtaskCreate, created_by_id: int) -> SubtaskResponse:
        """Создать новую подзадачу."""
        task = await self._kanban_task_repository.get_by_id(subtask_data.task_id)
        if not task:
            raise NotFoundError(f"Task with id {subtask_data.task_id} not found")

        subtask = await self._kanban_subtask_repository.create(subtask_data, created_by_id)

        # TODO: Отправить уведомление о создании подзадачи
        await self._notify_subtask_created(subtask, created_by_id)

        return SubtaskResponse.model_validate(subtask)

    async def update_subtask(
        self, subtask_id: int, subtask_data: SubtaskUpdate, current_user_id: int
    ) -> SubtaskResponse:
        """Обновить подзадачу."""
        subtask = await self._kanban_subtask_repository.get_by_id(subtask_id)
        if not subtask:
            raise NotFoundError(f"Subtask with id {subtask_id} not found")

        updated_subtask = await self._kanban_subtask_repository.update(subtask_id, subtask_data)
        if not updated_subtask:
            raise NotFoundError(f"Subtask with id {subtask_id} not found")

        # TODO: Отправить уведомление об обновлении
        await self._notify_subtask_updated(subtask, updated_subtask, current_user_id)

        return SubtaskResponse.model_validate(updated_subtask)

    async def toggle_subtask_completion(self, subtask_id: int, current_user_id: int) -> SubtaskResponse:
        """Переключить статус выполнения подзадачи."""
        subtask = await self._kanban_subtask_repository.get_by_id(subtask_id)
        if not subtask:
            raise NotFoundError(f"Subtask with id {subtask_id} not found")

        updated_subtask = await self._kanban_subtask_repository.update(
            subtask_id, SubtaskUpdate(is_completed=not subtask.is_completed)
        )

        if not updated_subtask:
            raise NotFoundError(f"Subtask with id {subtask_id} not found")

        # TODO: Отправить уведомление об изменении статуса
        await self._notify_subtask_toggled(updated_subtask, current_user_id)

        return SubtaskResponse.model_validate(updated_subtask)

    async def delete_subtask(self, subtask_id: int, current_user_id: int) -> bool:
        """Удалить подзадачу."""
        subtask = await self._kanban_subtask_repository.get_by_id(subtask_id)
        if not subtask:
            raise NotFoundError(f"Subtask with id {subtask_id} not found")

        result = await self._kanban_subtask_repository.delete(subtask_id)

        # TODO: Отправить уведомление об удалении
        if result:
            await self._notify_subtask_deleted(subtask, current_user_id)

        return result

    async def reorder_subtasks(self, task_id: int, subtask_orders: list[dict[str, Any]]) -> bool:
        """Изменить порядок подзадач."""
        task = await self._kanban_task_repository.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with id {task_id} not found")

        existing_subtasks = await self._kanban_subtask_repository.get_subtasks_by_task(task_id)
        existing_ids = {s.id for s in existing_subtasks}

        for item in subtask_orders:
            if item["id"] not in existing_ids:
                raise NotFoundError(f"Subtask with id {item['id']} not found in task {task_id}")

        return await self._kanban_subtask_repository.reorder_subtasks(task_id, subtask_orders)

    #   === Метод для статистики ===

    async def get_project_stats(self, project_id: int) -> dict:
        """Получить статистику по задачам проекта."""
        now = datetime.now(UTC)

        project = await self._project_repository.get_by_id(project_id)
        if not project:
            raise NotFoundError(f"Project with id {project_id} not found")

        # Получаем все задачи проекта
        tasks = await self._kanban_task_repository.get_tasks_by_project(project_id)

        stats = {
            "total": len(tasks),
            "by_column": {},
            "by_priority": {"low": 0, "medium": 0, "high": 0, "urgent": 0},
            "overdue": 0,
            "without_assignee": 0,
        }

        for task in tasks:
            # По колонкам
            column_id = task.column_id
            stats["by_column"][column_id] = stats["by_column"].get(column_id, 0) + 1

            # По приоритетам
            if task.priority:
                stats["by_priority"][task.priority] = stats["by_priority"].get(task.priority, 0) + 1

            # Просроченные
            if task.due_date and task.due_date < now:
                stats["overdue"] += 1

            # Без ответственных
            if not task.assignees:
                stats["without_assignee"] += 1

        # Добавляем названия колонок
        columns = await self._kanban_column_repository.get_columns_by_project(project_id)
        stats["column_names"] = {col.id: col.name for col in columns}

        return stats

    #   === Методы для фильтрации и поиска ===

    async def filter_tasks(
        self, project_id: int, filters: TaskFilter | None = None, page: int = 1, page_size: int = 50
    ) -> TaskListResponse:
        if filters is None:
            filters = TaskFilter()

        project = await self._project_repository.get_by_id(project_id)
        if not project:
            raise NotFoundError(f"Project with id {project_id} not found")

        tasks, total = await self._kanban_task_repository.filter_tasks(project_id, filters, page, page_size)

        return TaskListResponse(
            items=[TaskResponse.model_validate(t) for t in tasks],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
        )

    #   === Уведомления для задач ===

    async def _notify_task_created(self, task: Task, created_by_id: int) -> None:
        """Уведомление о создании задачи."""
        creator = await self._user_repository.get_by_id(created_by_id)
        self._logger.info(
            f"TASK CREATED: '{task.title}' (ID: {task.id}) "
            f"in column {task.column_id} by {creator.first_name} {creator.last_name}"
        )

    async def _notify_task_updated(self, old_task: Task, new_task: Task, updated_by_id: int) -> None:
        """Уведомление об обновлении задачи."""
        updater = await self._user_repository.get_by_id(updated_by_id)
        changes = []
        if old_task.title != new_task.title:
            changes.append("title")
        if old_task.description != new_task.description:
            changes.append("description")
        if old_task.priority != new_task.priority:
            changes.append("priority")
        if old_task.due_date != new_task.due_date:
            changes.append("due_date")

        self._logger.info(
            f"TASK UPDATED: '{new_task.title}' (ID: {new_task.id}) "
            f"changed fields: {changes} by {updater.first_name} {updater.last_name}"
        )

    async def _notify_task_moved(self, old_task: Task, new_task: Task, moved_by_id: int) -> None:
        mover = await self._user_repository.get_by_id(moved_by_id)

        old_column_name = old_task.column.name if old_task.column else "?"
        new_column_name = new_task.column.name if new_task.column else "?"

        self._logger.info(
            f"TASK MOVED: '{new_task.title}' (ID: {new_task.id}) "
            f"from column '{old_column_name}' to column '{new_column_name}' "
            f"by {mover.first_name} {mover.last_name}"
        )

    async def _notify_task_deleted(self, task: Task, deleted_by_id: int) -> None:
        """Уведомление об удалении задачи."""
        deleter = await self._user_repository.get_by_id(deleted_by_id)
        self._logger.info(f"TASK DELETED: '{task.title}' (ID: {task.id}) by {deleter.first_name} {deleter.last_name}")

    #   === Уведомления для подзадач ===

    async def _notify_subtask_created(self, subtask: Subtask, created_by_id: int) -> None:
        """Уведомление о создании подзадачи."""
        creator = await self._user_repository.get_by_id(created_by_id)
        self._logger.info(
            f"SUBTASK CREATED: '{subtask.title}' (ID: {subtask.id}) "
            f"for task {subtask.task_id} by {creator.first_name} {creator.last_name}"
        )

    async def _notify_subtask_updated(self, old_subtask: Subtask, new_subtask: Subtask, updated_by_id: int) -> None:
        """Уведомление об обновлении подзадачи."""
        updater = await self._user_repository.get_by_id(updated_by_id)
        changes = []
        if old_subtask.title != new_subtask.title:
            changes.append("title")
        if old_subtask.is_completed != new_subtask.is_completed:
            changes.append("is_completed")

        self._logger.info(
            f"SUBTASK UPDATED: '{new_subtask.title}' (ID: {new_subtask.id}) "
            f"changed fields: {changes} by {updater.first_name} {updater.last_name}"
        )

    async def _notify_subtask_toggled(self, subtask: Subtask, toggled_by_id: int) -> None:
        """Уведомление о переключении статуса подзадачи."""
        toggler = await self._user_repository.get_by_id(toggled_by_id)
        status = "completed" if subtask.is_completed else "uncompleted"
        self._logger.info(
            f"SUBTASK {status.upper()}: '{subtask.title}' (ID: {subtask.id}) "
            f"by {toggler.first_name} {toggler.last_name}"
        )

    async def _notify_subtask_deleted(self, subtask: Subtask, deleted_by_id: int) -> None:
        """Уведомление об удалении подзадачи."""
        deleter = await self._user_repository.get_by_id(deleted_by_id)
        self._logger.info(
            f"SUBTASK DELETED: '{subtask.title}' (ID: {subtask.id}) by {deleter.first_name} {deleter.last_name}"
        )
