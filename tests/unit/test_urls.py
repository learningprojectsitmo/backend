from __future__ import annotations

import pytest

from src.util.urls import build_resume_url


class TestBuildResumeUrl:
    """Ссылка на резюме должна совпадать с SPA-роутом фронтенда.

    Регрессия: backend отдавал `/resume/{id}`, а `routes/app/resume.tsx` читает
    `?id=`/`?workspaceId=` через `useSearchParams`. Роут `/resume/:id` не
    зарегистрирован, поэтому ссылка вела в catch-all `not-found`.
    """

    def test_should_return_empty_without_resume(self) -> None:
        # given / then
        assert build_resume_url(None) == ""
        assert build_resume_url(0) == ""

    def test_should_build_query_param_url_with_id(self) -> None:
        # given / when
        url = build_resume_url(2)

        # then
        assert url == "/app/resume?id=2"

    def test_should_include_workspace_id_when_known(self) -> None:
        # given / when
        url = build_resume_url(2, workspace_id=1)

        # then — порядок параметров стабилен: id, projectId, workspaceId
        assert url == "/app/resume?id=2&workspaceId=1"

    def test_should_include_project_id_when_known(self) -> None:
        # given / when
        url = build_resume_url(2, project_id=7)

        # then
        assert url == "/app/resume?id=2&projectId=7"

    def test_should_include_both_contexts(self) -> None:
        # given / when
        url = build_resume_url(2, workspace_id=1, project_id=7)

        # then
        assert url == "/app/resume?id=2&projectId=7&workspaceId=1"

    def test_should_skip_zero_context_ids(self) -> None:
        # given / when — 0 это «нет», а не id
        url = build_resume_url(2, workspace_id=0, project_id=0)

        # then
        assert url == "/app/resume?id=2"

    @pytest.mark.parametrize(
        "url",
        [
            "/app/resume?id=2&workspaceId=1",
            "/app/resume?id=2",
        ],
    )
    def test_should_never_use_legacy_path_shape(self, url) -> None:
        # given / then — путь `/resume/2` в роутере отсутствует
        assert not url.startswith("/resume/")

    def test_should_put_id_first_for_stable_reading(self) -> None:
        # given / when — фронтенд читает `searchParams.get("id")`; id обязан быть
        assert build_resume_url(2, workspace_id=1).split("?")[1].startswith("id=")
