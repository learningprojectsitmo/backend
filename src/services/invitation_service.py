from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from src.core.config import settings
from src.model.workspace import WorkSpaceParticipation
from src.model.workspace_invitation import WorkspaceInvitation
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.invitation_repository import InvitationRepository


@dataclass
class JoinByLinkResult:
    invitation: WorkspaceInvitation
    already_member: bool


class InvitationService(BaseService[WorkspaceInvitation, dict, dict]):
    def __init__(self, invitation_repository: InvitationRepository) -> None:
        super().__init__(invitation_repository)
        self._invitation_repository = invitation_repository

    def _build_url(self, token: str) -> str:
        return f"{settings.FRONTEND_URL}/join?token={token}"

    async def create_link(self, workspace_id: int, user_id: int, role_id: int = 2) -> WorkspaceInvitation:
        invitation = await self._invitation_repository.create(
            {
                "workspace_id": workspace_id,
                "created_by": user_id,
                "role_id": role_id,
            }
        )
        return invitation

    async def get_links(self, workspace_id: int) -> list[WorkspaceInvitation]:
        return await self._invitation_repository.get_all_by_workspace(workspace_id)

    async def get_link(self, workspace_id: int) -> WorkspaceInvitation | None:
        return await self._invitation_repository.get_by_workspace(workspace_id)

    async def revoke_all(self, workspace_id: int) -> None:
        await self._invitation_repository.deactivate_by_workspace(workspace_id)

    async def revoke_link(self, token: str) -> None:
        await self._invitation_repository.deactivate_by_token(token)

    async def join_by_link(self, token: str, user_id: int) -> JoinByLinkResult | None:
        invitation = await self._invitation_repository.get_by_token_with_for_update(token)
        if not invitation or not invitation.is_active:
            return None

        result = await self._invitation_repository.uow.session.execute(
            select(WorkSpaceParticipation).where(
                WorkSpaceParticipation.workspace_id == invitation.workspace_id,
                WorkSpaceParticipation.participant_id == user_id,
            )
        )
        already_member = result.scalars().first()
        if already_member:
            return JoinByLinkResult(invitation=invitation, already_member=True)

        participation = WorkSpaceParticipation(
            workspace_id=invitation.workspace_id,
            participant_id=user_id,
            role_id=invitation.role_id,
        )
        self._invitation_repository.uow.session.add(participation)

        await self._invitation_repository.increment_use_count(invitation.id)

        return JoinByLinkResult(invitation=invitation, already_member=False)
