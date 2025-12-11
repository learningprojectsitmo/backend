import math

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from core.database import get_db
from core.dependencies import get_current_user
from schemas import *
from model.models import User, Project


project_router = APIRouter(prefix="/projects", tags=['project'])

@project_router.get("/{project_id}", response_model=ProjectFull)
def fetch_project(
        project_id: int,
        db: Session = Depends(get_db),
        _: User = Depends(get_current_user)
):
    db_project = db.query(Project).filter(Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=404, detail="There is no project with that id!")

    return db_project


@project_router.patch("/{project_id}", response_model=ProjectFull)
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


@project_router.delete("/{project_id}", response_model=DeleteResponse)
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


@project_router.post("/", response_model=ProjectResponse, status_code=201)
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


@project_router.get("/", response_model=ProjectListResponse)
def fetch_projects(
        page: int = Query(1, ge=1, description="Номер страницы"),
        limit: int = Query(10, ge=1, le=100, description="Количество проектов на странице"),
        db: Session = Depends(get_db),
        _: User = Depends(get_current_user)
):
    total = db.query(Project).count()
    offset = (page - 1) * limit

    db_projects = db.query(Project).offset(offset).limit(limit).all()
    projects = [ProjectListItem.model_validate(project) for project in db_projects]

    total_pages = math.ceil(total / limit) if total > 0 else 0

    return ProjectListResponse(
        items=projects,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages
    )
