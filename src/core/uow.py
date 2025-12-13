from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal


class IUnitOfWork(Protocol):
    session: AsyncSession

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class SqlAlchemyUoW:
    def __init__(self) -> None:
        self.session_factory = AsyncSessionLocal

    async def __aenter__(self) -> SqlAlchemyUoW:
        self.session = self.session_factory()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc:
            await self.session.rollback()
        else:
            await self.session.commit()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
