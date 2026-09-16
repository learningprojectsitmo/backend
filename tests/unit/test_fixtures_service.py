from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from src.model.user import User
from src.services.fixtures_service import FIXTURE_USERS, FixtureService


def _make_user(user_id: int, email: str, first_name: str, last_name: str, role_id: int) -> User:
    return User(
        id=user_id,
        email=email,
        first_name=first_name,
        middle_name="",
        last_name=last_name,
        password_hashed="hashed",
        role_id=role_id,
    )


def _make_role(role_id: int, name: str) -> Mock:
    role = Mock()
    role.id = role_id
    role.name = name
    return role


def _build_service(*, existing_emails: set[str] | None = None) -> tuple[FixtureService, Mock, Mock]:
    """Собрать FixtureService с замоканными зависимостями."""
    existing_emails = existing_emails or set()

    # user_service
    user_service = AsyncMock()
    call_counter = {"n": 0}

    async def _get_user_by_email(email: str) -> User | None:
        if email in existing_emails:
            return _make_user(99, email, "existing", "user", 1)
        return None

    user_service.get_user_by_email = AsyncMock(side_effect=_get_user_by_email)

    def _create_side_effect(data):
        call_counter["n"] += 1
        return _make_user(call_counter["n"], data.email, data.first_name, data.last_name or "", data.role_id)

    user_service.create = AsyncMock(side_effect=_create_side_effect)

    # role_service
    role_service = Mock()
    role_repo = AsyncMock()

    roles = {ud["role_name"]: _make_role(idx + 1, ud["role_name"]) for idx, ud in enumerate(FIXTURE_USERS)}
    roles["admin"] = _make_role(0, "admin")

    async def _get_by_name(name: str) -> Mock | None:
        return roles.get(name)

    role_repo.get_by_name = AsyncMock(side_effect=_get_by_name)
    role_repo.uow = Mock()
    role_repo.uow.commit = Mock()
    role_service._repository = role_repo

    # permission_service / workspace_service
    permission_service = AsyncMock()
    workspace_service = AsyncMock()

    service = FixtureService(
        permission_service=permission_service,
        role_service=role_service,
        user_service=user_service,
        workspace_service=workspace_service,
    )

    return service, user_service, role_repo


class TestCreateFixtureUsers:
    @pytest.mark.asyncio
    async def test_should_create_all_three_users_when_none_exist(self):
        # given
        service, user_service, role_repo = _build_service(existing_emails=set())

        # when
        created, already_existed = await service.create_fixture_users()

        # then
        assert len(created) == len(FIXTURE_USERS)
        assert already_existed == []
        assert user_service.create.call_count == len(FIXTURE_USERS)
        role_repo.uow.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_skip_existing_users_and_report_them(self):
        # given — большинство пользователей уже есть, создаётся только один недостающий
        already_existing_emails = {ud["email"] for ud in FIXTURE_USERS[:-1]}
        service, user_service, role_repo = _build_service(existing_emails=already_existing_emails)

        # when
        created, already_existed = await service.create_fixture_users()

        # then
        assert len(created) == 1
        assert created[0].email == FIXTURE_USERS[-1]["email"]
        assert set(already_existed) == already_existing_emails
        assert user_service.create.call_count == 1
        role_repo.uow.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_create_nothing_when_all_exist(self):
        # given
        all_emails = {ud["email"] for ud in FIXTURE_USERS}
        service, user_service, role_repo = _build_service(existing_emails=all_emails)

        # when
        created, already_existed = await service.create_fixture_users()

        # then
        assert created == []
        assert set(already_existed) == all_emails
        user_service.create.assert_not_awaited()
        role_repo.uow.commit.assert_called_once()


class TestCreateUserIfMissing:
    @pytest.mark.asyncio
    async def test_should_return_none_when_email_already_exists(self):
        # given
        service, user_service, _ = _build_service(existing_emails={"taken@example.com"})

        # when
        result = await service._create_user_if_missing(
            email="taken@example.com",
            first_name="Test",
            middle_name="",
            last_name="User",
            password="pwd",
            role_name="member",
        )

        # then
        assert result is None
        user_service.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_create_and_return_user_when_new(self):
        # given
        service, user_service, _ = _build_service()

        # when
        result = await service._create_user_if_missing(
            email="new@example.com",
            first_name="New",
            middle_name="",
            last_name="User",
            password="pwd",
            role_name="member",
        )

        # then
        assert result is not None
        assert result.email == "new@example.com"
        user_service.create.assert_awaited_once()


class TestGetRoleId:
    @pytest.mark.asyncio
    async def test_should_raise_when_role_not_seeded(self):
        # given
        service, _, _ = _build_service()

        # when / then
        with pytest.raises(ValueError, match="not seeded"):
            await service._get_role_id("nonexistent_role")
