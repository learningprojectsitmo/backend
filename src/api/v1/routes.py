from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError  

from db.database import get_db
from schemas import *
from db.models import User
from auth import hash_password, get_current_user

router = APIRouter()

@router.get("/users/{user_id}", response_model=UserFull, tags=['user'])
def fetch_user(
    user_id: int, 
    db: Session = Depends(get_db)
):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="There is no user with that id!")
    
    return db_user

@router.patch("/users/{user_id}", response_model=UserFull, tags=['user'])
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

@router.delete("/users/{user_id}", response_model=DeleteResponse, tags=['user'])
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

@router.post("/users", response_model=UserResponse, status_code=201, tags=['user'])
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

