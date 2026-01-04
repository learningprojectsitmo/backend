from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.container import get_user_service
from src.core.dependencies import get_current_user
from src.model.models import User
from src.schema.user import UserCreate, UserFull, UserListResponse, UserUpdate
from src.services.user_service import UserService

user_router = APIRouter(prefix="/users", tags=["users"])


@user_router.post("/", response_model=UserFull)
async def create_user(
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service),
) -> UserFull:
    """Создать нового пользователя"""
    user = await user_service.create_user(user_data)
    return UserFull.model_validate(user)


@user_router.get("/{user_id}", response_model=UserFull)
async def get_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service),
    _current_user: User = Depends(get_current_user),
) -> UserFull:
    """Получить пользователя по ID"""
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserFull.model_validate(user)


@user_router.put("/{user_id}", response_model=UserFull)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user),
) -> UserFull:
    """Обновить пользователя (только сам пользователь или админ)"""
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )

    def _check_user_exists_or_raise_not_found() -> None:
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

    try:
        user = await user_service.update_user(user_id, user_data)
        _check_user_exists_or_raise_not_found()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update user: {e!s}",
        ) from e
    else:
        return UserFull.model_validate(user)


@user_router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Удалить пользователя (только сам пользователь или админ)"""
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )

    success = await user_service.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "User deleted successfully"}


@user_router.get("/", response_model=UserListResponse)
async def get_users(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество пользователей на странице"),
    user_service: UserService = Depends(get_user_service),
    _current_user: User = Depends(get_current_user),
) -> UserListResponse:
    """Получить список пользователей с пагинацией"""
    return await user_service.get_users_paginated(page=page, limit=limit)
