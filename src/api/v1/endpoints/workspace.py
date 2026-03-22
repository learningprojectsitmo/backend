from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.container import get_user_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.models import User
from src.schema.user import UserCreate, UserFull, UserListResponse, UserUpdate
from src.services.user_service import UserService

user_router = APIRouter(prefix="/users", tags=["users"])


@user_router.post("/", response_model=UserFull)
async def create_workspace(
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service),
) -> UserFull:
    """Создать нового пользователя"""
    pass


@user_router.delete("/{workspace_id}", response_model=UserFull)
async def dell_workspace(
    workspace_id: int,
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service),
) -> UserFull:
    """Удаление нового пользователя"""
    pass


@user_router.post("/{workspace_id}/user/{user_id}", response_model=UserFull)
async def add_user_workspace(
    workspace_id: int,
    user_id: int,
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service),
) -> UserFull:
    """Создать нового пользователя"""
    pass


@user_router.delete("/{workspace_id}/user/{user_id}", response_model=UserFull)
async def dell_user_workspace(
    workspace_id: int,
    user_id: int,
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service),
) -> UserFull:
    """Создать нового пользователя"""
    pass
