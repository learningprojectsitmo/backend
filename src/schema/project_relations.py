"""Response schemas for project relations endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectRelationsResponse(BaseModel):
    """Complete snapshot of project relationships at query time."""

    project_id: int = Field(description="Project identifier")
    workspace_id: int = Field(description="Workspace the project belongs to")
    manager_id: int = Field(description="Project author (manager) user ID")
    member_ids: list[int] = Field(
        default_factory=list,
        description="Student/participant user IDs from project_participation",
    )
    workspace_teacher_ids: list[int] = Field(
        default_factory=list,
        description="User IDs with effective teacher or admin role in the workspace",
    )
    contract_version: int = Field(
        default=1,
        description="Schema version for forward compatibility",
    )

    model_config = {"from_attributes": False}
