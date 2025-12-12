from dependency_injector.wiring import Provide
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.container import Container
from src.core.dependencies import get_current_user
from src.model.models import User
from src.schemas import UserCreate, UserFull, UserListResponse, UserUpdate
from src.services.user_service import UserService

user_router = APIRouter(prefix="/users", tags=["users"])


@user_router.post("/", response_model=UserFull)
async def create_user(
    user_data: UserCreate,
    user_service: UserService = Depends(Provide[Container.user_service])
):
    """Создать нового пользователя"""
    try:
        user = user_service.create_user(user_data)
        return UserFull.model_validate(user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create user: {str(e)}"
        ) from e


@user_router.get("/{user_id}", response_model=UserFull)
async def get_user(
    user_id: int,
    user_service: UserService = Depends(Provide[Container.user_service]),
    _current_user: User = Depends(get_current_user)
):
    """Получить пользователя по ID"""
    user = user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return UserFull.model_validate(user)


@user_router.get("/", response_model=UserListResponse)
async def get_users(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество пользователей на странице"),
    user_service: UserService = Depends(Provide[Container.user_service]),
    _current_user: User = Depends(get_current_user)
):
    """Получить список пользователей с пагинацией"""
    return user_service.get_users_paginated(page=page, limit=limit)


@user_router.put("/{user_id}", response_model=UserFull)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    user_service: UserService = Depends(Provide[Container.user_service]),
    current_user: User = Depends(get_current_user)
):
    """Обновить пользователя"""
    # Проверяем, что пользователь может обновлять только свои данные
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own profile"
        )

    user = user_service.update_user(user_id, user_data)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return UserFull.model_validate(user)


@user_router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    user_service: UserService = Depends(Provide[Container.user_service]),
    current_user: User = Depends(get_current_user)
):
    """Удалить пользователя"""
    # Проверяем, что пользователь может удалять только свои данные
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own profile"
        )

    success = user_service.delete_user(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return {"message": "User deleted successfully"}
