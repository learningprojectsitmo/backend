from __future__ import annotations

from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.portfolio import Portfolio
from src.repository.base_repository import BaseRepository
from src.schema.portfolio import PortfolioCreate, PortfolioUpdate


class PortfolioRepository(BaseRepository[Portfolio, PortfolioCreate, PortfolioUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Portfolio

    async def get_by_user_id(self, user_id: int) -> list[Portfolio]:
        result = await self.uow.session.execute(
            select(Portfolio).where(Portfolio.user_id == user_id),
        )
        return list(result.scalars().all())
