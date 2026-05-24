from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.exceptions import PermissionError
from src.model.language import Language
from src.schema.language import LanguageCreate, LanguageUpdate
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.language_repository import LanguageRepository


class LanguageService(BaseService[Language, LanguageCreate, LanguageUpdate]):
    def __init__(self, language_repository: LanguageRepository):
        super().__init__(language_repository)
        self._language_repository = language_repository

    async def get_by_user_id(self, user_id: int) -> list[Language]:
        return await self._language_repository.get_by_user_id(user_id)

    async def create_language(self, data: LanguageCreate, user_id: int) -> Language:
        if not data.user_id:
            data.user_id = user_id
        return await self._language_repository.create(data)

    async def update_language(self, item_id: int, data: LanguageUpdate, user_id: int) -> Language | None:
        item = await self._language_repository.get_by_id(item_id)
        if not item:
            return None
        if item.user_id != user_id:
            raise PermissionError("Only owner can update language")
        return await self._language_repository.update(item_id, data)

    async def delete_language(self, item_id: int, user_id: int) -> bool:
        item = await self._language_repository.get_by_id(item_id)
        if not item:
            return False
        if item.user_id != user_id:
            raise PermissionError("Only owner can delete language")
        return await self._language_repository.delete(item_id)
