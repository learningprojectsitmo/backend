from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.core.container import get_specification_service
from src.core.dependencies import get_current_user, is_admin_user, setup_audit
from src.core.exceptions import BaseAppException
from src.model.project import SpecificationComment
from src.model.user import User
from src.schema.specification import (
    SpecificationCommentCreate,
    SpecificationCommentResponse,
    SpecificationCommentUpdate,
    SpecificationFull,
    SpecificationUpdate,
)
from src.services.specification_service import SpecificationService

specification_router = APIRouter(
    prefix="/projects",
    tags=["project-specification"],
    dependencies=[Depends(setup_audit)],
)


def _resolve_error(e: BaseAppException) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.detail)


@specification_router.get("/{project_id}/specification", response_model=SpecificationFull)
async def get_specification(
    project_id: int,
    specification_service: SpecificationService = Depends(get_specification_service),
    current_user: User = Depends(get_current_user),
) -> SpecificationFull:
    """Получить техническое задание проекта (создаётся черновик, если его нет)"""
    try:
        return await specification_service.get_specification(project_id, current_user.id)
    except BaseAppException as e:
        raise _resolve_error(e) from e


@specification_router.put("/{project_id}/specification", response_model=SpecificationFull)
async def update_specification(
    project_id: int,
    data: SpecificationUpdate,
    specification_service: SpecificationService = Depends(get_specification_service),
    current_user: User = Depends(get_current_user),
) -> SpecificationFull:
    """Обновить техническое задание проекта (только автор, только в статусе черновика)"""
    try:
        return await specification_service.update_specification(project_id, current_user.id, data)
    except BaseAppException as e:
        raise _resolve_error(e) from e


@specification_router.get(
    "/{project_id}/specification/comments",
    response_model=list[SpecificationCommentResponse],
)
async def get_specification_comments(
    project_id: int,
    specification_service: SpecificationService = Depends(get_specification_service),
    current_user: User = Depends(get_current_user),
) -> list[SpecificationCommentResponse]:
    """Получить комментарии к техническому заданию проекта"""
    try:
        return await specification_service.get_comments(project_id, current_user.id)
    except BaseAppException as e:
        raise _resolve_error(e) from e


def _to_comment_response(comment: SpecificationComment, current_user: User) -> SpecificationCommentResponse:
    return SpecificationCommentResponse(
        id=comment.id,
        specification_id=comment.specification_id,
        author={"id": current_user.id, "username": current_user.first_name or "Unknown"},
        text=comment.text,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


@specification_router.post(
    "/{project_id}/specification/comments",
    response_model=SpecificationCommentResponse,
)
async def add_specification_comment(
    project_id: int,
    comment_data: SpecificationCommentCreate,
    specification_service: SpecificationService = Depends(get_specification_service),
    current_user: User = Depends(get_current_user),
) -> SpecificationCommentResponse:
    """Добавить комментарий к техническому заданию (автор, преподаватель или админ)"""
    if not comment_data.text.strip():
        raise HTTPException(status_code=422, detail="Comment text cannot be empty")
    try:
        comment = await specification_service.add_comment(
            project_id,
            current_user.id,
            comment_data.text,
            is_admin=is_admin_user(current_user),
        )
    except BaseAppException as e:
        raise _resolve_error(e) from e
    return _to_comment_response(comment, current_user)


@specification_router.put(
    "/{project_id}/specification/comments/{comment_id}",
    response_model=SpecificationCommentResponse,
)
async def update_specification_comment(
    project_id: int,
    comment_id: int,
    comment_data: SpecificationCommentUpdate,
    specification_service: SpecificationService = Depends(get_specification_service),
    current_user: User = Depends(get_current_user),
) -> SpecificationCommentResponse:
    """Обновить комментарий к техническому заданию (только автор комментария)"""
    if not comment_data.text.strip():
        raise HTTPException(status_code=422, detail="Comment text cannot be empty")
    try:
        comment = await specification_service.update_comment(
            project_id,
            comment_id,
            current_user.id,
            comment_data.text,
        )
    except BaseAppException as e:
        raise _resolve_error(e) from e
    return _to_comment_response(comment, current_user)


@specification_router.delete("/{project_id}/specification/comments/{comment_id}", status_code=204)
async def delete_specification_comment(
    project_id: int,
    comment_id: int,
    specification_service: SpecificationService = Depends(get_specification_service),
    current_user: User = Depends(get_current_user),
) -> None:
    """Удалить комментарий к техническому заданию (автор комментария или админ)"""
    try:
        await specification_service.delete_comment(
            project_id,
            comment_id,
            current_user.id,
            is_admin=is_admin_user(current_user),
        )
    except BaseAppException as e:
        raise _resolve_error(e) from e
