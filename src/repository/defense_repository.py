from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.core.uow import IUnitOfWork
from src.model.models import DefenseDay, DefenseProjectType, DefenseRegistration, DefenseSlot
from src.repository.base_repository import BaseRepository
from src.schema.defense import DefenseDayCreate, DefenseSlotCreate, ProjectTypeCreate


class DefenseProjectTypeRepository(BaseRepository[DefenseProjectType, ProjectTypeCreate, ProjectTypeCreate]):
    """Репозиторий для типов проектов защиты."""

    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = DefenseProjectType

    async def get_by_name(self, name: str) -> DefenseProjectType | None:
        """Получить тип проекта по имени."""
        result = await self.uow.session.execute(
            select(DefenseProjectType).where(DefenseProjectType.name == name)
        )
        return result.scalars().first()

    async def get_all(self) -> list[DefenseProjectType]:
        """Получить все типы проектов."""
        result = await self.uow.session.execute(
            select(DefenseProjectType).order_by(DefenseProjectType.name)
        )
        return list(result.scalars().all())


class DefenseDayRepository(BaseRepository[DefenseDay, DefenseDayCreate, DefenseDayCreate]):
    """Репозиторий для дней защит."""

    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = DefenseDay

    async def get_paginated(self, skip: int = 0, limit: int = 10) -> list[DefenseDay]:
        """Получить список дней с пагинацией."""
        return await self.get_multi(skip=skip, limit=limit)


class DefenseSlotRepository(BaseRepository[DefenseSlot, DefenseSlotCreate, DefenseSlotCreate]):
    """Репозиторий для работы со слотами защит."""

    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = DefenseSlot

    async def get_by_id(self, slot_id: int) -> DefenseSlot | None:
        """Получить слот по ID с загрузкой связанного типа проекта."""
        result = await self.uow.session.execute(
            select(DefenseSlot)
            .options(selectinload(DefenseSlot.project_type))
            .where(DefenseSlot.id == slot_id)
        )
        return result.scalars().first()

    async def get_paginated(self, skip: int = 0, limit: int = 10) -> list[DefenseSlot]:
        """Получить список слотов с пагинацией."""
        result = await self.uow.session.execute(
            select(DefenseSlot)
            .options(selectinload(DefenseSlot.project_type))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_filtered(
        self,
        skip: int = 0,
        limit: int = 100,
        date: date_type | None = None,
        project_type_id: int | None = None,
    ) -> list[DefenseSlot]:
        """Получить слоты с фильтрами по дате и типу проекта."""
        query = select(DefenseSlot).options(selectinload(DefenseSlot.project_type))

        if date:
            query = query.where(func.date(DefenseSlot.start_at) == date)

        if project_type_id:
            query = query.where(DefenseSlot.project_type_id == project_type_id)

        query = query.offset(skip).limit(limit)
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        date: date_type | None = None,
        project_type_id: int | None = None,
    ) -> int:
        """Подсчитать слоты с фильтрами."""
        query = select(func.count()).select_from(DefenseSlot)

        if date:
            query = query.where(func.date(DefenseSlot.start_at) == date)

        if project_type_id:
            query = query.where(DefenseSlot.project_type_id == project_type_id)

        result = await self.uow.session.execute(query)
        return result.scalar_one()

    async def count_slots_for_day(self, defense_day_id: int) -> int:
        """Число слотов, созданных для данного дня."""
        result = await self.uow.session.execute(
            select(func.count()).select_from(DefenseSlot).where(DefenseSlot.defense_day_id == defense_day_id)
        )
        return result.scalar_one()

    async def get_by_day_and_index(self, defense_day_id: int, slot_index: int) -> DefenseSlot | None:
        """Найти слот по дню и номеру (для проверки дубля)."""
        result = await self.uow.session.execute(
            select(DefenseSlot).where(
                DefenseSlot.defense_day_id == defense_day_id,
                DefenseSlot.slot_index == slot_index,
            )
        )
        return result.scalars().first()

    async def create_slot(
        self,
        *,
        defense_day_id: int,
        slot_index: int,
        start_at: datetime,
        end_at: datetime,
        title: str,
        project_type_id: int,
        location: str | None,
        capacity: int,
    ) -> DefenseSlot:
        """Создать слот с вычисленным временем (30 мин)."""
        slot = DefenseSlot(
            defense_day_id=defense_day_id,
            slot_index=slot_index,
            start_at=start_at,
            end_at=end_at,
            title=title,
            project_type_id=project_type_id,
            location=location,
            capacity=capacity,
        )
        self.uow.session.add(slot)
        await self.uow.session.flush()
        await self.uow.session.refresh(slot, ["project_type"])
        return slot


class DefenseRegistrationRepository:
    """Репозиторий для записей на защиту.

    Используем отдельный класс, так как базовый CRUD нам здесь не так важен,
    а нужна специфичная логика по проверке уникальности и лимитов.
    """

    def __init__(self, uow: IUnitOfWork) -> None:
        self.uow = uow

    async def count_for_slot(self, slot_id: int) -> int:
        """Подсчитать количество записей на конкретный слот."""
        result = await self.uow.session.execute(
            select(func.count()).select_from(DefenseRegistration).where(DefenseRegistration.slot_id == slot_id)
        )
        return result.scalar_one()

    async def get_by_user_and_slot(self, user_id: int, slot_id: int) -> DefenseRegistration | None:
        """Найти запись по пользователю и слоту (для проверки дублей)."""
        result = await self.uow.session.execute(
            select(DefenseRegistration).where(
                DefenseRegistration.user_id == user_id,
                DefenseRegistration.slot_id == slot_id,
            )
        )
        return result.scalars().first()

    async def create(self, slot_id: int, user_id: int) -> DefenseRegistration:
        """Создать новую запись на защиту."""
        registration = DefenseRegistration(slot_id=slot_id, user_id=user_id)
        self.uow.session.add(registration)
        await self.uow.session.flush()
        return registration

    async def list_for_slot(self, slot_id: int) -> Sequence[DefenseRegistration]:
        """Получить все записи на конкретный слот (пригодится позже)."""
        result = await self.uow.session.execute(
            select(DefenseRegistration).where(DefenseRegistration.slot_id == slot_id)
        )
        return result.scalars().all()

