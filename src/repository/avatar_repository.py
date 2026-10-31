from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.core.uow import IUnitOfWork
from src.model.user_avatar import UserAvatar


class AvatarRepository:
    """Доступ к фото профиля.

    Ни один метод, кроме :meth:`get_image`, не выбирает колонку ``data``:
    в списках участников нужна только метка обновления, иначе каждый список
    тянул бы из БД все картинки.
    """

    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def get_meta(self, user_id: int) -> tuple[str, datetime] | None:
        """Вернуть (content_type, updated_at) без чтения самого изображения."""
        result = await self._uow.session.execute(
            select(UserAvatar.content_type, UserAvatar.updated_at).where(UserAvatar.user_id == user_id)
        )
        row = result.one_or_none()
        return (row[0], row[1]) if row else None

    async def get_image(self, user_id: int) -> UserAvatar | None:
        """Вернуть запись целиком, включая ``data`` (только для отдачи картинки)."""
        result = await self._uow.session.execute(
            select(UserAvatar).where(UserAvatar.user_id == user_id),
        )
        return result.scalar_one_or_none()

    async def upsert(self, user_id: int, content_type: str, data: bytes) -> datetime:
        """Создать или заменить фото одним запросом (ON CONFLICT DO UPDATE)."""
        stmt = (
            pg_insert(UserAvatar)
            .values(user_id=user_id, content_type=content_type, data=data)
            .on_conflict_do_update(
                index_elements=[UserAvatar.user_id],
                set_={
                    "content_type": content_type,
                    "data": data,
                    # ORM-овый onupdate здесь не срабатывает — ставим явно.
                    "updated_at": func.now(),
                },
            )
            .returning(UserAvatar.updated_at)
        )
        result = await self._uow.session.execute(stmt)
        return result.scalar_one()

    async def delete(self, user_id: int) -> bool:
        result = await self._uow.session.execute(
            delete(UserAvatar).where(UserAvatar.user_id == user_id),
        )
        return bool(result.rowcount)

    async def get_updated_at_map(self, user_ids: Iterable[int]) -> dict[int, datetime]:
        """Метки обновления для набора пользователей — наполнение ``avatar_url`` в списках."""
        ids = list(user_ids)
        if not ids:
            return {}

        result = await self._uow.session.execute(
            select(UserAvatar.user_id, UserAvatar.updated_at).where(UserAvatar.user_id.in_(ids))
        )
        return {row[0]: row[1] for row in result.all()}
