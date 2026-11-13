from __future__ import annotations

from sqlalchemy import exists, select

from src.core.uow import IUnitOfWork
from src.model.exam_registration import ExamRegistration, ExamSlot, RegistrationEvent
from src.model.project import Project
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

    async def project(self, workspace_id: int, project_id: int, *, lock: bool = False) -> Project | None:
        query = (
            select(Project)
            .where(Project.id == project_id, Project.workspace_id == workspace_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        return (await self.uow.session.scalars(query)).one_or_none()

    async def registration(
        self, workspace_id: int, exam_id: int, registration_id: int, *, lock: bool = False
    ) -> ExamRegistration | None:
        query = (
            select(ExamRegistration)
            .where(
                ExamRegistration.id == registration_id,
                ExamRegistration.workspace_id == workspace_id,
                ExamRegistration.exam_id == exam_id,
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        return (await self.uow.session.scalars(query)).one_or_none()

    async def active_for_project(self, project_id: int) -> ExamRegistration | None:
        return (
            await self.uow.session.scalars(
                select(ExamRegistration).where(
                    ExamRegistration.project_id == project_id, ExamRegistration.status == "active"
                )
            )
        ).one_or_none()

    async def slots_for_update(self, workspace_id: int, exam_ids: set[int], ids: set[int]) -> dict[int, ExamSlot]:
        query = (
            select(ExamSlot)
            .where(ExamSlot.id.in_(ids), ExamSlot.workspace_id == workspace_id, ExamSlot.exam_id.in_(exam_ids))
            .order_by(ExamSlot.id)
            .with_for_update()
        )
        return {slot.id: slot for slot in await self.uow.session.scalars(query)}

    async def slot_occupied(self, slot_id: int, *, except_registration: int | None) -> bool:
        query = select(ExamRegistration.id).where(
            ExamRegistration.slot_id == slot_id, ExamRegistration.status == "active"
        )
        if except_registration is not None:
            query = query.where(ExamRegistration.id != except_registration)
        return (await self.uow.session.scalar(query.limit(1))) is not None

    async def list_registrations(
        self,
        workspace_id: int,
        exam_id: int,
        *,
        author_id: int | None,
        project_id: int | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> list[ExamRegistration]:
        query = (
            select(ExamRegistration)
            .join(Project, Project.id == ExamRegistration.project_id)
            .where(ExamRegistration.workspace_id == workspace_id, ExamRegistration.exam_id == exam_id)
        )
        if author_id is not None:
            query = query.where(Project.author_id == author_id)
        if project_id is not None:
            query = query.where(ExamRegistration.project_id == project_id)
        if status is not None:
            query = query.where(ExamRegistration.status == status)
        return list(
            await self.uow.session.scalars(
                query.order_by(ExamRegistration.created_at, ExamRegistration.id).limit(limit + 1).offset(offset)
            )
        )

    async def project_author(self, project_id: int) -> int | None:
        return await self.uow.session.scalar(select(Project.author_id).where(Project.id == project_id))

    async def events(self, registration_id: int, *, limit: int, offset: int) -> list[RegistrationEvent]:
        return list(
            await self.uow.session.scalars(
                select(RegistrationEvent)
                .where(RegistrationEvent.registration_id == registration_id)
                .order_by(RegistrationEvent.version)
                .limit(limit + 1)
                .offset(offset)
            )
        )
