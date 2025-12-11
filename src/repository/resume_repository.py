

from src.model.models import Resume
from src.repository.base_repository import BaseRepository
from src.schemas import ResumeCreate, ResumeUpdate


class ResumeRepository(BaseRepository[Resume, ResumeCreate, ResumeUpdate]):
    def __init__(self, session_factory):
        super().__init__(session_factory)
        self._model = Resume

    def get_by_id(self, id: int) -> Resume | None:
        """Получить резюме по ID"""
        db = self._get_session()
        return db.query(Resume).filter(Resume.id == id).first()

    def get_by_author_id(self, author_id: int) -> list[Resume]:
        """Получить резюме автора"""
        db = self._get_session()
        return db.query(Resume).filter(Resume.author_id == author_id).all()

    def get_multi(self, skip: int = 0, limit: int = 100) -> list[Resume]:
        """Получить список резюме с пагинацией"""
        db = self._get_session()
        return db.query(Resume).offset(skip).limit(limit).all()

    def create(self, obj_data: ResumeCreate) -> Resume:
        """Создать новое резюме"""
        db = self._get_session()
        db_resume = Resume(**obj_data.model_dump())
        db.add(db_resume)
        db.commit()
        db.refresh(db_resume)
        return db_resume

    def update(self, id: int, obj_data: ResumeUpdate) -> Resume | None:
        """Обновить резюме"""
        db = self._get_session()
        db_resume = db.query(Resume).filter(Resume.id == id).first()
        if not db_resume:
            return None

        update_data = obj_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_resume, field, value)

        db.commit()
        db.refresh(db_resume)
        return db_resume

    def delete(self, id: int) -> bool:
        """Удалить резюме"""
        db = self._get_session()
        db_resume = db.query(Resume).filter(Resume.id == id).first()
        if not db_resume:
            return False

        db.delete(db_resume)
        db.commit()
        return True

    def count(self) -> int:
        """Подсчитать количество резюме"""
        db = self._get_session()
        return db.query(Resume).count()
