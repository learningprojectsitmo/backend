import math

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError  

from db.database import get_db
from schemas import *
from db.models import User, Project, Resume
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


@router.get("/users", response_model=UserListResponse, tags=['user'])
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


@router.get("/projects", response_model=ProjectListResponse, tags=['project'])
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


@router.get("/resumes/{resume_id}", response_model=ResumeFull, tags=["resume"])
def fetch_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    db_resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not db_resume:
        raise HTTPException(status_code=404, detail="There is no resume with that id!")
    return db_resume


@router.post("/resumes", response_model=ResumeResponse, status_code=201, tags=["resume"])
def create_resume(
    resume: ResumeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = resume.model_dump(exclude_unset=True)
    if "author_id" not in data:
        data["author_id"] = current_user.id

    print(data)
    db_resume = Resume(**data)
    print(db_resume)
    db.add(db_resume)

    try:
        db.commit()
        db.refresh(db_resume)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create the resume",
        )

    return db_resume


@router.patch("/resumes/{resume_id}", response_model=ResumeFull, tags=["resume"])
def update_resume(
    resume_id: int,
    resume: ResumeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not db_resume:
        raise HTTPException(status_code=404, detail="There is no resume with that id!")

    if current_user.id != db_resume.author_id:
        # TODO add admin role check in the future
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Only a user with id {db_resume.user_id} can update this resume!",
            headers={"WWW-Authenticate": "Bearer"},
        )

    update_data = resume.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_resume, field, value)

    try:
        db.commit()
        db.refresh(db_resume)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update the resume",
        )

    return db_resume


@router.delete("/resumes/{resume_id}", response_model=DeleteResponse, tags=["resume"])
def delete_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not db_resume:
        raise HTTPException(
            status_code=404,
            detail="There is no resume with that id!",
        )

    if current_user.id != db_resume.author_id:
        # TODO add admin role check in the future
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Only a user with id {db_resume.user_id} can delete this resume!",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        db.delete(db_resume)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete the resume",
        )

    return {"message": "Resume Deleted"}

@router.get("/resumes", response_model=ResumeListResponse, tags=['resume'])
def fetch_resumes(
    page: int = Query(1, ge=1, description="Номер страницы"), 
    limit: int = Query(10, ge=1, le=100, description="Количество резюме на странице"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    total = db.query(Resume).count()
    offset = (page - 1) * limit
    
    db_resumes = db.query(Resume).offset(offset).limit(limit).all()
    resumes = [ResumeFull.model_validate(resume) for resume in db_resumes]
    
    total_pages = math.ceil(total / limit) if total > 0 else 0
    
    return ResumeListResponse(
        items=resumes,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages
    )
