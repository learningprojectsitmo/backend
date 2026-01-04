from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.container import get_resume_service
from src.core.dependencies import get_current_user
from src.model.models import User
from src.schema.resume import ResumeCreate, ResumeFull, ResumeListResponse, ResumeUpdate
from src.services.resume_service import ResumeService

resume_router = APIRouter(prefix="/resumes", tags=["resume"])


@resume_router.get("/{resume_id}", response_model=ResumeFull)
async def fetch_resume(
    resume_id: int,
    resume_service: ResumeService = Depends(get_resume_service),
    _current_user: User = Depends(get_current_user),
) -> ResumeFull:
    """Получить резюме по ID"""
    resume = await resume_service.get_resume_by_id(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="There is no resume with that id!")

    return ResumeFull.model_validate(resume)


@resume_router.get("/", response_model=ResumeListResponse)
async def fetch_resumes(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество резюме на странице"),
    resume_service: ResumeService = Depends(get_resume_service),
    _current_user: User = Depends(get_current_user),
) -> ResumeListResponse:
    """Получить список резюме с пагинацией"""
    resumes, total = await resume_service.get_resumes_paginated(page, limit)
    resumes_list = [ResumeFull.model_validate(resume) for resume in resumes]

    total_pages = (total + limit - 1) // limit if total > 0 else 0

    return ResumeListResponse(
        items=resumes_list,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@resume_router.post("/", response_model=ResumeFull)
async def create_resume(
    resume_data: ResumeCreate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeFull:
    """Создать новое резюме"""
    resume = await resume_service.create_resume(resume_data, current_user.id)
    return ResumeFull.model_validate(resume)


@resume_router.put("/{resume_id}", response_model=ResumeFull)
async def update_resume(
    resume_id: int,
    resume_data: ResumeUpdate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeFull:
    """Обновить резюме (только автор может обновлять)"""

    def _get_resume_or_raise_not_found() -> None:
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")

    try:
        resume = await resume_service.update_resume(resume_id, resume_data, current_user.id)
        _get_resume_or_raise_not_found()
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to update resume: {e!s}") from e
    else:
        return ResumeFull.model_validate(resume)


@resume_router.delete("/{resume_id}")
async def delete_resume(
    resume_id: int,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Удалить резюме (только автор может удалять)"""

    def _check_success_or_raise_not_found() -> None:
        if not success:
            raise HTTPException(status_code=404, detail="Resume not found")

    try:
        success = await resume_service.delete_resume(resume_id, current_user.id)
        _check_success_or_raise_not_found()
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    else:
        return {"message": "Resume deleted successfully"}
