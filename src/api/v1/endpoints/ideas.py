from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.container import get_idea_service, get_idea_tag_service
from src.core.dependencies import get_current_user, is_admin_user, permission_required
from src.model.user import User
from src.schema.ideas import (
    IdeaCommentCreate,
    IdeaCommentResponse,
    IdeaCreate,
    IdeaFullResponse,
    IdeaListResponse,
    IdeaTagCreate,
    IdeaTagResponse,
    IdeaUpdate,
    IdeaVoteRequest,
)
from src.services.ideas_service import IdeaService, IdeaTagService

ideas_router = APIRouter(prefix="/ideas", tags=["ideas"])


@ideas_router.get("/", response_model=IdeaListResponse)
async def fetch_ideas(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(100, ge=1, le=100, description="Количество идей на странице"),
    search: str | None = Query(None, description="Поиск по заголовку и описанию"),
    sort: str | None = Query(None, description="Сортировка: newest или popular"),
    status: str | None = Query(None, description="Фильтр по статусу"),
    tag: str | None = Query(None, description="Фильтр по тегу"),
    idea_service: IdeaService = Depends(get_idea_service),
    current_user: User = Depends(get_current_user),
) -> IdeaListResponse:
    """Получить список идей с фильтрацией и пагинацией"""
    result = await idea_service.get_ideas_filtered(
        page=page,
        limit=limit,
        search=search,
        sort=sort,
        status=status,
        tag=tag,
        current_user_id=current_user.id,
    )
    return IdeaListResponse(**result)


@ideas_router.get("/tags", response_model=list[IdeaTagResponse])
async def fetch_tags(
    tag_service: IdeaTagService = Depends(get_idea_tag_service),
    _current_user: User = Depends(get_current_user),
) -> list[IdeaTagResponse]:
    """Получить список всех тегов идей"""
    return await tag_service.get_all_tags()


@ideas_router.post("/tags", response_model=IdeaTagResponse)
async def create_tag(
    tag_data: IdeaTagCreate,
    tag_service: IdeaTagService = Depends(get_idea_tag_service),
    current_user: User = Depends(permission_required("ideas:update")),
) -> IdeaTagResponse:
    """Создать новый тег для идей"""
    if not tag_data.name.strip():
        raise HTTPException(status_code=422, detail="Tag name cannot be empty")

    tag = await tag_service.create_tag(tag_data.name.strip())
    return IdeaTagResponse(id=tag.id, name=tag.name, count=tag.count)


@ideas_router.get("/{idea_id}", response_model=IdeaFullResponse)
async def fetch_idea(
    idea_id: int,
    idea_service: IdeaService = Depends(get_idea_service),
    current_user: User = Depends(get_current_user),
) -> IdeaFullResponse:
    """Получить идею по ID с деталями и комментариями"""
    idea = await idea_service.get_idea_full(idea_id, current_user_id=current_user.id)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    return idea


@ideas_router.post("/", response_model=IdeaFullResponse)
async def create_idea(
    idea_data: IdeaCreate,
    idea_service: IdeaService = Depends(get_idea_service),
    current_user: User = Depends(permission_required("ideas:create")),
) -> IdeaFullResponse:
    """Создать новую идею"""
    idea = await idea_service.create_idea(idea_data, author_id=current_user.id)
    result = await idea_service.get_idea_full(idea.id, current_user_id=current_user.id)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create idea")
    return result


@ideas_router.put("/{idea_id}", response_model=IdeaFullResponse)
async def update_idea(
    idea_id: int,
    idea_data: IdeaUpdate,
    idea_service: IdeaService = Depends(get_idea_service),
    current_user: User = Depends(permission_required("ideas:update")),
) -> IdeaFullResponse:
    """Обновить идею (автор или админ): заголовок, описание, статус"""
    is_admin = is_admin_user(current_user)

    try:
        updated = await idea_service.update_idea(idea_id, idea_data, current_user.id, is_admin=is_admin)
    except PermissionError:
        raise HTTPException(status_code=403, detail="You can only update your own ideas") from None

    if not updated:
        raise HTTPException(status_code=404, detail="Idea not found")

    result = await idea_service.get_idea_full(idea_id, current_user_id=current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Idea not found")
    return result


@ideas_router.delete("/{idea_id}", status_code=204)
async def delete_idea(
    idea_id: int,
    idea_service: IdeaService = Depends(get_idea_service),
    current_user: User = Depends(permission_required("ideas:delete")),
) -> None:
    """Удалить идею (свою или любую для админа)"""
    is_admin = is_admin_user(current_user)

    try:
        deleted = await idea_service.delete_idea(idea_id, current_user.id, is_admin=is_admin)
    except PermissionError:
        raise HTTPException(status_code=403, detail="You can only delete your own ideas") from None

    if not deleted:
        raise HTTPException(status_code=404, detail="Idea not found")


@ideas_router.post("/{idea_id}/vote", response_model=IdeaFullResponse)
async def vote_idea(
    idea_id: int,
    vote_data: IdeaVoteRequest,
    idea_service: IdeaService = Depends(get_idea_service),
    current_user: User = Depends(permission_required("ideas:update")),
) -> IdeaFullResponse:
    """Проголосовать за идею (up/down). Повторный вызов того же направления отменяет голос."""
    if vote_data.direction not in ("up", "down"):
        raise HTTPException(status_code=422, detail="Direction must be 'up' or 'down'")

    try:
        await idea_service.toggle_vote(idea_id, current_user.id, vote_data.direction)
    except ValueError:
        raise HTTPException(status_code=404, detail="Idea not found") from None

    result = await idea_service.get_idea_full(idea_id, current_user_id=current_user.id)
    if not result:
        raise HTTPException(status_code=404, detail="Idea not found")
    return result


@ideas_router.get("/{idea_id}/comments", response_model=list[IdeaCommentResponse])
async def fetch_comments(
    idea_id: int,
    idea_service: IdeaService = Depends(get_idea_service),
    current_user: User = Depends(get_current_user),
) -> list[IdeaCommentResponse]:
    """Получить комментарии к идее"""
    return await idea_service.get_comments(idea_id)


@ideas_router.post("/{idea_id}/comments", response_model=IdeaCommentResponse)
async def add_comment(
    idea_id: int,
    comment_data: IdeaCommentCreate,
    idea_service: IdeaService = Depends(get_idea_service),
    current_user: User = Depends(permission_required("ideas:update")),
) -> IdeaCommentResponse:
    """Добавить комментарий к идее"""
    if not comment_data.text.strip():
        raise HTTPException(status_code=422, detail="Comment text cannot be empty")

    comment = await idea_service.add_comment(idea_id, current_user.id, comment_data.text)
    return IdeaCommentResponse(
        id=comment.id,
        author={"id": current_user.id, "username": current_user.first_name or "Unknown"},
        text=comment.text,
        created_at=comment.created_at,
    )
