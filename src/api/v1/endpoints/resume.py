import math

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.container import Container
from src.core.dependencies import get_current_user
from src.core.middleware import inject
from src.model.models import User
from src.schemas import *
from src.services.resume_service import ResumeService

resume_router = APIRouter(prefix="/resumes", tags=["resume"])


@resume_router.get("/{resume_id}", response_model=ResumeFull)
@inject
async def fetch_resume(
    resume_id: int,
    resume_service: ResumeService = Depends(Provide[Container.resume_service]),
    current_user: User = Depends(get_current_user)
):
    """Получить резюме по ID"""
    resume = resume_service.get_resume_by_id(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="There is no resume with that id!")

    return ResumeFull.model_validate(resume)


@resume_router.post("/", response_model=ResumeResponse, status_code=201)
@inject
async def create_resume(
    resume_data: ResumeCreate,
    resume_service: ResumeService = Depends(Provide[Container.resume_service]),
    current_user: User = Depends(get_current_user)
):
    """Создать новое резюме"""
    resume = resume_service.create_resume(resume_data, current_user.id)
    return ResumeResponse.model_validate(resume)


@resume_router.patch("/{resume_id}", response_model=ResumeFull)
@inject
async def update_resume(
    resume_id: int,
    resume_data: ResumeUpdate,
    resume_service: ResumeService = Depends(Provide[Container.resume_service]),
    current_user: User = Depends(get_current_user)
):
    """Обновить резюме (только автор может обновлять)"""
    try:
        resume = resume_service.update_resume(resume_id, resume_data, current_user.id)
        if not resume:
            raise HTTPException(status_code=404, detail="There is no resume with that id!")

        return ResumeFull.model_validate(resume)
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@resume_router.delete("/{resume_id}", response_model=DeleteResponse)
@inject
async def delete_resume(
    resume_id: int,
    resume_service: ResumeService = Depends(Provide[Container.resume_service]),
    current_user: User = Depends(get_current_user)
):
    """Удалить резюме (только автор может удалять)"""
    try:
        success = resume_service.delete_resume(resume_id, current_user.id)
        if not success:
            raise HTTPException(status_code=404, detail="There is no resume with that id!")

        return {"message": "Resume Deleted"}
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


@resume_router.get("/", response_model=ResumeListResponse)
@inject
async def fetch_resumes(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество резюме на странице"),
    resume_service: ResumeService = Depends(Provide[Container.resume_service]),
    current_user: User = Depends(get_current_user)
):
    """Получить список резюме с пагинацией"""
    resumes, total = resume_service.get_resumes_paginated(page, limit)
    resumes_list = [ResumeFull.model_validate(resume) for resume in resumes]

    total_pages = math.ceil(total / limit) if total > 0 else 0

    return ResumeListResponse(
        items=resumes_list,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages
    )
