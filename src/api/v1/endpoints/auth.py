from typing import Annotated

from dependency_injector.wiring import Provide
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from src.core.middleware import inject
from src.core.container import Container
from src.core.dependencies import get_current_user
from src.model.models import User
from src.schemas import Token
from src.services.auth_service import AuthService

auth_router = APIRouter(prefix="/auth", tags=["authentication"])


@auth_router.post("/token")
@inject
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: AuthService = Depends(Provide[Container.auth_service])
) -> Token:
    """Аутентификация пользователя и получение токена доступа"""
    return await auth_service.login_for_access_token(form_data)


@auth_router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user)
):
    """Выход пользователя (в будущем можно добавить blacklist токенов)"""
    return {"message": "Successfully logged out"}


@auth_router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Получить информацию о текущем пользователе"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "middle_name": current_user.middle_name,
        "last_name": current_user.last_name,
        "isu_number": current_user.isu_number,
        "tg_nickname": current_user.tg_nickname
    }
