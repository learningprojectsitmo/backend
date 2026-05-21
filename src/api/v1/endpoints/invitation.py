from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.core.container import get_invitation_service, get_workspace_service
from src.core.dependencies import get_current_user
from src.model.user import User
from src.schema.workspace_invitation import InviteLinkCreate, InviteLinkResponse, JoinByLinkInput, JoinByLinkResponse
from src.services.invitation_service import InvitationService
from src.services.workspace_service import WorkSpaceService

invitation_router = APIRouter(tags=["invitation"])


@invitation_router.post("/workspaces/{workspace_id}/invite-link", response_model=InviteLinkResponse)
async def create_invite_link(
    workspace_id: int,
    link_data: InviteLinkCreate,
    invitation_service: InvitationService = Depends(get_invitation_service),
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    current_user: User = Depends(get_current_user),
) -> InviteLinkResponse:
    """Создать или получить существующую ссылку-приглашение"""
    workspace = await workspace_service.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    role_id = link_data.role_id or 2
    invitation = await invitation_service.get_or_create_link(workspace_id, current_user.id, role_id)
    url = invitation_service._build_url(invitation.token)

    return InviteLinkResponse(
        token=invitation.token,
        url=url,
        is_active=invitation.is_active,
        use_count=invitation.use_count,
        role_id=invitation.role_id,
        created_at=invitation.created_at,
    )


@invitation_router.get("/workspaces/{workspace_id}/invite-link", response_model=InviteLinkResponse)
async def get_invite_link(
    workspace_id: int,
    invitation_service: InvitationService = Depends(get_invitation_service),
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    _current_user: User = Depends(get_current_user),
) -> InviteLinkResponse:
    """Получить текущую ссылку-приглашение"""
    workspace = await workspace_service.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    invitation = await invitation_service.get_link(workspace_id)
    if not invitation:
        raise HTTPException(status_code=404, detail="No active invite link found")

    url = invitation_service._build_url(invitation.token)
    return InviteLinkResponse(
        token=invitation.token,
        url=url,
        is_active=invitation.is_active,
        use_count=invitation.use_count,
        role_id=invitation.role_id,
        created_at=invitation.created_at,
    )


@invitation_router.delete("/workspaces/{workspace_id}/invite-link")
async def revoke_invite_link(
    workspace_id: int,
    invitation_service: InvitationService = Depends(get_invitation_service),
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Отозвать ссылку-приглашение"""
    workspace = await workspace_service.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only workspace author can revoke invite link")

    await invitation_service.revoke_link(workspace_id)
    return {"message": "Invite link revoked successfully"}


@invitation_router.post("/workspaces/join-by-link", response_model=JoinByLinkResponse)
async def join_by_link(
    join_data: JoinByLinkInput,
    invitation_service: InvitationService = Depends(get_invitation_service),
    current_user: User = Depends(get_current_user),
) -> JoinByLinkResponse:
    """Присоединиться к пространству по ссылке-приглашению"""
    invitation = await invitation_service.join_by_link(join_data.token, current_user.id)
    if not invitation:
        raise HTTPException(status_code=404, detail="Invalid or expired invite link")

    return JoinByLinkResponse(message="Successfully joined the workspace", workspace_id=invitation.workspace_id)
