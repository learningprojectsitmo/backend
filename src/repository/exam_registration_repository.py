from __future__ import annotations

from sqlalchemy import exists, select

from src.core.uow import IUnitOfWork
from src.model.exam_registration import ExamRegistration, ExamSlot
from src.schema.exam_registration import SlotRead


class ExamRegistrationRepository:
    def __init__(self, uow: IUnitOfWork):
        self.uow = uow

    async def has_slots(self, exam_id: int) -> bool:
        return bool(await self.uow.session.scalar(select(exists().where(ExamSlot.exam_id == exam_id))))

    async def has_registrations(self, exam_id: int) -> bool:
        return bool(await self.uow.session.scalar(select(exists().where(ExamRegistration.exam_id == exam_id))))

    async def all_slots(self, exam_id: int) -> list[ExamSlot]:
        return list(
            (
                await self.uow.session.scalars(
                    select(ExamSlot).where(ExamSlot.exam_id == exam_id).order_by(ExamSlot.starts_at, ExamSlot.id)
                )
            ).all()
        )

    async def list_slots(self, workspace_id: int, exam_id: int, *, limit: int, offset: int) -> list[SlotRead]:
        occupied = exists().where(ExamRegistration.slot_id == ExamSlot.id, ExamRegistration.status == "active")
        query = (
            select(ExamSlot, (~occupied).label("available"))
            .where(ExamSlot.exam_id == exam_id, ExamSlot.workspace_id == workspace_id)
            .order_by(ExamSlot.starts_at, ExamSlot.id)
            .limit(limit + 1)
            .offset(offset)
        )
        return [
            SlotRead(
                id=slot.id,
                workspace_id=slot.workspace_id,
                exam_id=slot.exam_id,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                is_available=available,
            )
            for slot, available in await self.uow.session.execute(query)
        ]
