from typing import Annotated
from src.core.middleware import inject
from fastapi import APIRouter, Depends, Query, HTTPException, status
from dependency_injector.wiring import Provide

from src.model.models import User
from src.schema.user import UserCreate, UserListResponse, UserFull
from src.core.container import Container
from src.services.user_service import UserService
from src.core.dependencies import get_current_user


user_router = APIRouter(prefix="/users", tags=["users"])


@user_router.post("/", response_model=UserFull)
@inject
async def create_user(
    user_data: UserCreate,
    user_service: Annotated[
        UserService, Depends(Provide[Container.user_service])
    ],
):
    """Создать нового пользователя"""
    user = await user_service.create_user(user_data)
    return UserFull.model_validate(user)


@user_router.get("/{user_id}", response_model=UserFull)
@inject
async def get_user(
    user_id: int,
    user_service: UserService = Depends(Provide[Container.user_service]),
    _current_user: User = Depends(get_current_user)
):
    """Получить пользователя по ID"""
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserFull.model_validate(user)


@user_router.put("/{user_id}", response_model=UserFull)
@inject
async def update_user(
    user_id: int,
    user_data: UserCreate,
    user_service: UserService = Depends(Provide[Container.user_service]),
    current_user: User = Depends(get_current_user)
):
    """Обновить пользователя (только сам пользователь или админ)"""
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )

    try:
        user = await user_service.update_user(user_id, user_data)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return UserFull.model_validate(user)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update user: {str(e)}"
        ) from e


@user_router.delete("/{user_id}")
@inject
async def delete_user(
    user_id: int,
    user_service: UserService = Depends(Provide[Container.user_service]),
    current_user: User = Depends(get_current_user)
):
    """Удалить пользователя (только сам пользователь или админ)"""
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    success = await user_service.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": "User deleted successfully"}


@user_router.get("/", response_model=UserListResponse)
@inject
async def get_users(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество пользователей на странице"),
    user_service: UserService = Depends(Provide[Container.user_service]),
    _current_user: User = Depends(get_current_user)
):
    """Получить список пользователей с пагинацией"""
    return await user_service.get_users_paginated(page=page, limit=limit)

