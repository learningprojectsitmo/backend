import math

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from core.database import get_db
from core.dependencies import get_current_user
from schemas import *
from model.models import User, Resume


resume_router = APIRouter(prefix="/resumes", tags=["resume"])

@resume_router.get("/{resume_id}", response_model=ResumeFull)
def fetch_resume(
        resume_id: int,
        db: Session = Depends(get_db),
        _: User = Depends(get_current_user),
):
    db_resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not db_resume:
        raise HTTPException(status_code=404, detail="There is no resume with that id!")
    return db_resume


@resume_router.post("/resumes", response_model=ResumeResponse, status_code=201, tags=["resume"])
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


@resume_router.patch("/{resume_id}", response_model=ResumeFull, tags=["resume"])
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


@resume_router.delete("/{resume_id}", response_model=DeleteResponse, tags=["resume"])
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


@resume_router.get("/resumes", response_model=ResumeListResponse, tags=['resume'])
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
