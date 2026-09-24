from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.core.container import get_search_service
from src.core.dependencies import get_current_user
from src.model.user import User
from src.schema.search import SearchResponse
from src.services.search_service import SearchService

search_router = APIRouter(prefix="/search", tags=["search"], dependencies=[Depends(get_current_user)])


@search_router.get("/", response_model=SearchResponse)
async def global_search(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    project_limit: int = Query(5, ge=1, le=50),
    space_limit: int = Query(5, ge=1, le=50),
    user_limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    search_service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    """Глобальный поиск: проекты, пространства, участники"""
    return await search_service.search(q, current_user.id, project_limit, space_limit, user_limit)
