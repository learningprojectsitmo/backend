from sqlalchemy import func

from src.model.models import User
from src.repository.base_repository import BaseRepository
from src.schemas import UserCreate, UserUpdate


class UserRepository(BaseRepository):
    def __init__(self, session_factory):
        super().__init__(session_factory)
        self._model = User

    def get_by_id(self, id: int) -> User | None:
        """Получить пользователя по ID"""
        db = self._get_session()
        return db.query(User).filter(User.id == id).first()

    def get_by_email(self, email: str) -> User | None:
        """Получить пользователя по email"""
        db = self._get_session()
        return db.query(User).filter(User.email == email).first()

    def get_multi(self, skip: int = 0, limit: int = 100) -> list[User]:
        """Получить список пользователей с пагинацией"""
        db = self._get_session()
        return db.query(User).offset(skip).limit(limit).all()

    def create(self, obj_data: UserCreate) -> User:
        """Создать нового пользователя"""
        db = self._get_session()

        # Хеширование пароля будет происходить в сервисе
        db_obj = User(
            email=obj_data.email,
            first_name=obj_data.first_name,
            middle_name=obj_data.middle_name,
            last_name=obj_data.last_name,
            isu_number=obj_data.isu_number,
            password_hashed=obj_data.password_string  # Будет заменено на хеш в сервисе
        )

        db.add(db_obj)
        self._commit_session()
        self._refresh_session(db_obj)
        return db_obj

    def update(self, id: int, obj_data: UserUpdate) -> User | None:
        """Обновить пользователя"""
        db = self._get_session()
        db_obj = db.query(User).filter(User.id == id).first()

        if not db_obj:
            return None

        # Обновляем только те поля, которые переданы и не None
        update_data = obj_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)

        self._commit_session()
        self._refresh_session(db_obj)
        return db_obj

    def delete(self, id: int) -> bool:
        """Удалить пользователя"""
        db = self._get_session()
        db_obj = db.query(User).filter(User.id == id).first()

        if not db_obj:
            return False

        db.delete(db_obj)
        self._commit_session()
        return True

    def count(self) -> int:
        """Подсчитать количество пользователей"""
        db = self._get_session()
        return db.query(func.count(User.id)).scalar()

    def authenticate_user(self, email: str, password: str, verify_password_func) -> User | None:
        """Аутентификация пользователя"""
        db_user = self.get_by_email(email)

        if not db_user:
            return None

        if not verify_password_func(password, db_user.password_hashed):
            return None

        return db_user
