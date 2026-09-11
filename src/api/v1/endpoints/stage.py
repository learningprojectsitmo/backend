from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from src.core.container import get_stage_service
from src.core.dependencies import get_current_user, permission_required, setup_audit
from src.core.exceptions import BaseAppException
from src.model.user import User
from src.schema.project import ProjectFull
from src.schema.stage import (
    ProjectStageCreate,
    ProjectStageUpdate,
    ProjectTypeCreate,
    ProjectTypeFull,
    ProjectTypeUpdate,
    RejectStageRequest,
    StageHistoryResponse,
)
from src.services.stage_service import ProjectStageService

type_router = APIRouter(prefix="/project-types", tags=["project-type"], dependencies=[Depends(setup_audit)])
stage_router = APIRouter(prefix="/projects/stages", tags=["project-stage"], dependencies=[Depends(setup_audit)])


def _resolve_error(e: BaseAppException) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.detail)


@type_router.get("/", response_model=list[ProjectTypeFull])
async def list_project_types(
    workspace_id: int | None = None,
    stage_service: ProjectStageService = Depends(get_stage_service),
    _current_user: User = Depends(get_current_user),
) -> list[ProjectTypeFull]:
    """Получить список типов проектов с этапами (для пространства — по workspace_id)"""
    return await stage_service.list_project_types(workspace_id)


@type_router.get("/{type_id}", response_model=ProjectTypeFull)
async def get_project_type(
    type_id: int,
    stage_service: ProjectStageService = Depends(get_stage_service),
    _current_user: User = Depends(get_current_user),
) -> ProjectTypeFull:
    """Получить тип проекта по ID"""
    try:
        return await stage_service.get_project_type(type_id)
    except BaseAppException as e:
        raise _resolve_error(e) from e


@type_router.post("/", response_model=ProjectTypeFull)
async def create_project_type(
    data: ProjectTypeCreate,
    workspace_id: int | None = Query(None, description="ID пространства, которому принадлежит тип"),
    stage_service: ProjectStageService = Depends(get_stage_service),
    current_user: User = Depends(permission_required("workspace:update")),
) -> ProjectTypeFull:
    """Создать тип проекта (автор/админ/преподаватель пространства)"""
    data.workspace_id = data.workspace_id or workspace_id
    try:
        return await stage_service.create_project_type(data, data.workspace_id, current_user.id)
    except BaseAppException as e:
        raise _resolve_error(e) from e


@type_router.put("/{type_id}", response_model=ProjectTypeFull)
async def update_project_type(
    type_id: int,
    data: ProjectTypeUpdate,
    workspace_id: int | None = Query(None, description="Пространство, к которому привязан тип"),
    stage_service: ProjectStageService = Depends(get_stage_service),
    current_user: User = Depends(permission_required("workspace:update")),
) -> ProjectTypeFull:
    """Обновить тип проекта (админ/преподаватель пространства)"""
    try:
        return await stage_service.update_project_type(type_id, workspace_id, data, current_user.id)
    except BaseAppException as e:
        raise _resolve_error(e) from e


@type_router.delete("/{type_id}")
async def delete_project_type(
    type_id: int,
    workspace_id: int | None = Query(None, description="Пространство, к которому привязан тип"),
    stage_service: ProjectStageService = Depends(get_stage_service),
    current_user: User = Depends(permission_required("workspace:update")),
) -> dict[str, str]:
    """Удалить тип проекта (админ/преподаватель пространства)"""
    try:
        await stage_service.delete_project_type(type_id, workspace_id, current_user.id)
    except BaseAppException as e:
        raise _resolve_error(e) from e
    return {"message": "Project type deleted successfully"}


@type_router.post("/{type_id}/stages", response_model=ProjectTypeFull)
async def add_stage(
    type_id: int,
    data: ProjectStageCreate,
    workspace_id: int | None = Query(None, description="Пространство, к которому привязан тип"),
    stage_service: ProjectStageService = Depends(get_stage_service),
    current_user: User = Depends(permission_required("workspace:update")),
) -> ProjectTypeFull:
    """Добавить этап к типу проекта"""
    try:
        return await stage_service.add_stage(type_id, workspace_id, data, current_user.id)
    except BaseAppException as e:
        raise _resolve_error(e) from e


@type_router.put("/{type_id}/stages/{stage_id}", response_model=ProjectTypeFull)
async def update_stage(
    type_id: int,
    stage_id: int,
    data: ProjectStageUpdate,
    workspace_id: int | None = Query(None, description="Пространство, к которому привязан тип"),
    stage_service: ProjectStageService = Depends(get_stage_service),
    current_user: User = Depends(permission_required("workspace:update")),
) -> ProjectTypeFull:
    """Обновить этап (админ/преподаватель пространства)"""
    try:
        return await stage_service.update_stage(type_id, stage_id, workspace_id, data, current_user.id)
    except BaseAppException as e:
        raise _resolve_error(e) from e


@type_router.delete("/{type_id}/stages/{stage_id}")
async def remove_stage(
    type_id: int,
    stage_id: int,
    workspace_id: int | None = Query(None, description="Пространство, к которому привязан тип"),
    stage_service: ProjectStageService = Depends(get_stage_service),
    current_user: User = Depends(permission_required("workspace:update")),
) -> dict[str, str]:
    """Удалить этап (админ/преподаватель пространства)"""
    try:
        await stage_service.remove_stage(type_id, stage_id, workspace_id, current_user.id)
    except BaseAppException as e:
        raise _resolve_error(e) from e
    return {"message": "Stage deleted successfully"}


@stage_router.post("/{project_id}/advance", response_model=ProjectFull)
async def advance_stage(
    project_id: int,
    stage_service: ProjectStageService = Depends(get_stage_service),
    current_user: User = Depends(permission_required("project:update")),
) -> ProjectFull:
    """Автор инициирует переход на следующий этап"""
    try:
        project = await stage_service.advance_stage(project_id, current_user.id)
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    return ProjectFull.from_orm(project, current_user.id)


@stage_router.post("/{project_id}/approve", response_model=ProjectFull)
async def approve_stage(
    project_id: int,
    stage_service: ProjectStageService = Depends(get_stage_service),
    current_user: User = Depends(permission_required("project:update")),
) -> ProjectFull:
    """Преподаватель утверждает текущий этап"""
    try:
        project = await stage_service.approve_stage(project_id, current_user.id)
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    return ProjectFull.from_orm(project, current_user.id)


@stage_router.post("/{project_id}/reject", response_model=ProjectFull)
async def reject_stage(
    project_id: int,
    body: RejectStageRequest = Body(default_factory=RejectStageRequest),
    stage_service: ProjectStageService = Depends(get_stage_service),
    current_user: User = Depends(permission_required("project:update")),
) -> ProjectFull:
    """Преподаватель отклоняет этап с возвратом на предыдущий"""
    try:
        project = await stage_service.reject_stage(project_id, current_user.id, body.comment)
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    return ProjectFull.from_orm(project, current_user.id)


@stage_router.get("/{project_id}/history", response_model=StageHistoryResponse)
async def stage_history(
    project_id: int,
    stage_service: ProjectStageService = Depends(get_stage_service),
    current_user: User = Depends(get_current_user),
) -> StageHistoryResponse:
    """Получить историю переходов этапов проекта"""
    try:
        return await stage_service.get_stage_history(project_id, current_user.id)
    except BaseAppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
