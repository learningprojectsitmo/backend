from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class UserAvatar(Base):
    """Фото профиля пользователя, хранится прямо в БД.

    Отдельная таблица, а не колонка в ``user``: ``User`` подгружается на каждом
    аутентифицированном запросе (``get_current_user``), и ``bytea`` в ней тянул
    бы картинку на каждый запрос. Здесь же blob читается только эндпоинтом
    отдачи картинки, а списки берут лишь ``updated_at`` (см. AvatarRepository).

    Хранение в Postgres, а не на диске, выбрано осознанно: ``deploy/scripts/backup.sh``
    делает только ``pg_dump`` — файлы на volume остались бы без бэкапа.
    """

    __tablename__ = "user_avatar"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"UserAvatar(user_id={self.user_id!r}, content_type={self.content_type!r})"
