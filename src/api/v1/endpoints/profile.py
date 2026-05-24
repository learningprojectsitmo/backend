from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.core.container import get_profile_service
from src.core.dependencies import get_current_user
from src.model.user import User
from src.schema.profile import ProfileResponse
from src.services.profile_service import ProfileService

profile_router = APIRouter(prefix="/profile", tags=["profile"])


@profile_router.get("/", response_model=ProfileResponse)
async def fetch_profile(
    current_user: User = Depends(get_current_user),
    profile_service: ProfileService = Depends(get_profile_service),
) -> ProfileResponse:
    """Получить профиль текущего пользователя"""
    try:
        return await profile_service.get_profile(current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
