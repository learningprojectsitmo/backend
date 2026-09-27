from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.container import get_wiki_service
from src.core.dependencies import get_current_user, get_current_user_no_exception, is_admin_user
from src.core.exceptions import BaseAppException
from src.model.user import User
from src.schema.wiki import (
    WikiPageCreate,
    WikiPageFull,
    WikiPageListResponse,
    WikiPageSummary,
    WikiPageUpdate,
)
from src.services.wiki_service import WikiService

# Без router-level setup_audit: вики читается анонимно, и лишний middleware
# на публичном GET не нужен. Аудит на мутациях вешается точечно.
wiki_router = APIRouter(prefix="/projects", tags=["wiki"])


def _resolve_error(e: BaseAppException) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=e.detail)


def _admin_flag(current_user: User | None) -> bool:
    """is_admin для анонимного посетителя — просто False."""
    return bool(current_user and is_admin_user(current_user))


@wiki_router.get("/{project_id}/wiki", response_model=WikiPageListResponse)
async def list_wiki_pages(
    project_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=200),
    wiki_service: WikiService = Depends(get_wiki_service),
    current_user: User | None = Depends(get_current_user_no_exception),
) -> WikiPageListResponse:
    """Список страниц вики проекта. Анонимному видны только публичные."""
    try:
        return await wiki_service.list_pages(
            project_id,
            current_user.id if current_user else None,
            page=page,
            limit=limit,
            is_admin=_admin_flag(current_user),
        )
    except BaseAppException as e:
        raise _resolve_error(e) from e


@wiki_router.get("/{project_id}/wiki/tree", response_model=list[WikiPageSummary])
async def get_wiki_tree(
    project_id: int,
    wiki_service: WikiService = Depends(get_wiki_service),
    current_user: User | None = Depends(get_current_user_no_exception),
) -> list[WikiPageSummary]:
    """Плоский список страниц для построения дерева. Анонимному — публичные."""
    try:
        return await wiki_service.get_tree(
            project_id,
            current_user.id if current_user else None,
            is_admin=_admin_flag(current_user),
        )
    except BaseAppException as e:
        raise _resolve_error(e) from e


@wiki_router.get("/{project_id}/wiki/{page_id}", response_model=WikiPageFull)
async def get_wiki_page(
    project_id: int,
    page_id: int,
    wiki_service: WikiService = Depends(get_wiki_service),
    current_user: User | None = Depends(get_current_user_no_exception),
) -> WikiPageFull:
    """Страница вики. Приватная постороннему отдаёт 404, а не 403."""
    try:
        return await wiki_service.get_page(
            project_id,
            page_id,
            current_user.id if current_user else None,
            is_admin=_admin_flag(current_user),
        )
    except BaseAppException as e:
        raise _resolve_error(e) from e


@wiki_router.post(
    "/{project_id}/wiki",
    response_model=WikiPageFull,
    status_code=201,
    dependencies=[Depends(get_current_user)],
)
async def create_wiki_page(
    project_id: int,
    data: WikiPageCreate,
    wiki_service: WikiService = Depends(get_wiki_service),
    current_user: User = Depends(get_current_user),
) -> WikiPageFull:
    """Создать страницу вики. Видимость по умолчанию — приватная."""
    try:
        return await wiki_service.create_page(
            project_id,
            current_user.id,
            data,
            is_admin=is_admin_user(current_user),
        )
    except BaseAppException as e:
        raise _resolve_error(e) from e


@wiki_router.put(
    "/{project_id}/wiki/{page_id}",
    response_model=WikiPageFull,
    dependencies=[Depends(get_current_user)],
)
async def update_wiki_page(
    project_id: int,
    page_id: int,
    data: WikiPageUpdate,
    wiki_service: WikiService = Depends(get_wiki_service),
    current_user: User = Depends(get_current_user),
) -> WikiPageFull:
    """Обновить страницу вики. Не переданные поля не меняются."""
    try:
        return await wiki_service.update_page(
            project_id,
            page_id,
            current_user.id,
            data,
            is_admin=is_admin_user(current_user),
        )
    except BaseAppException as e:
        raise _resolve_error(e) from e


@wiki_router.delete(
    "/{project_id}/wiki/{page_id}",
    status_code=204,
    dependencies=[Depends(get_current_user)],
)
async def delete_wiki_page(
    project_id: int,
    page_id: int,
    wiki_service: WikiService = Depends(get_wiki_service),
    current_user: User = Depends(get_current_user),
) -> None:
    """Удалить страницу вики вместе со всеми вложенными."""
    try:
        await wiki_service.delete_page(
            project_id,
            page_id,
            current_user.id,
            is_admin=is_admin_user(current_user),
        )
    except BaseAppException as e:
        raise _resolve_error(e) from e
