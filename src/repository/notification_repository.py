from __future__ import annotations

from sqlalchemy import func, select, update

from src.core.uow import IUnitOfWork
from src.model.notification import Notification, NotificationType
from src.repository.base_repository import BaseRepository


class NotificationRepository(BaseRepository[Notification, dict, dict]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Notification

    async def get_by_user_id(self, user_id: int, page: int = 1, limit: int = 20) -> tuple[list[Notification], int, int]:
        query = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        result = await self.uow.session.execute(query)
        items = list(result.scalars().all())

        count_query = select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
        count_result = await self.uow.session.execute(count_query)
        total = count_result.scalar() or 0

        unread_query = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read == False)
        )
        unread_result = await self.uow.session.execute(unread_query)
        unread_count = unread_result.scalar() or 0

        return items, total, unread_count

    async def create_notification(self, user_id: int, type: NotificationType, data: dict) -> Notification:
        notification = Notification(
            user_id=user_id,
            type=type,
            data=data,
        )
        self.uow.session.add(notification)
        await self.uow.session.flush()
        return notification

    async def mark_read(self, notification_id: int, user_id: int) -> Notification | None:
        result = await self.uow.session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        notification = result.scalar_one_or_none()
        if notification:
            notification.read = True
            await self.uow.session.flush()
        return notification

    async def mark_all_read(self, user_id: int) -> int:
        result = await self.uow.session.execute(
            update(Notification).where(Notification.user_id == user_id, Notification.read == False).values(read=True)
        )
        await self.uow.session.flush()
        return result.rowcount
