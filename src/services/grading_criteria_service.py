from __future__ import annotations

from fastapi import HTTPException

from src.core.logging_config import get_logger
from src.model.models import GradingCriteria
from src.repository.grading_criteria_repository import GradingCriteriaRepository
from src.schema.grading_criteria import (
    GradingCriteriaCreate,
    GradingCriteriaUpdate,
    GradingCriteriaListResponse,
    GradingCriteriaResponse,
)


class GradingCriteriaService:
    """Сервис для работы с критериями оценивания"""

    def __init__(self, repository: GradingCriteriaRepository):
        """Инициализация сервиса

        Args:
            repository: Репозиторий для работы с критериями
        """
        self.repository = repository
        self._logger = get_logger(self.__class__.__name__)

    async def create_criteria(self, criteria_data: GradingCriteriaCreate) -> GradingCriteria:
        """Создать критерий оценивания

        Args:
            criteria_data: Данные для создания критерия

        Returns:
            Созданный критерий

        Raises:
            HTTPException: Если критерий с таким именем уже существует
        """
        self._logger.info(f"Creating criteria: {criteria_data.name} for project_type: {criteria_data.project_type_id}")

        # Проверка на дубликаты
        exists = await self.repository.exists_by_name(
            criteria_data.project_type_id,
            criteria_data.name
        )
        if exists:
            self._logger.warning(f"Criteria '{criteria_data.name}' already exists")
            raise HTTPException(
                status_code=400,
                detail=f"Criteria with name '{criteria_data.name}' already exists for this project type"
            )

        criteria = await self.repository.create(criteria_data.model_dump())
        self._logger.info(f"Successfully created criteria with ID: {criteria.id}")
        return criteria

    async def get_by_id(self, criteria_id: int) -> GradingCriteria:
        """Получить критерий по ID

        Args:
            criteria_id: ID критерия

        Returns:
            Критерий

        Raises:
            HTTPException: Если критерий не найден
        """
        criteria = await self.repository.get_by_id(criteria_id)
        if not criteria:
            self._logger.warning(f"Criteria with ID {criteria_id} not found")
            raise HTTPException(status_code=404, detail="Criteria not found")

        return criteria

    async def get_by_project_type(
            self,
            project_type_id: int
    ) -> GradingCriteriaListResponse:
        """Получить все критерии для типа проекта

        Args:
            project_type_id: ID типа проекта

        Returns:
            Список критериев с метаданными
        """
        self._logger.info(f"Getting criteria for project_type_id: {project_type_id}")

        criteria = await self.repository.get_by_project_type(project_type_id)
        total_max_score = await self.repository.get_total_max_score(project_type_id)

        return GradingCriteriaListResponse(
            items=[GradingCriteriaResponse.model_validate(c) for c in criteria],
            total=len(criteria),
            project_type_id=project_type_id,
            total_max_score=total_max_score
        )

    async def update_criteria(
            self,
            criteria_id: int,
            criteria_data: GradingCriteriaUpdate
    ) -> GradingCriteria:
        """Обновить критерий

        Args:
            criteria_id: ID критерия
            criteria_data: Новые данные

        Returns:
            Обновлённый критерий

        Raises:
            HTTPException: Если критерий не найден
        """
        self._logger.info(f"Updating criteria with ID: {criteria_id}")

        existing = await self.repository.get_by_id(criteria_id)
        if not existing:
            self._logger.warning(f"Criteria with ID {criteria_id} not found")
            raise HTTPException(status_code=404, detail="Criteria not found")

        updated = await self.repository.update(criteria_id, criteria_data.model_dump(exclude_unset=True))
        self._logger.info(f"Successfully updated criteria with ID: {criteria_id}")
        return updated  # type: ignore[return-value]

    async def delete_criteria(self, criteria_id: int) -> bool:
        """Удалить критерий

        Args:
            criteria_id: ID критерия

        Returns:
            True если удалён

        Raises:
            HTTPException: Если критерий не найден
        """
        self._logger.info(f"Deleting criteria with ID: {criteria_id}")

        existing = await self.repository.get_by_id(criteria_id)
        if not existing:
            self._logger.warning(f"Criteria with ID {criteria_id} not found")
            raise HTTPException(status_code=404, detail="Criteria not found")

        deleted = await self.repository.delete(criteria_id)
        if deleted:
            self._logger.info(f"Successfully deleted criteria with ID: {criteria_id}")
        return deleted

    async def get_total_max_score(self, project_type_id: int) -> float:
        """Получить максимальную сумму баллов для типа проекта

        Args:
            project_type_id: ID типа проекта

        Returns:
            Суммарный максимальный балл
        """
        return await self.repository.get_total_max_score(project_type_id)
