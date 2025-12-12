from fastapi import APIRouter, Depends, Query, HTTPException, status
from dependency_injector.wiring import Provide

from src.core.middleware import inject
from src.model.models import User
from src.schema.resume import ResumeCreate, ResumeUpdate, ResumeResponse, ResumeListResponse, ResumeFull
from src.core.container import Container
from src.services.resume_service import ResumeService
from src.core.dependencies import get_current_user


resume_router = APIRouter(prefix="/resumes", tags=["resume"])


@resume_router.get("/{resume_id}", response_model=ResumeFull)
@inject
async def fetch_resume(
    resume_id: int,
    resume_service: ResumeService = Depends(Provide[Container.resume_service]),
    _current_user: User = Depends(get_current_user)
):
    """Получить резюме по ID"""
    resume = await resume_service.get_resume_by_id(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="There is no resume with that id!")

    return ResumeFull.model_validate(resume)


@resume_router.get("/", response_model=ResumeListResponse)
@inject
async def fetch_resumes(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество резюме на странице"),
    resume_service: ResumeService = Depends(Provide[Container.resume_service]),
    _current_user: User = Depends(get_current_user)
):
    """Получить список резюме с пагинацией"""
    resumes, total = await resume_service.get_resumes_paginated(page, limit)
    resumes_list = [ResumeFull.model_validate(resume) for resume in resumes]

    total_pages = (total + limit - 1) // limit if total > 0 else 0

    return ResumeListResponse(
        items=resumes_list,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages
    )


@resume_router.post("/", response_model=ResumeFull)
@inject
async def create_resume(
    resume_data: ResumeCreate,
    resume_service: ResumeService = Depends(Provide[Container.resume_service]),
    current_user: User = Depends(get_current_user)
):
    """Создать новое резюме"""
    resume = await resume_service.create_resume(resume_data, current_user.id)
    return ResumeFull.model_validate(resume)


@resume_router.put("/{resume_id}", response_model=ResumeFull)
@inject
async def update_resume(
    resume_id: int,
    resume_data: ResumeUpdate,
    resume_service: ResumeService = Depends(Provide[Container.resume_service]),
    current_user: User = Depends(get_current_user)
):
    """Обновить резюме (только автор может обновлять)"""
    try:
        resume = await resume_service.update_resume(resume_id, resume_data, current_user.id)
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")
        
        return ResumeFull.model_validate(resume)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update resume: {str(e)}") from e


@resume_router.delete("/{resume_id}")
@inject
async def delete_resume(
    resume_id: int,
    resume_service: ResumeService = Depends(Provide[Container.resume_service]),
    current_user: User = Depends(get_current_user)
):
    """Удалить резюме (только автор может удалять)"""
    try:
        success = await resume_service.delete_resume(resume_id, current_user.id)
        if not success:
            raise HTTPException(status_code=404, detail="Resume not found")
        
        return {"message": "Resume deleted successfully"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))