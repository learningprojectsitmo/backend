from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict


# --- DefenseProjectType ---


class ProjectTypeCreate(BaseModel):
    """Схема для создания типа проекта."""

    name: str
    description: str | None = None


class ProjectTypeFull(BaseModel):
    """Полная схема типа проекта."""

    id: int
    name: str
    description: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectTypeListResponse(BaseModel):
    """Список типов проектов."""

    items: list[ProjectTypeFull]


class ProjectTypeInfo(BaseModel):
    """Краткая информация о типе проекта (для вложения)."""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


# --- DefenseDay ---


class DefenseDayCreate(BaseModel):
    """Схема для создания дня защит."""

    date: date
    max_slots: int
    first_slot_time: time = time(10, 0)


class DefenseDayFull(BaseModel):
    """Полная схема дня защит."""

    id: int
    date: date
    max_slots: int
    first_slot_time: time
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DefenseDayListItem(BaseModel):
    """Элемент списка дней защит."""

    id: int
    date: date
    max_slots: int
    first_slot_time: time

    model_config = ConfigDict(from_attributes=True)


class DefenseDayListResponse(BaseModel):
    """Список дней защит с пагинацией."""

    items: list[DefenseDayListItem]
    total: int
    page: int
    limit: int
    total_pages: int


# --- DefenseSlot (время вычисляется по дню и slot_index) ---


class DefenseSlotCreate(BaseModel):
    """Схема для создания слота: день + номер слота, время вычисляется (30 мин)."""

    defense_day_id: int
    slot_index: int
    title: str
    project_type_id: int
    location: str | None = None
    capacity: int


class DefenseSlotBase(BaseModel):
    """Базовая схема слота защиты (ответ)."""

    title: str
    project_type: ProjectTypeInfo
    start_at: datetime
    end_at: datetime
    location: str | None = None
    capacity: int


class DefenseSlotFull(DefenseSlotBase):
    """Полная схема слота защиты."""

    id: int
    defense_day_id: int
    slot_index: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DefenseRegistrationCreate(BaseModel):
    """Схема для записи пользователя на защиту."""

    slot_id: int


class DefenseRegistrationFull(BaseModel):
    """Полная схема записи на защиту."""

    id: int
    slot_id: int
    user_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DefenseSlotListItem(BaseModel):
    """Элемент списка слотов защит."""

    id: int
    defense_day_id: int
    slot_index: int
    title: str
    project_type: ProjectTypeInfo
    start_at: datetime
    end_at: datetime
    location: str | None = None
    capacity: int

    model_config = ConfigDict(from_attributes=True)


class DefenseSlotListResponse(BaseModel):
    """Список слотов защит с пагинацией."""

    items: list[DefenseSlotListItem]
    total: int
    page: int
    limit: int
    total_pages: int

