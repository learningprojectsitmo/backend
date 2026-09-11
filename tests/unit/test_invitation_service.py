from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from src.model.workspace import WorkSpaceParticipation
from src.model.workspace_invitation import WorkspaceInvitation
from src.services.invitation_service import InvitationService, JoinByLinkResult

# Роли из fixtures (admin=1, teacher=3, member=2)
MEMBER_ROLE_ID = 2
MANAGER_ROLE_ID = 3
CREATOR_ID = 1
WORKSPACE_ID = 10
JOINING_USER_ID = 7
MOCK_WORKSPACE_ID = 1
TOKEN = "token-1"


def _mock_result(existing: WorkSpaceParticipation | None = None) -> Mock:
    result = Mock()
    result.scalars.return_value.first.return_value = existing
    return result


def _make_repository() -> Mock:
    mock_repository = Mock()
    mock_repository.uow.session = Mock()
    mock_repository.uow.session.execute = AsyncMock()
    return mock_repository


def _invitation(link_id: int, workspace_id: int, role_id: int, is_active: bool = True) -> WorkspaceInvitation:
    return WorkspaceInvitation(
        id=link_id,
        workspace_id=workspace_id,
        created_by=CREATOR_ID,
        role_id=role_id,
        is_active=is_active,
    )


class TestInvitationService:
    @pytest.mark.asyncio
    async def test_create_link_should_always_add_new_row(self):
        """Тест должен всегда создавать новую строку ссылки, даже если ссылка уже существует"""
        # given
        mock_repository = _make_repository()
        new_link = _invitation(2, MOCK_WORKSPACE_ID, role_id=MANAGER_ROLE_ID)
        mock_repository.create = AsyncMock(return_value=new_link)
        service = InvitationService(mock_repository)

        # when
        result = await service.create_link(workspace_id=MOCK_WORKSPACE_ID, user_id=CREATOR_ID, role_id=MANAGER_ROLE_ID)

        # then
        assert result == new_link
        assert result.role_id == MANAGER_ROLE_ID
        mock_repository.create.assert_called_once_with(
            {"workspace_id": MOCK_WORKSPACE_ID, "created_by": CREATOR_ID, "role_id": MANAGER_ROLE_ID}
        )

    @pytest.mark.asyncio
    async def test_get_links_should_return_all_links(self):
        """Тест должен вернуть все активные ссылки пространства"""
        # given
        mock_repository = _make_repository()
        links = [
            _invitation(1, MOCK_WORKSPACE_ID, role_id=MEMBER_ROLE_ID),
            _invitation(2, MOCK_WORKSPACE_ID, role_id=MANAGER_ROLE_ID),
        ]
        mock_repository.get_all_by_workspace = AsyncMock(return_value=links)
        service = InvitationService(mock_repository)

        # when
        result = await service.get_links(MOCK_WORKSPACE_ID)

        # then
        assert result == links
        assert len(result) == len(links)
        mock_repository.get_all_by_workspace.assert_called_once_with(MOCK_WORKSPACE_ID)

    @pytest.mark.asyncio
    async def test_revoke_link_should_deactivate_by_token(self):
        """Тест должен деактивировать ссылку по токену"""
        # given
        mock_repository = _make_repository()
        mock_repository.deactivate_by_token = AsyncMock()
        service = InvitationService(mock_repository)

        # when
        await service.revoke_link(TOKEN)

        # then
        mock_repository.deactivate_by_token.assert_called_once_with(TOKEN)

    @pytest.mark.asyncio
    async def test_revoke_all_should_deactivate_by_workspace(self):
        """Тест должен деактивировать все ссылки пространства"""
        # given
        mock_repository = _make_repository()
        mock_repository.deactivate_by_workspace = AsyncMock()
        service = InvitationService(mock_repository)

        # when
        await service.revoke_all(MOCK_WORKSPACE_ID)

        # then
        mock_repository.deactivate_by_workspace.assert_called_once_with(MOCK_WORKSPACE_ID)

    @pytest.mark.asyncio
    async def test_join_by_link_should_add_participation_with_invite_role(self):
        """Тест должен добавить участника с ролью из ссылки"""
        # given
        mock_repository = _make_repository()
        invitation = _invitation(1, WORKSPACE_ID, role_id=MANAGER_ROLE_ID)
        mock_repository.get_by_token_with_for_update = AsyncMock(return_value=invitation)
        mock_repository.increment_use_count = AsyncMock()
        mock_repository.uow.session.execute.return_value = _mock_result(existing=None)

        service = InvitationService(mock_repository)

        # when
        result = await service.join_by_link(TOKEN, user_id=JOINING_USER_ID)

        # then
        assert isinstance(result, JoinByLinkResult)
        assert result.invitation == invitation
        assert result.already_member is False
        added = mock_repository.uow.session.add.call_args.args[0]
        assert isinstance(added, WorkSpaceParticipation)
        assert added.workspace_id == WORKSPACE_ID
        assert added.participant_id == JOINING_USER_ID
        assert added.role_id == MANAGER_ROLE_ID
        mock_repository.increment_use_count.assert_called_once_with(invitation.id)

    @pytest.mark.asyncio
    async def test_join_by_link_should_return_none_for_inactive_link(self):
        """Тест должен вернуть None для неактивной ссылки"""
        # given
        mock_repository = _make_repository()
        invitation = _invitation(1, WORKSPACE_ID, role_id=MEMBER_ROLE_ID, is_active=False)
        mock_repository.get_by_token_with_for_update = AsyncMock(return_value=invitation)
        service = InvitationService(mock_repository)

        # when
        result = await service.join_by_link(TOKEN, user_id=JOINING_USER_ID)

        # then
        assert result is None

    @pytest.mark.asyncio
    async def test_join_by_link_should_not_duplicate_existing_participation(self):
        """Тест не должен добавлять повторное участие, если пользователь уже член пространства"""
        # given
        mock_repository = _make_repository()
        invitation = _invitation(1, WORKSPACE_ID, role_id=MEMBER_ROLE_ID)
        mock_repository.get_by_token_with_for_update = AsyncMock(return_value=invitation)
        existing = WorkSpaceParticipation(
            id=5, workspace_id=WORKSPACE_ID, participant_id=JOINING_USER_ID, role_id=MEMBER_ROLE_ID
        )
        mock_repository.uow.session.execute.return_value = _mock_result(existing=existing)

        service = InvitationService(mock_repository)

        # when
        result = await service.join_by_link(TOKEN, user_id=JOINING_USER_ID)

        # then
        assert isinstance(result, JoinByLinkResult)
        assert result.invitation == invitation
        assert result.already_member is True
        mock_repository.uow.session.add.assert_not_called()
        mock_repository.increment_use_count.assert_not_called()

    @pytest.mark.asyncio
    async def test_join_by_link_should_not_upgrade_role_of_existing_member(self):
        """Тест не должен повышать роль участника, если ссылка предлагает роль выше"""
        # given
        mock_repository = _make_repository()
        invitation = _invitation(1, WORKSPACE_ID, role_id=MANAGER_ROLE_ID)
        mock_repository.get_by_token_with_for_update = AsyncMock(return_value=invitation)
        existing = WorkSpaceParticipation(
            id=8, workspace_id=WORKSPACE_ID, participant_id=JOINING_USER_ID, role_id=MEMBER_ROLE_ID
        )
        mock_repository.uow.session.execute.return_value = _mock_result(existing=existing)

        service = InvitationService(mock_repository)

        # when
        result = await service.join_by_link(TOKEN, user_id=JOINING_USER_ID)

        # then
        assert isinstance(result, JoinByLinkResult)
        assert result.already_member is True
        assert existing.role_id == MEMBER_ROLE_ID
        mock_repository.uow.session.add.assert_not_called()
        mock_repository.increment_use_count.assert_not_called()
