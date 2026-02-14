from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from src.model.models import DefenseDay, DefenseProjectType, DefenseRegistration, DefenseSlot
from src.schema.defense import DefenseDayCreate, DefenseSlotCreate, ProjectTypeCreate
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.defense_repository import (
        DefenseDayRepository,
        DefenseProjectTypeRepository,
        DefenseRegistrationRepository,
        DefenseSlotRepository,
    )


def _slot_start_end(day: DefenseDay, slot_index: int) -> tuple[datetime, datetime]:
    """Вычислить start_at и end_at для слота (30 мин)."""
    start_naive = datetime.combine(day.date, day.first_slot_time)
    start_naive = start_naive.replace(tzinfo=timezone.utc)
    start_at = start_naive + timedelta(minutes=slot_index * 30)
    end_at = start_at + timedelta(minutes=30)
    return start_at, end_at


class DefenseService(BaseService[DefenseSlot, DefenseSlotCreate, DefenseSlotCreate]):
    """Сервис для работы с днями защит, слотами и записями на них."""

    def __init__(
        self,
        project_type_repository: "DefenseProjectTypeRepository",
        day_repository: "DefenseDayRepository",
        slot_repository: "DefenseSlotRepository",
        registration_repository: "DefenseRegistrationRepository",
    ):
        super().__init__(slot_repository)
        self._project_type_repository = project_type_repository
        self._day_repository = day_repository
        self._slot_repository = slot_repository
        self._registration_repository = registration_repository

    async def create_project_type(self, type_data: ProjectTypeCreate) -> DefenseProjectType:
        """Создать новый тип проекта."""
        existing = await self._project_type_repository.get_by_name(type_data.name)
        if existing:
            raise ValueError(f"Project type with name '{type_data.name}' already exists")
        return await self._project_type_repository.create(type_data)

    async def get_all_project_types(self) -> list[DefenseProjectType]:
        """Получить все типы проектов."""
        return await self._project_type_repository.get_all()

    async def get_project_type_by_id(self, type_id: int) -> DefenseProjectType | None:
        """Получить тип проекта по ID."""
        return await self._project_type_repository.get_by_id(type_id)

    async def get_day_by_id(self, day_id: int) -> DefenseDay | None:
        """Получить день защит по ID."""
        return await self._day_repository.get_by_id(day_id)

    async def create_day(self, day_data: DefenseDayCreate) -> DefenseDay:
        """Создать день защит (дата + макс. число слотов по 30 мин)."""
        return await self._day_repository.create(day_data)

    async def get_days_paginated(self, page: int = 1, limit: int = 10) -> tuple[list[DefenseDay], int]:
        """Получить дни защит с пагинацией."""
        skip = (page - 1) * limit
        days = await self._day_repository.get_paginated(skip=skip, limit=limit)
        total = await self._day_repository.count()
        return days, total

    async def get_slot_by_id(self, slot_id: int) -> DefenseSlot | None:
        """Получить слот защиты по ID."""
        return await self._slot_repository.get_by_id(slot_id)

    async def create_slot(self, slot_data: DefenseSlotCreate) -> DefenseSlot:
        """Создать слот по дню и номеру; время вычисляется (30 мин)."""
        # Проверка типа проекта
        project_type = await self._project_type_repository.get_by_id(slot_data.project_type_id)
        if not project_type:
            raise ValueError("Project type not found")

        day = await self._day_repository.get_by_id(slot_data.defense_day_id)
        if not day:
            raise ValueError("Defense day not found")

        if slot_data.slot_index < 0 or slot_data.slot_index >= day.max_slots:
            raise ValueError(
                f"slot_index must be in [0, {day.max_slots - 1}], got {slot_data.slot_index}"
            )

        existing = await self._slot_repository.get_by_day_and_index(
            defense_day_id=day.id, slot_index=slot_data.slot_index
        )
        if existing:
            raise ValueError(
                f"Slot with index {slot_data.slot_index} already exists for this day"
            )

        start_at, end_at = _slot_start_end(day, slot_data.slot_index)

        return await self._slot_repository.create_slot(
            defense_day_id=day.id,
            slot_index=slot_data.slot_index,
            start_at=start_at,
            end_at=end_at,
            title=slot_data.title,
            project_type_id=slot_data.project_type_id,
            location=slot_data.location,
            capacity=slot_data.capacity,
        )

    async def get_slots_paginated(
        self,
        page: int = 1,
        limit: int = 10,
        filter_date: date | None = None,
        filter_project_type_id: int | None = None,
    ) -> tuple[list[DefenseSlot], int]:
        """Получить слоты защит с пагинацией и фильтрами (по дате и типу проекта)."""
        skip = (page - 1) * limit
        slots = await self._slot_repository.get_filtered(
            skip=skip,
            limit=limit,
            date=filter_date,
            project_type_id=filter_project_type_id,
        )
        total = await self._slot_repository.count_filtered(
            date=filter_date,
            project_type_id=filter_project_type_id,
        )
        return slots, total

    async def register_user_to_slot(self, user_id: int, slot_id: int) -> DefenseRegistration:
        """Записать пользователя на защиту в указанный слот.

        Бизнес‑правила:
        - слот должен существовать;
        - пользователь не может записаться дважды в один и тот же слот;
        - количество записей не должно превышать capacity слота.
        """
        slot = await self._slot_repository.get_by_id(slot_id)
        if not slot:
            raise ValueError("Defense slot not found")

        existing = await self._registration_repository.get_by_user_and_slot(user_id=user_id, slot_id=slot_id)
        if existing:
            raise ValueError("User is already registered for this defense slot")

        current_count = await self._registration_repository.count_for_slot(slot_id=slot_id)
        if current_count >= slot.capacity:
            raise ValueError("Defense slot is full")

        return await self._registration_repository.create(slot_id=slot_id, user_id=user_id)

