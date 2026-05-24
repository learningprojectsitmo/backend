from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.exceptions import PermissionError
from src.model.portfolio import Portfolio
from src.schema.portfolio import PortfolioCreate, PortfolioUpdate
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.portfolio_repository import PortfolioRepository


class PortfolioService(BaseService[Portfolio, PortfolioCreate, PortfolioUpdate]):
    def __init__(self, portfolio_repository: PortfolioRepository):
        super().__init__(portfolio_repository)
        self._portfolio_repository = portfolio_repository

    async def get_by_user_id(self, user_id: int) -> list[Portfolio]:
        return await self._portfolio_repository.get_by_user_id(user_id)

    async def create_portfolio(self, data: PortfolioCreate, user_id: int) -> Portfolio:
        if not data.user_id:
            data.user_id = user_id
        return await self._portfolio_repository.create(data)

    async def update_portfolio(self, item_id: int, data: PortfolioUpdate, user_id: int) -> Portfolio | None:
        item = await self._portfolio_repository.get_by_id(item_id)
        if not item:
            return None
        if item.user_id != user_id:
            raise PermissionError("Only owner can update portfolio")
        return await self._portfolio_repository.update(item_id, data)

    async def delete_portfolio(self, item_id: int, user_id: int) -> bool:
        item = await self._portfolio_repository.get_by_id(item_id)
        if not item:
            return False
        if item.user_id != user_id:
            raise PermissionError("Only owner can delete portfolio")
        return await self._portfolio_repository.delete(item_id)
