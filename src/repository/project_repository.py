

from src.model.models import Project
from src.repository.base_repository import BaseRepository
from src.schemas import ProjectCreate, ProjectUpdate


class ProjectRepository(BaseRepository[Project, ProjectCreate, ProjectUpdate]):
    def __init__(self, session_factory):
        super().__init__(session_factory)
        self._model = Project

    def get_by_id(self, id: int) -> Project | None:
        """Получить проект по ID"""
        db = self._get_session()
        return db.query(Project).filter(Project.id == id).first()

    def get_by_author_id(self, author_id: int) -> list[Project]:
        """Получить проекты автора"""
        db = self._get_session()
        return db.query(Project).filter(Project.author_id == author_id).all()

    def get_multi(self, skip: int = 0, limit: int = 100) -> list[Project]:
        """Получить список проектов с пагинацией"""
        db = self._get_session()
        return db.query(Project).offset(skip).limit(limit).all()

    def create(self, obj_data: ProjectCreate) -> Project:
        """Создать новый проект"""
        db = self._get_session()
        db_project = Project(**obj_data.model_dump())
        db.add(db_project)
        db.commit()
        db.refresh(db_project)
        return db_project

    def update(self, id: int, obj_data: ProjectUpdate) -> Project | None:
        """Обновить проект"""
        db = self._get_session()
        db_project = db.query(Project).filter(Project.id == id).first()
        if not db_project:
            return None

        update_data = obj_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_project, field, value)

        db.commit()
        db.refresh(db_project)
        return db_project

    def delete(self, id: int) -> bool:
        """Удалить проект"""
        db = self._get_session()
        db_project = db.query(Project).filter(Project.id == id).first()
        if not db_project:
            return False

        db.delete(db_project)
        db.commit()
        return True

    def count(self) -> int:
        """Подсчитать количество проектов"""
        db = self._get_session()
        return db.query(Project).count()
