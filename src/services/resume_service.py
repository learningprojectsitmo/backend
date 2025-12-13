from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import PermissionError
from src.model.models import Resume
from src.schema.resume import ResumeCreate, ResumeUpdate
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.resume_repository import ResumeRepository


class ResumeService(BaseService[Resume, ResumeCreate, ResumeUpdate]):
    def __init__(self, resume_repository: ResumeRepository):
        super().__init__(resume_repository)
        self._resume_repository = resume_repository

    async def get_resume_by_id(self, resume_id: int) -> Resume | None:
        """Получить резюме по ID"""
        return await self._resume_repository.get_by_id(resume_id)

    async def get_resumes_by_author(self, author_id: int) -> list[Resume]:
        """Получить резюме по автору"""
        return await self._resume_repository.get_by_author_id(author_id)

    async def get_resumes_paginated(self, page: int = 1, limit: int = 10) -> tuple[list[Resume], int]:
        """Получить резюме с пагинацией"""
        skip = (page - 1) * limit
        resumes = await self._resume_repository.get_multi(skip=skip, limit=limit)
        total = await self._resume_repository.count()
        return resumes, total

    async def create_resume(self, resume_data: ResumeCreate, author_id: int) -> Resume:
        """Создать новое резюме"""
        if not resume_data.author_id:
            resume_data.author_id = author_id
        return await self._resume_repository.create(resume_data)

    async def update_resume(self, resume_id: int, resume_data: ResumeUpdate, current_user_id: int) -> Resume | None:
        """Обновить резюме (только автор может обновлять)"""
        resume = await self.get_resume_by_id(resume_id)
        if not resume:
            return None

        if resume.author_id != current_user_id:
            raise PermissionError("Only author can update resume")

        return await self._resume_repository.update(resume_id, resume_data)

    async def delete_resume(self, resume_id: int, current_user_id: int) -> bool:
        """Удалить резюме (только автор может удалять)"""
        resume = await self.get_resume_by_id(resume_id)
        if not resume:
            return False

        if resume.author_id != current_user_id:
            raise PermissionError("Only author can delete resume")

        return await self._resume_repository.delete(resume_id)
