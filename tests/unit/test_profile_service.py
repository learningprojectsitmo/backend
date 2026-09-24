from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from src.model.resume import Resume
from src.model.user import Role, User
from src.services.profile_service import ProfileService


def _user(user_id: int = 1, role: str = "member") -> User:
    user = User(
        id=user_id,
        email=f"user{user_id}@example.com",
        first_name="Иван",
        middle_name="Иванович",
        last_name="Иванов",
        phone="+7 (999) 123-45-67",
        tg_nickname="@ivan",
        vk_nickname="@ivan_vk",
    )
    user.role = Role(id=2, name=role)
    return user


def _resume(resume_id: int, *, is_visible: bool) -> Resume:
    return Resume(
        id=resume_id,
        author_id=1,
        header=f"Резюме {resume_id}",
        is_visible=is_visible,
        has_experience=True,
        views_count=0,
    )


def _make_service(user: User | None) -> tuple[ProfileService, Mock, Mock]:
    user_repo = Mock()
    user_repo.get_by_id_with_role = AsyncMock(return_value=user)

    resume_repo = Mock()
    resume_repo.get_by_author_id = AsyncMock(return_value=[])

    portfolio_repo = Mock()
    portfolio_repo.get_by_user_id = AsyncMock(return_value=[])

    education_repo = Mock()
    education_repo.get_by_user_id = AsyncMock(return_value=[])

    language_repo = Mock()
    language_repo.get_by_user_id = AsyncMock(return_value=[])

    project_repo = Mock()

    service = ProfileService(  # type: ignore[arg-type]
        user_repository=user_repo,
        resume_repository=resume_repo,
        portfolio_repository=portfolio_repo,
        education_repository=education_repo,
        language_repository=language_repo,
        project_repository=project_repo,
    )
    return service, user_repo, resume_repo


class TestPublicProfile:
    """Тесты ProfileService.get_public_profile (публичный профиль другого пользователя)"""

    @pytest.mark.asyncio
    async def test_should_return_only_visible_resumes(self):
        # given
        service, _, resume_repo = _make_service(_user())
        resume_repo.get_by_author_id.return_value = [
            _resume(1, is_visible=True),
            _resume(2, is_visible=False),
            _resume(3, is_visible=True),
        ]

        # when
        result = await service.get_public_profile(1)

        # then
        assert [r.id for r in result.resumes] == [1, 3]
        resume_repo.get_by_author_id.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_should_map_user_fields(self):
        # given
        target_user_id = 7
        service, _, _ = _make_service(_user(user_id=target_user_id, role="teacher"))

        # when
        result = await service.get_public_profile(target_user_id)

        # then
        assert result.id == target_user_id
        assert result.first_name == "Иван"
        assert result.last_name == "Иванов"
        assert result.role == "teacher"
        assert result.tg_nickname == "@ivan"

    @pytest.mark.asyncio
    async def test_should_raise_value_error_when_user_not_found(self):
        # given
        unknown_user_id = 404
        service, _, _ = _make_service(None)

        # when / then
        with pytest.raises(ValueError, match="User not found"):
            await service.get_public_profile(unknown_user_id)
