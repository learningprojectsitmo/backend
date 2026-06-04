from __future__ import annotations

from sqlalchemy import select, update

from src.core.uow import IUnitOfWork
from src.model.workspace_invitation import WorkspaceInvitation
from src.repository.base_repository import BaseRepository


class InvitationRepository(BaseRepository[WorkspaceInvitation, dict, dict]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = WorkspaceInvitation

    async def get_by_workspace(self, workspace_id: int) -> WorkspaceInvitation | None:
        result = await self.uow.session.execute(
            select(WorkspaceInvitation).where(
                WorkspaceInvitation.workspace_id == workspace_id,
                WorkspaceInvitation.is_active.is_(True),
            )
        )
        return result.scalars().first()

    async def get_by_token(self, token: str) -> WorkspaceInvitation | None:
        result = await self.uow.session.execute(select(WorkspaceInvitation).where(WorkspaceInvitation.token == token))
        return result.scalars().first()

    async def get_by_token_with_for_update(self, token: str) -> WorkspaceInvitation | None:
        result = await self.uow.session.execute(
            select(WorkspaceInvitation).where(WorkspaceInvitation.token == token).with_for_update(),
        )
        return result.scalars().first()

    async def deactivate_by_workspace(self, workspace_id: int) -> None:
        await self.uow.session.execute(
            update(WorkspaceInvitation)
            .where(
                WorkspaceInvitation.workspace_id == workspace_id,
                WorkspaceInvitation.is_active.is_(True),
            )
            .values(is_active=False)
        )

    async def increment_use_count(self, invitation_id: int) -> None:
        await self.uow.session.execute(
            update(WorkspaceInvitation)
            .where(WorkspaceInvitation.id == invitation_id)
            .values(use_count=WorkspaceInvitation.use_count + 1)
        )
