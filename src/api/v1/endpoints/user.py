import math

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from core.database import get_db
from core.dependencies import get_current_user
from core.security import hash_password
from schemas import *
from model.models import User


user_router = APIRouter(prefix="/users", tags=['user'])


@user_router.get("/{user_id}", response_model=UserFull)
def fetch_user(
        user_id: int,
        db: Session = Depends(get_db),
        _: User = Depends(get_current_user)
):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="There is no user with that id!")
    return db_user


@user_router.get("/", response_model=UserListResponse)
def fetch_users(
        page: int = Query(1, ge=1, description="Номер страницы"),
        limit: int = Query(10, ge=1, le=100, description="Количество пользователей на странице"),
        db: Session = Depends(get_db),
        _: User = Depends(get_current_user)
):
    # Подсчет общего количества пользователей
    total = db.query(User).count()

    # Вычисление offset для пагинации
    offset = (page - 1) * limit

    # Получение пользователей с пагинацией
    db_users = db.query(User).offset(offset).limit(limit).all()

    # Преобразование в схему UserListItem
    users = [UserListItem.model_validate(user) for user in db_users]

    # Вычисление общего количества страниц
    total_pages = math.ceil(total / limit) if total > 0 else 0

    return UserListResponse(
        items=users,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages
    )


@user_router.patch("/{user_id}", response_model=UserFull)
def update_user(
        user_id: int,
        user: UserUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    if current_user.id != user_id:
        # TODO when roles are implemented, allow admin to update users as well
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Only a user with id {user_id} can update their info!",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="There is no user with that id!")

    update_data = user.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_user, field, value)

    try:
        db.commit()
        db.refresh(db_user)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update a user")

    return db_user


@user_router.delete("/{user_id}", response_model=DeleteResponse)
def delete_user(
        user_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    if current_user.id != user_id:
        # TODO when roles are implemented, allow admin to update users as well
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Only a user with id {user_id} can update their info!",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="There is no user with that id!")

    try:
        db.delete(db_user)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete user")

    return {"message": "User Deleted"}


@user_router.post("/", response_model=UserResponse, status_code=201)
def create_user(
        user: UserCreate,
        db: Session = Depends(get_db)
):
    pwd = user.password_string
    data = user.model_dump(exclude={"password_string"})
    data["password_hashed"] = hash_password(pwd)
    db_user = User(**data)
    db.add(db_user)
    try:
        db.commit()
        db.refresh(db_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="User with this email already exists")

    return db_user
