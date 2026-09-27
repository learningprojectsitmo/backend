from __future__ import annotations

from urllib.parse import urlencode

# Путь SPA-роута резюме. Фронтенд регистрирует только query-param вариант
# (`paths.app.resume` в `frontend/src/config/paths.ts`), обработчик читает
# `?id=` и `?workspaceId=` через `useSearchParams`.
RESUME_PATH = "/app/resume"


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
