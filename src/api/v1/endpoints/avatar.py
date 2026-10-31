from __future__ import annotations

from datetime import UTC
from email.utils import format_datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from src.core.container import get_avatar_service
from src.services.avatar_service import AvatarService
from src.util.urls import avatar_version

avatar_router = APIRouter(prefix="/media", tags=["media"])


@avatar_router.get("/{user_id}/avatar")
async def get_user_avatar(
    user_id: int,
    if_none_match: str | None = Header(default=None),
    avatar_service: AvatarService = Depends(get_avatar_service),
) -> Response:
    """Публичная отдача фото профиля.

    Без ``get_current_user`` намеренно: ``<img src="...">`` не отправляет
    Bearer-токен (access-токен живёт в памяти фронтенда), поэтому защищённый
    эндпоинт давал бы битые картинки. Отдаётся только само изображение,
    без каких-либо данных профиля.

    URL содержит ``?v=<updated_at>``, так что агрессивный кэш безопасен:
    после замены фото меняется и версия.
    """
    image = await avatar_service.get_image(user_id)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found")

    data, content_type, updated_at = image
    moment = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=UTC)
    etag = f'"{avatar_version(updated_at)}"'
    headers = {
        "ETag": etag,
        "Last-Modified": format_datetime(moment.astimezone(UTC), usegmt=True),
        "Cache-Control": "public, max-age=86400",
        "X-Content-Type-Options": "nosniff",
    }

    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    return Response(content=data, media_type=content_type, headers=headers)
