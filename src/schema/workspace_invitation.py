from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InviteLinkCreate(BaseModel):
    role_id: int | None = None


class InviteLinkResponse(BaseModel):
    token: str
    url: str
    is_active: bool
    use_count: int
    role_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InviteLinkListResponse(BaseModel):
    links: list[InviteLinkResponse]


class JoinByLinkInput(BaseModel):
    token: str


class JoinByLinkResponse(BaseModel):
    message: str
    workspace_id: int
    already_member: bool = False

    model_config = ConfigDict(from_attributes=True)
