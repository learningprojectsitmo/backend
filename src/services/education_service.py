from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.exceptions import PermissionError
from src.model.education import Education
from src.schema.education import EducationCreate, EducationUpdate
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.education_repository import EducationRepository


class EducationService(BaseService[Education, EducationCreate, EducationUpdate]):
    def __init__(self, education_repository: EducationRepository):
        super().__init__(education_repository)
        self._education_repository = education_repository

    async def get_by_user_id(self, user_id: int) -> list[Education]:
        return await self._education_repository.get_by_user_id(user_id)

    async def create_education(self, data: EducationCreate, user_id: int) -> Education:
        if not data.user_id:
            data.user_id = user_id
        return await self._education_repository.create(data)

    async def update_education(self, item_id: int, data: EducationUpdate, user_id: int) -> Education | None:
        item = await self._education_repository.get_by_id(item_id)
        if not item:
            return None
        if item.user_id != user_id:
            raise PermissionError("Only owner can update education")
        return await self._education_repository.update(item_id, data)

    async def delete_education(self, item_id: int, user_id: int) -> bool:
        item = await self._education_repository.get_by_id(item_id)
        if not item:
            return False
        if item.user_id != user_id:
            raise PermissionError("Only owner can delete education")
        return await self._education_repository.delete(item_id)
