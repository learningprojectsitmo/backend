from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal


class IUnitOfWork(Protocol):
    session: AsyncSession

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
    async def __aenter__(self) -> IUnitOfWork: ...
    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None: ...


class SqlAlchemyUoW:
    def __init__(self) -> None:
        self.session_factory = AsyncSessionLocal

    async def __aenter__(self) -> SqlAlchemyUoW:
        self.session = self.session_factory()
        return self

    async def __aexit__(self, _exc_type: object, exc: object, tb: object) -> None:  # type: ignore[override]
        if exc:
            await self.session.rollback()
        else:
            try:
                await self.session.commit()
            except Exception:
                # TODO: for some reason this code does not work, I don't get errors on IntegrityError
                await self.session.rollback()
                raise

        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
