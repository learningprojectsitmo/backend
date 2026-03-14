from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Dict, Any, Tuple

from src.core.exceptions import NotFoundError, PermissionError, ValidationError
from src.model.models import Task, TaskStatus, TaskPriority, ColumnTemplate, User, Role
from src.schema.task import (
    TaskCreate, TaskUpdate, TaskStatusUpdate, 
    ColumnTemplateCreate, ColumnTemplateUpdate,
    TaskFilter
)
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.task_repository import TaskRepository, ColumnTemplateRepository
    from src.repository.user_repository import UserRepository
    from src.repository.project_repository import ProjectRepository


class TaskService(BaseService[Task, TaskCreate, TaskUpdate]):
    """Сервис для работы с задачами канбан-доски.
    
    Содержит бизнес-логику:
    - Проверка прав на изменение статуса (бакалавр vs магистр/преподаватель)
    - Создание уведомлений при изменении статуса
    - Фильтрация задач
    - Валидация данных
    """

    def __init__(
        self, 
        task_repository: TaskRepository,
        column_repository: ColumnTemplateRepository,
        user_repository: UserRepository,
        project_repository: ProjectRepository
    ):
        super().__init__(task_repository)
        self._task_repository = task_repository
        self._column_repository = column_repository
        self._user_repository = user_repository
        self._project_repository = project_repository

    # === Основные методы ===

    async def get_tasks_by_project(
        self, 
        project_id: int, 
        filters: Optional[TaskFilter] = None,
        page: int = 1,
        page_size: int = 100
    ) -> Dict[str, Any]:
        """Получить задачи проекта с фильтрацией и пагинацией.
        
        Args:
            project_id: ID проекта
            filters: Фильтры (статус, приоритет, ответственный и т.д.)
            page: Номер страницы
            page_size: Размер страницы
            
        Returns:
            Dict с задачами и метаданными пагинации
        """
        # Проверяем существование проекта
        project = await self._project_repository.get_by_id(project_id)
        if not project:
            raise NotFoundError(f"Project with id {project_id} not found")

        # Применяем фильтры
        filter_dict = filters.model_dump(exclude_unset=True) if filters else {}
        skip = (page - 1) * page_size
        
        tasks = await self._task_repository.get_tasks_by_project(
            project_id=project_id,
            filters=filter_dict,
            skip=skip,
            limit=page_size
        )
        
        total = await self._task_repository.count_by_project(project_id, filter_dict)
        
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        
        return {
            "items": tasks,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }

    async def create_task(self, task_data: TaskCreate, created_by_id: int) -> Task:
        """Создать новую задачу.
        
        Args:
            task_data: Данные задачи
            created_by_id: ID создателя
            
        Returns:
            Созданная задача
        """
        # Проверяем существование проекта
        project = await self._project_repository.get_by_id(task_data.project_id)
        if not project:
            raise NotFoundError(f"Project with id {task_data.project_id} not found")
        
        # Проверяем, что все назначенные пользователи существуют
        if task_data.assignee_ids:
            for user_id in task_data.assignee_ids:
                user = await self._user_repository.get_by_id(user_id)
                if not user:
                    raise NotFoundError(f"User with id {user_id} not found")
        
        # Создаем задачу
        task = await self._task_repository.create(task_data)
        
        # TODO: Создать уведомление для назначенных пользователей
        
        return task

    async def update_task(self, task_id: int, task_data: TaskUpdate, current_user_id: int) -> Task:
        """Обновить задачу.
        
        Args:
            task_id: ID задачи
            task_data: Данные для обновления
            current_user_id: ID текущего пользователя
            
        Returns:
            Обновленная задача
        """
        # Проверяем существование задачи
        task = await self._task_repository.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with id {task_id} not found")
        
        # Проверяем права (только создатель или магистр/преподаватель могут редактировать)
        await self._check_edit_permission(task, current_user_id)
        
        # Проверяем назначенных пользователей
        if task_data.assignee_ids:
            for user_id in task_data.assignee_ids:
                user = await self._user_repository.get_by_id(user_id)
                if not user:
                    raise NotFoundError(f"User with id {user_id} not found")
        
        # Обновляем задачу
        updated_task = await self._task_repository.update(task_id, task_data)
        if not updated_task:
            raise NotFoundError(f"Task with id {task_id} not found")
        
        return updated_task

    async def update_task_status(
        self, 
        task_id: int, 
        status_update: TaskStatusUpdate, 
        current_user_id: int
    ) -> Task:
        """Обновить статус задачи (для drag-and-drop).
        
        Args:
            task_id: ID задачи
            status_update: Новый статус и порядок
            current_user_id: ID пользователя, меняющего статус
            
        Returns:
            Обновленная задача
            
        Raises:
            PermissionError: Если пользователь не может менять статус
        """
        # Проверяем существование задачи
        task = await self._task_repository.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with id {task_id} not found")
        
        # Проверяем права на изменение статуса
        await self._check_status_change_permission(task, status_update.status, current_user_id)
        
        # Получаем следующее значение order (если не указано)
        if status_update.order < 0:
            tasks_in_column = await self._task_repository.get_tasks_by_project(
                project_id=task.project_id,
                filters={"status": status_update.status}
            )
            status_update.order = len(tasks_in_column)
        
        # Обновляем статус
        updated_task = await self._task_repository.update_status(
            task_id, 
            status_update, 
            current_user_id
        )
        
        if not updated_task:
            raise NotFoundError(f"Task with id {task_id} not found")
        
        # TODO: Отправить уведомление преподавателям об изменении статуса
        await self._notify_teachers_about_status_change(
            task=task,
            new_status=status_update.status,
            changed_by_id=current_user_id
        )
        
        return updated_task

    async def delete_task(self, task_id: int, current_user_id: int) -> bool:
        """Удалить задачу.
        
        Args:
            task_id: ID задачи
            current_user_id: ID текущего пользователя
            
        Returns:
            True если успешно
        """
        # Проверяем существование задачи
        task = await self._task_repository.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with id {task_id} not found")
        
        # Проверяем права (только создатель или магистр/преподаватель)
        await self._check_edit_permission(task, current_user_id)
        
        return await self._task_repository.delete(task_id)

    async def reorder_tasks(
        self, 
        project_id: int, 
        status: TaskStatus, 
        task_orders: List[Dict[str, Any]],
        current_user_id: int
    ) -> bool:
        """Изменить порядок задач в колонке.
        
        Args:
            project_id: ID проекта
            status: Статус задач (колонка)
            task_orders: Список {id: task_id, order: новый_порядок}
            current_user_id: ID текущего пользователя
            
        Returns:
            True если успешно
        """
        # Проверяем права (только магистр/преподаватель могут менять порядок)
        user = await self._user_repository.get_by_id(current_user_id)
        if not user:
            raise NotFoundError(f"User with id {current_user_id} not found")
        
        if not self._is_master_or_teacher(user):
            raise PermissionError("Only masters and teachers can reorder tasks")
        
        return await self._task_repository.reorder_tasks(project_id, status, task_orders)

    async def get_task_history(self, task_id: int, current_user_id: int, limit: int = 50) -> List[Any]:
        """Получить историю изменений задачи.
        
        Args:
            task_id: ID задачи
            current_user_id: ID текущего пользователя
            limit: Максимальное количество записей
            
        Returns:
            Список записей истории
        """
        # Проверяем существование задачи
        task = await self._task_repository.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with id {task_id} not found")
        
        # Все участники проекта могут видеть историю
        return await self._task_repository.get_task_history(task_id, limit)

    # === Методы для колонок ===

    async def get_project_columns(self, project_id: int) -> List[ColumnTemplate]:
        """Получить все колонки проекта."""
        return await self._column_repository.get_columns_by_project(project_id)

    async def create_column(
        self, 
        column_data: ColumnTemplateCreate, 
        current_user_id: int
    ) -> ColumnTemplate:
        """Создать новую колонку (только магистр/преподаватель)."""
        # Проверяем права
        await self._check_master_or_teacher_permission(current_user_id)
        
        # Проверяем существование проекта
        project = await self._project_repository.get_by_id(column_data.project_id)
        if not project:
            raise NotFoundError(f"Project with id {column_data.project_id} not found")
        
        return await self._column_repository.create(column_data)

    async def update_column(
        self,
        column_id: int,
        column_data: ColumnTemplateUpdate,
        current_user_id: int
    ) -> ColumnTemplate:
        """Обновить колонку (только магистр/преподаватель)."""
        # Проверяем права
        await self._check_master_or_teacher_permission(current_user_id)
        
        # Проверяем существование колонки
        column = await self._column_repository.get_by_id(column_id)
        if not column:
            raise NotFoundError(f"Column with id {column_id} not found")
        
        updated_column = await self._column_repository.update(column_id, column_data)
        if not updated_column:
            raise NotFoundError(f"Column with id {column_id} not found")
        
        return updated_column

    async def delete_column(self, column_id: int, current_user_id: int) -> bool:
        """Удалить колонку (только магистр/преподаватель)."""
        # Проверяем права
        await self._check_master_or_teacher_permission(current_user_id)
        
        # Проверяем существование колонки
        column = await self._column_repository.get_by_id(column_id)
        if not column:
            raise NotFoundError(f"Column with id {column_id} not found")
        
        return await self._column_repository.delete(column_id)

    async def reorder_columns(
        self,
        project_id: int,
        column_orders: List[Dict[str, Any]],
        current_user_id: int
    ) -> bool:
        """Изменить порядок колонок (только магистр/преподаватель)."""
        # Проверяем права
        await self._check_master_or_teacher_permission(current_user_id)
        
        return await self._column_repository.reorder_columns(project_id, column_orders)

    # === Вспомогательные методы для проверки прав ===

    async def _check_edit_permission(self, task: Task, user_id: int) -> None:
        """Проверить права на редактирование задачи.
        
        Редактировать могут:
        - Создатель задачи
        - Магистры и преподаватели
        """
        user = await self._user_repository.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User with id {user_id} not found")
        
        # Создатель всегда может редактировать
        if task.created_by_id == user_id:
            return
        
        # Магистры и преподаватели тоже могут
        if self._is_master_or_teacher(user):
            return
        
        raise PermissionError("You don't have permission to edit this task")

    async def _check_status_change_permission(
        self, 
        task: Task, 
        new_status: TaskStatus, 
        user_id: int
    ) -> None:
        """Проверить права на изменение статуса задачи.
        
        Правила:
        - Бакалавр: NOT_STARTED -> IN_PROGRESS -> REVIEW
        - Магистр/преподаватель: могут менять на любой статус
        - Только магистр/преподаватель могут менять REVIEW -> DONE
        """
        user = await self._user_repository.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User with id {user_id} not found")
        
        # Магистры и преподаватели могут всё
        if self._is_master_or_teacher(user):
            return
        
        # Бакалавр - проверяем правила
        if not self._is_bachelor(user):
            raise PermissionError("Invalid user role for status change")
        
        # Проверяем, что бакалавр - ответственный за задачу
        assignee_ids = [a.user_id for a in task.assignees]
        if user_id not in assignee_ids:
            raise PermissionError("Only assigned bachelors can change task status")
        
        # Правила для бакалавров
        if task.status == TaskStatus.NOT_STARTED and new_status == TaskStatus.IN_PROGRESS:
            return
        elif task.status == TaskStatus.IN_PROGRESS and new_status == TaskStatus.REVIEW:
            return
        elif task.status == TaskStatus.REVIEW and new_status == TaskStatus.DONE:
            raise PermissionError("Only masters and teachers can move tasks from REVIEW to DONE")
        else:
            raise PermissionError(f"Invalid status transition from {task.status} to {new_status}")

    async def _check_master_or_teacher_permission(self, user_id: int) -> None:
        """Проверить, что пользователь - магистр или преподаватель."""
        user = await self._user_repository.get_by_id(user_id)
        if not user:
            raise NotFoundError(f"User with id {user_id} not found")
        
        if not self._is_master_or_teacher(user):
            raise PermissionError("Only masters and teachers can perform this action")

    def _is_master_or_teacher(self, user: User) -> bool:
        """Проверить, что пользователь - магистр или преподаватель."""
        # если role_id = 2 для master, 3 для teacher, 4 для admin
        return user.role_id in [2, 3, 4] if user else False

    def _is_bachelor(self, user: User) -> bool:
        """Проверить, что пользователь - бакалавр."""
        return user.role_id == 1 if user else False

    # === Уведомления ===

    async def _notify_teachers_about_status_change(
        self,
        task: Task,
        new_status: TaskStatus,
        changed_by_id: int
    ) -> None:
        """Отправить уведомление преподавателям об изменении статуса задачи.
        
        Args:
            task: Задача
            new_status: Новый статус
            changed_by_id: ID пользователя, изменившего статус
        """
        changed_by = await self._user_repository.get_by_id(changed_by_id)
        
        # TODO: Реализовать систему уведомлений
        # Пока просто логируем
        self._logger.info(
            f"STATUS CHANGE: Task '{task.title}' (ID: {task.id}) "
            f"changed from {task.status} to {new_status} "
            f"by {changed_by.first_name} {changed_by.last_name} "
            f"at {datetime.now()}"
        )
        
        # Здесь будет отправка уведомлений:
        # 1. Найти всех преподавателей проекта
        # 2. Создать уведомление в БД
        # 3. Отправить email/telegram/etc.