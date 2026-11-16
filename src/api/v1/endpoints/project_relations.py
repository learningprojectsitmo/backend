"""API endpoint for project relations — verifiable relationship source."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from src.core.container import get_project_relations_service
from src.core.dependencies import get_current_user, setup_audit
from src.core.exceptions import PermissionError
from src.model.user import User
from src.schema.project_relations import ProjectRelationsResponse
from src.services.project_relations import ProjectRelationsService

project_relations_router = APIRouter(
    prefix="/workspaces/{workspace_id}/projects",
    tags=["project-relations"],
    dependencies=[Depends(setup_audit)],
)


@project_relations_router.get(
    "/{project_id}/relations",
    response_model=ProjectRelationsResponse,
)
async def get_project_relations(
    workspace_id: int = Path(ge=1),
    project_id: int = Path(ge=1),
    user: User = Depends(get_current_user),
    service: ProjectRelationsService = Depends(get_project_relations_service),
):
    """Return the verifiable relationship snapshot for a project.

    Access: teacher or admin of the workspace, OR the project manager
    (author).  Other workspace members and outsiders receive 403.
    """
    # Resolve project manager for access check
    manager_id = await service.get_manager_id(project_id, workspace_id=workspace_id)

    # Authorize: manager of the project OR teacher/admin of the workspace
    is_manager = user.id == manager_id
    if not is_manager:
        is_teacher = await service.is_workspace_teacher(
            user.id, workspace_id=workspace_id
        )
        if not is_teacher:
            raise PermissionError(
                "Access denied: must be a teacher/admin of this workspace "
                "or the project manager"
            )

    relations = await service.get_project_relations(
        project_id, workspace_id=workspace_id
    )

    return ProjectRelationsResponse(
        project_id=relations.project_id,
        workspace_id=relations.workspace_id,
        manager_id=relations.manager_id,
        member_ids=relations.member_ids,
        workspace_teacher_ids=relations.workspace_teacher_ids,
    )