from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.container import get_auth_service, get_kanban_service, get_project_service
from src.core.dependencies import get_current_user, permission_required, setup_audit
from src.core.exceptions import PermissionError
from src.model.user import User
from src.schema.project import (
    ApplyRequest,
    InviteRequest,
    MyInvitationListResponse,
    MyProjectListResponse,
    MyResponseListResponse,
    ProjectCreate,
    ProjectFull,
    ProjectListResponse,
    ProjectUpdate,
)
from src.services.auth_service import AuthService
from src.services.kanban_service import KanbanService
from src.services.project_service import ProjectService

project_router = APIRouter(prefix="/projects", tags=["project"], dependencies=[Depends(setup_audit)])

response_router = APIRouter(prefix="/responses", tags=["response"], dependencies=[Depends(setup_audit)])
invitation_router = APIRouter(prefix="/invitations", tags=["invitation"], dependencies=[Depends(setup_audit)])


@project_router.get("/created", response_model=MyProjectListResponse)
async def fetch_my_created_projects(
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> MyProjectListResponse:
    """Получить проекты, созданные текущим пользователем"""
    return await project_service.get_my_created_projects(current_user.id)


@project_router.get("/my", response_model=MyProjectListResponse)
async def fetch_my_projects(
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> MyProjectListResponse:
    """Получить проекты текущего пользователя"""
    return await project_service.get_my_projects(current_user.id)


@project_router.get("/by_ids", response_model=MyProjectListResponse)
async def fetch_projects_by_ids(
    ids: str = Query(..., description="Comma-separated project IDs"),
    project_service: ProjectService = Depends(get_project_service),
    _current_user: User = Depends(get_current_user),
) -> MyProjectListResponse:
    """Получить проекты по списку ID"""
    project_ids = [int(x.strip()) for x in ids.split(",") if x.strip()]
    return await project_service.get_projects_by_ids(project_ids)


@project_router.get("/{project_id}", response_model=ProjectFull)
async def fetch_project(
    project_id: int,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> ProjectFull:
    """Получить проект по ID"""
    project = await project_service.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="There is no project with that id!")

    return ProjectFull.from_orm(project, current_user.id)


@project_router.get("/", response_model=ProjectListResponse)
async def fetch_projects(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество проектов на странице"),
    workspace_id: int | None = Query(None, description="ID пространства для фильтрации"),
    project_service: ProjectService = Depends(get_project_service),
    _current_user: User = Depends(get_current_user),
) -> ProjectListResponse:
    """Получить список проектов с пагинацией"""

    if workspace_id is not None:
        projects, total = await project_service.get_projects_by_workspace(workspace_id, page, limit)
    else:
        projects, total = await project_service.get_projects_paginated(page, limit)

    projects_list = [project_service.to_project_list_item(project) for project in projects]

    total_pages = (total + limit - 1) // limit if total > 0 else 0

    return ProjectListResponse(
        items=projects_list,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@response_router.get("/my", response_model=MyResponseListResponse)
async def fetch_my_responses(
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> MyResponseListResponse:
    """Получить отклики текущего пользователя"""
    return await project_service.get_my_responses(current_user.id)


@invitation_router.get("/my", response_model=MyInvitationListResponse)
async def fetch_my_invitations(
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> MyInvitationListResponse:
    """Получить приглашения текущего пользователя"""
    return await project_service.get_my_invitations(current_user.id)


@response_router.patch("/{response_id}/withdraw")
async def withdraw_response(
    response_id: int,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Отозвать отклик"""
    await project_service.withdraw_response(response_id, current_user.id)
    return {"message": "Response withdrawn successfully"}


@response_router.patch("/{response_id}/confirm-join")
async def confirm_join(
    response_id: int,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Участник подтверждает вступление в проект"""
    await project_service.confirm_join(response_id, current_user.id)
    return {"message": "Joined project successfully"}


@invitation_router.patch("/{invitation_id}/accept")
async def accept_invitation(
    invitation_id: int,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Принять приглашение"""
    await project_service.accept_invitation(invitation_id, current_user.id)
    return {"message": "Invitation accepted successfully"}


@invitation_router.patch("/{invitation_id}/reject")
async def reject_invitation(
    invitation_id: int,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Отклонить приглашение"""
    await project_service.reject_invitation(invitation_id, current_user.id)
    return {"message": "Invitation rejected successfully"}


@project_router.post("/", response_model=ProjectFull)
async def create_project(
    project_data: ProjectCreate,
    project_service: ProjectService = Depends(get_project_service),
    kanban_service: KanbanService = Depends(get_kanban_service),
    current_user: User = Depends(permission_required("project:create")),
    _audit=Depends(setup_audit),
) -> ProjectFull:
    """Создать новый проект"""

    try:
        project = await project_service.create_project(project_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    await kanban_service.create_default_columns(project.id)
    return ProjectFull.from_orm(project, current_user.id)


@project_router.put("/{project_id}", response_model=ProjectFull)
async def update_project(
    project_id: int,
    project_data: ProjectUpdate,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(permission_required("project:update")),
    _audit=Depends(setup_audit),
) -> ProjectFull:
    """Обновить проект (только автор может обновлять)"""

    project = await project_service.update_project(project_id, project_data, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectFull.from_orm(project, current_user.id)


@project_router.post("/{project_id}/apply")
async def apply_for_project(
    project_id: int,
    body: ApplyRequest,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Откликнуться на проект"""
    await project_service.apply_for_project(project_id, current_user.id, body.vacancy_id, body.resume_id)
    return {"message": "Application sent successfully"}


@project_router.post("/{project_id}/invite")
async def invite_to_project(
    project_id: int,
    body: InviteRequest,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(permission_required("project:update")),
) -> dict[str, str]:
    """Пригласить пользователя в проект (только автор)"""
    await project_service.invite_to_project(project_id, current_user.id, body.user_id, body.vacancy_id, body.resume_id)
    return {"message": "Invitation sent successfully"}


@project_router.put("/{project_id}/responses/{response_id}/accept")
async def accept_response(
    project_id: int,
    response_id: int,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(permission_required("project:update")),
    _audit=Depends(setup_audit),
) -> dict[str, str]:
    """Принять отклик (только автор)"""
    await project_service.accept_response(response_id, current_user.id)
    return {"message": "Response accepted successfully"}


@project_router.put("/{project_id}/responses/{response_id}/reject")
async def reject_response(
    project_id: int,
    response_id: int,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(permission_required("project:update")),
    _audit=Depends(setup_audit),
) -> dict[str, str]:
    """Отклонить отклик (только автор)"""
    await project_service.reject_response(response_id, current_user.id)
    return {"message": "Response rejected successfully"}


@project_router.delete("/{project_id}/participants/{user_id}")
async def remove_participant(
    project_id: int,
    user_id: int,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(permission_required("project:update")),
    _audit=Depends(setup_audit),
) -> dict[str, str]:
    """Удалить участника из проекта (только автор)"""
    success = await project_service.remove_participant(project_id, user_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Participant not found")
    return {"message": "Participant removed successfully"}


@project_router.delete("/{project_id}")
async def delete_project(
    project_id: int,
    project_service: ProjectService = Depends(get_project_service),
    current_user: User = Depends(permission_required("project:delete")),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """Удалить проект (только при наличии права project:delete)"""

    permissions = await auth_service.get_all_user_permissions(current_user)
    is_admin = "project:delete" in permissions

    success = await project_service.delete_project(project_id, is_admin=is_admin)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")

    return {"message": "Project deleted successfully"}
