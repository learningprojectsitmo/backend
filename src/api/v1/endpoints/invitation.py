from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.core.container import get_invitation_service, get_workspace_service
from src.core.dependencies import get_current_user
from src.model.user import User
from src.schema.workspace_invitation import (
    InviteLinkCreate,
    InviteLinkListResponse,
    InviteLinkResponse,
    JoinByLinkInput,
    JoinByLinkResponse,
)
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
    """Создать новую ссылку-приглашение"""
    workspace = await workspace_service.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    role_id = link_data.role_id or 2
    invitation = await invitation_service.create_link(workspace_id, current_user.id, role_id)
    url = invitation_service._build_url(invitation.token)

    return InviteLinkResponse(
        token=invitation.token,
        url=url,
        is_active=invitation.is_active,
        use_count=invitation.use_count,
        role_id=invitation.role_id,
        created_at=invitation.created_at,
    )


@invitation_router.get("/workspaces/{workspace_id}/invite-link", response_model=InviteLinkListResponse)
async def get_invite_links(
    workspace_id: int,
    invitation_service: InvitationService = Depends(get_invitation_service),
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    _current_user: User = Depends(get_current_user),
) -> InviteLinkListResponse:
    """Получить все активные ссылки-приглашения"""
    workspace = await workspace_service.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    invitations = await invitation_service.get_links(workspace_id)

    return InviteLinkListResponse(
        links=[
            InviteLinkResponse(
                token=invitation.token,
                url=invitation_service._build_url(invitation.token),
                is_active=invitation.is_active,
                use_count=invitation.use_count,
                role_id=invitation.role_id,
                created_at=invitation.created_at,
            )
            for invitation in invitations
        ]
    )


@invitation_router.delete("/workspaces/{workspace_id}/invite-link/{token}")
async def revoke_invite_link(
    workspace_id: int,
    token: str,
    invitation_service: InvitationService = Depends(get_invitation_service),
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Отозвать конкретную ссылку-приглашение"""
    workspace = await workspace_service.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only workspace author can revoke invite link")

    await invitation_service.revoke_link(token)
    return {"message": "Invite link revoked successfully"}


@invitation_router.delete("/workspaces/{workspace_id}/invite-link")
async def revoke_all_invite_links(
    workspace_id: int,
    invitation_service: InvitationService = Depends(get_invitation_service),
    workspace_service: WorkSpaceService = Depends(get_workspace_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Отозвать все ссылки-приглашения"""
    workspace = await workspace_service.get_workspace_by_id(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only workspace author can revoke invite link")

    await invitation_service.revoke_all(workspace_id)
    return {"message": "All invite links revoked successfully"}


@invitation_router.post("/workspaces/join-by-link", response_model=JoinByLinkResponse)
async def join_by_link(
    join_data: JoinByLinkInput,
    invitation_service: InvitationService = Depends(get_invitation_service),
    current_user: User = Depends(get_current_user),
) -> JoinByLinkResponse:
    """Присоединиться к пространству по ссылке-приглашению"""
    result = await invitation_service.join_by_link(join_data.token, current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Invalid or expired invite link")

    message = (
        "You are already a member of this workspace" if result.already_member else "Successfully joined the workspace"
    )
    return JoinByLinkResponse(
        message=message,
        workspace_id=result.invitation.workspace_id,
        already_member=result.already_member,
    )
