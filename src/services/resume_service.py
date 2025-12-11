
from sqlalchemy.orm import Session

from schemas import ResumeCreate, ResumeUpdate
from src.model.models import Resume
from src.repository.resume_repository import ResumeRepository
from src.services.base_service import BaseService


class ResumeService(BaseService[Resume, ResumeCreate, ResumeUpdate]):
    def __init__(self, resume_repository: ResumeRepository, db_session: Session):
        super().__init__(resume_repository)
        self._resume_repository = resume_repository
        self._db_session = db_session

    def get_resume_by_id(self, resume_id: int) -> Resume | None:
        """Получить резюме по ID"""
        return self._resume_repository.get_by_id(resume_id)

    def get_resumes_by_author(self, author_id: int) -> list[Resume]:
        """Получить резюме автора"""
        return self._resume_repository.get_by_author_id(author_id)

    def get_resumes_paginated(self, page: int = 1, limit: int = 10) -> tuple[list[Resume], int]:
        """Получить резюме с пагинацией"""
        skip = (page - 1) * limit
        resumes = self._resume_repository.get_multi(skip=skip, limit=limit)
        total = self._resume_repository.count()
        return resumes, total

    def create_resume(self, resume_data: ResumeCreate, author_id: int) -> Resume:
        """Создать новое резюме"""
        if not resume_data.author_id:
            resume_data.author_id = author_id
        return self._resume_repository.create(resume_data)

    def update_resume(self, resume_id: int, resume_data: ResumeUpdate, current_user_id: int) -> Resume | None:
        """Обновить резюме (только автор может обновлять)"""
        resume = self.get_resume_by_id(resume_id)
        if not resume:
            return None

        if resume.author_id != current_user_id:
            raise PermissionError("Только автор резюме может его обновлять")

        return self._resume_repository.update(resume_id, resume_data)

    def delete_resume(self, resume_id: int, current_user_id: int) -> bool:
        """Удалить резюме (только автор может удалять)"""
        resume = self.get_resume_by_id(resume_id)
        if not resume:
            return False

        if resume.author_id != current_user_id:
            raise PermissionError("Только автор резюме может его удалять")

        return self._resume_repository.delete(resume_id)
