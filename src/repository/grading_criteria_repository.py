from __future__ import annotations

from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.models import GradingCriteria
from src.repository.base_repository import BaseRepository


class GradingCriteriaRepository(BaseRepository[GradingCriteria, dict, dict]):
    """Репозиторий для работы с критериями оценивания"""

    def __init__(self, uow: IUnitOfWork):
        """Инициализация репозитория

        Args:
            uow: Unit of Work для управления транзакциями
        """
        super().__init__(uow)
        self._model = GradingCriteria

    async def get_by_project_type(self, project_type_id: int) -> list[GradingCriteria]:
        """Получить все критерии для типа проекта

        Args:
            project_type_id: ID типа проекта

        Returns:
            Список критериев, отсортированных по order_index
        """
        self._logger.debug(f"Getting criteria for project_type_id: {project_type_id}")

        result = await self.uow.session.execute(
            select(GradingCriteria)
            .where(GradingCriteria.project_type_id == project_type_id)
            .order_by(GradingCriteria.order_index)
        )
        criteria = list(result.scalars().all())

        self._logger.info(f"Found {len(criteria)} criteria for project_type_id: {project_type_id}")
        return criteria

    async def get_total_max_score(self, project_type_id: int) -> float:
        """Вычислить максимальную сумму баллов для типа проекта

        Args:
            project_type_id: ID типа проекта

        Returns:
            Суммарный максимальный балл с учётом весов
        """
        criteria = await self.get_by_project_type(project_type_id)
        total = sum(c.max_score * c.weight for c in criteria)

        self._logger.info(f"Total max score for project_type_id {project_type_id}: {total}")
        return total

    async def exists_by_name(self, project_type_id: int, name: str) -> bool:
        """Проверить существует ли критерий с таким именем для данного типа проекта

        Args:
            project_type_id: ID типа проекта
            name: Название критерия

        Returns:
            True если критерий существует
        """
        result = await self.uow.session.execute(
            select(GradingCriteria)
            .where(
                GradingCriteria.project_type_id == project_type_id,
                GradingCriteria.name == name
            )
        )
        exists = result.scalar_one_or_none() is not None

        self._logger.debug(f"Criteria '{name}' exists for project_type {project_type_id}: {exists}")
        return exists
