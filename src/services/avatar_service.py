from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from src.util.urls import build_avatar_url

if TYPE_CHECKING:
    from datetime import datetime

    from src.repository.avatar_repository import AvatarRepository


#: Потолок размера файла: 512×512 WebP с фронтенда весит 30–60 КБ, так что
#: 2 МБ — с большим запасом даже для PNG.
MAX_AVATAR_BYTES = 2 * 1024 * 1024

ALLOWED_CONTENT_TYPES = frozenset({"image/webp", "image/png", "image/jpeg"})


class AvatarError(ValueError):
    """Ошибка валидации загружаемого фото."""

    status_code = 400


class AvatarTooLargeError(AvatarError):
    status_code = 413


class AvatarUnsupportedTypeError(AvatarError):
    status_code = 415


def _normalize_content_type(content_type: str | None) -> str:
    # Браузер может прислать `image/webp; charset=...` — параметры отбрасываем.
    return (content_type or "").split(";")[0].strip().lower()


def _matches_signature(content_type: str, data: bytes) -> bool:
    """Проверить magic bytes — ``Content-Type`` от клиента подделывается одной строкой.

    SVG намеренно не поддерживаем: он исполняет скрипты при открытии по прямой ссылке.
    """
    if content_type == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    return False


class AvatarService:
    def __init__(self, avatar_repository: AvatarRepository) -> None:
        self._avatar_repository = avatar_repository

    async def upload(self, user_id: int, content_type: str | None, data: bytes) -> str:
        """Проверить и сохранить фото, вернуть URL для ответа API."""
        if not data:
            raise AvatarError("Файл пустой")

        normalized = _normalize_content_type(content_type)
        if normalized not in ALLOWED_CONTENT_TYPES:
            raise AvatarUnsupportedTypeError("Поддерживаются только WebP, PNG и JPEG")

        if len(data) > MAX_AVATAR_BYTES:
            raise AvatarTooLargeError(f"Файл больше {MAX_AVATAR_BYTES // (1024 * 1024)} МБ")

        if not _matches_signature(normalized, data):
            raise AvatarUnsupportedTypeError("Файл не является изображением заявленного формата")

        updated_at = await self._avatar_repository.upsert(user_id, normalized, data)
        return build_avatar_url(user_id, updated_at)

    async def delete(self, user_id: int) -> bool:
        return await self._avatar_repository.delete(user_id)

    async def get_image(self, user_id: int) -> tuple[bytes, str, datetime] | None:
        avatar = await self._avatar_repository.get_image(user_id)
        if not avatar:
            return None
        return avatar.data, avatar.content_type, avatar.updated_at

    async def get_avatar_url(self, user_id: int) -> str | None:
        meta = await self._avatar_repository.get_meta(user_id)
        if not meta:
            return None
        _, updated_at = meta
        return build_avatar_url(user_id, updated_at)

    async def get_avatar_urls(self, user_ids: Iterable[int]) -> dict[int, str]:
        updated_at_map = await self._avatar_repository.get_updated_at_map(user_ids)
        return {user_id: build_avatar_url(user_id, updated_at) for user_id, updated_at in updated_at_map.items()}
