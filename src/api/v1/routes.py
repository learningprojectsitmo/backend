from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError  

from db.database import get_db
from schemas import *
from db.models import User, Project
from auth import hash_password, get_current_user

router = APIRouter()

@router.get("/users/{user_id}", response_model=UserFull, tags=['user'])
def fetch_user(
    user_id: int, 
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
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

#
# PROJECT CRUD, move it to a separate file
#

@router.get("/projects/{project_id}", response_model=ProjectFull, tags=['project'])
def fetch_project(
    project_id: int, 
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=404, detail="There is no project with that id!")
    
    return db_project


@router.patch("/projects/{project_id}", response_model=ProjectFull, tags=['project'])
def update_project(
    project_id: int, 
    project: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=404, detail="There is no project with that id!")

    if current_user.id != db_project.author.id:
        # TODO when roles are implemented, allow admin to update projects as well
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Only a user with id {db_project.author.id} can update their info!",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    update_data = project.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_project, field, value)

    try:
        db.commit()
        db.refresh(db_project)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update a project")

    return db_project


@router.delete("/projects/{project_id}", response_model=DeleteResponse, tags=['project'])
def delete_project(
    project_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=404, detail="There is no project with that id!")

    if current_user.id != db_project.author.id:
        # TODO when roles are implemented, allow admin to delete projects as well
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Only a user with id {db_project.author.id} can delete their project!",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    try:
        db.delete(db_project)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete the project")

    return {"message": "Project Deleted"}


@router.post("/projects", response_model=ProjectResponse, status_code=201, tags=['project'])
def create_project(
    project: ProjectCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    data = project.model_dump(exclude_unset=True)
    if not 'author_id' in data:
        data['author_id'] = current_user.id
    db_project = Project(**data)
    db.add(db_project)
    try:
        db.commit()
        db.refresh(db_project)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create the project")

    return db_project

