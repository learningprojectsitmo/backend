from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlencode

# Путь SPA-роута резюме. Фронтенд регистрирует только query-param вариант
# (`paths.app.resume` в `frontend/src/config/paths.ts`), обработчик читает
# `?id=` и `?workspaceId=` через `useSearchParams`.
RESUME_PATH = "/app/resume"


def avatar_version(updated_at: datetime) -> int:
    """Версия фото профиля — микросекунды ``updated_at``.

    Не секунды: картинка отдаётся с ``Cache-Control: max-age=86400``, и при
    повторной загрузке в ту же секунду совпали бы и URL, и ETag — браузер
    показал бы старый аватар. ``updated_at`` пишется ``now()`` (микросекунды),
    поэтому версия меняется на каждой загрузке.
    """
    moment = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=UTC)
    # Считаем от эпохи целыми числами: float от ``timestamp()`` теряет
    # микросекунды на текущих датах и мог бы склеить две близкие загрузки.
    delta = moment - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def build_avatar_url(user_id: int, updated_at: datetime) -> str:
    """Относительный URL фото профиля; версия в query сбрасывает кэш браузера.

    Путь без ``/v1``: фронтенд склеивает его со своим ``API_URL``, которому
    префикс уже известен (в проде это относительный ``/v1``).
    """
    return f"/media/{user_id}/avatar?v={avatar_version(updated_at)}"


def build_resume_url(
    resume_id: int | None,
    *,
    workspace_id: int | None = None,
    project_id: int | None = None,
) -> str:
    """Ссылка на резюме в SPA.

    Раньше здесь отдавался путь `/resume/{id}`, которого в роутере нет: запрос
    уходил в catch-all `not-found`. Ссылка нужна рабочая, поэтому id и
    контекст передаются query-параметрами, как их и читает `routes/app/resume.tsx`.

    `workspace_id` нужен для хлебных крошек и возврата к пространству, поэтому
    подставляется везде, где он известен.
    """
    if not resume_id:
        return ""

    params: dict[str, int] = {"id": resume_id}
    if project_id:
        params["projectId"] = project_id
    if workspace_id:
        params["workspaceId"] = workspace_id

    return f"{RESUME_PATH}?{urlencode(params)}"
