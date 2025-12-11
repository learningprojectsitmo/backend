from datetime import timedelta

from typing import Annotated
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import  OAuth2PasswordRequestForm

from core.config import settings
from core.database import get_db
from core.security import create_access_token, verify_password
from model.models import User
from schemas import Token

auth_router = APIRouter(prefix="/auth", tags=["authentication"])


def authenticate_user(
    email: str,
    password: str,
    db: Session
):
    db_user = db.query(User).filter(User.email == email).first()
    if not db_user or not verify_password(password, db_user.password_hashed):
        return False

    return db_user


@auth_router.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db)
):
    # OAuth2PasswordRequestForm has strict fields names, but we will treat username as an email
    user = authenticate_user(form_data.username, form_data.password, db)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")






