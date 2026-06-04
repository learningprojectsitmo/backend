from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.container import get_resume_service
from src.core.dependencies import get_current_user, setup_audit
from src.core.exceptions import PermissionError
from src.model.user import User
from src.schema.resume import (
    ResumeCreate,
    ResumeDetail,
    ResumeEducationCreate,
    ResumeEducationFull,
    ResumeEducationUpdate,
    ResumeExperienceCreate,
    ResumeExperienceFull,
    ResumeExperienceUpdate,
    ResumeFull,
    ResumeInterestCreate,
    ResumeInterestFull,
    ResumeInterestUpdate,
    ResumeLanguageCreate,
    ResumeLanguageFull,
    ResumeLanguageUpdate,
    ResumeLinkCreate,
    ResumeLinkFull,
    ResumeLinkUpdate,
    ResumeListResponse,
    ResumeSkillCreate,
    ResumeSkillFull,
    ResumeSkillUpdate,
    ResumeUpdate,
)
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


@resume_router.get("/{resume_id}/detail", response_model=ResumeDetail)
async def fetch_resume_detail(
    resume_id: int,
    resume_service: ResumeService = Depends(get_resume_service),
    _current_user: User = Depends(get_current_user),
) -> ResumeDetail:
    """Получить полное резюме со всеми секциями"""
    detail = await resume_service.get_resume_detail(resume_id)
    if not detail:
        raise HTTPException(status_code=404, detail="There is no resume with that id!")
    return detail


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
    _audit=Depends(setup_audit),
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
    _audit=Depends(setup_audit),
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


@resume_router.get("/me", response_model=ResumeListResponse)
async def fetch_my_resumes(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeListResponse:
    """Получить резюме текущего пользователя с пагинацией"""
    resumes, total = await resume_service.get_user_resumes_paginated(current_user.id, page, limit)
    items = [ResumeFull.model_validate(r) for r in resumes]
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    return ResumeListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


# ─── Resume Link CRUD ────────────────────────────────────────────────────


@resume_router.post("/{resume_id}/links", response_model=ResumeLinkFull)
async def create_resume_link(
    resume_id: int,
    link_data: ResumeLinkCreate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeLinkFull:
    """Создать ссылку портфолио в резюме"""
    try:
        link = await resume_service.create_resume_link(resume_id, link_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    else:
        return ResumeLinkFull.model_validate(link)


@resume_router.put("/links/{link_id}", response_model=ResumeLinkFull)
async def update_resume_link(
    link_id: int,
    link_data: ResumeLinkUpdate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeLinkFull:
    """Обновить ссылку портфолио в резюме"""
    try:
        link = await resume_service.update_resume_link(link_id, link_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    return ResumeLinkFull.model_validate(link)


@resume_router.delete("/links/{link_id}")
async def delete_resume_link(
    link_id: int,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Удалить ссылку портфолио из резюме"""
    try:
        success = await resume_service.delete_resume_link(link_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not success:
        raise HTTPException(status_code=404, detail="Link not found")
    return {"message": "Link deleted successfully"}


# ─── Resume Education CRUD ────────────────────────────────────────────────


@resume_router.post("/{resume_id}/educations", response_model=ResumeEducationFull)
async def create_resume_education(
    resume_id: int,
    edu_data: ResumeEducationCreate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeEducationFull:
    """Создать запись об образовании в резюме"""
    try:
        edu = await resume_service.create_resume_education(resume_id, edu_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    else:
        return ResumeEducationFull.model_validate(edu)


@resume_router.put("/educations/{edu_id}", response_model=ResumeEducationFull)
async def update_resume_education(
    edu_id: int,
    edu_data: ResumeEducationUpdate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeEducationFull:
    """Обновить запись об образовании в резюме"""
    try:
        edu = await resume_service.update_resume_education(edu_id, edu_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not edu:
        raise HTTPException(status_code=404, detail="Education not found")
    return ResumeEducationFull.model_validate(edu)


@resume_router.delete("/educations/{edu_id}")
async def delete_resume_education(
    edu_id: int,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Удалить запись об образовании из резюме"""
    try:
        success = await resume_service.delete_resume_education(edu_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not success:
        raise HTTPException(status_code=404, detail="Education not found")
    return {"message": "Education deleted successfully"}


# ─── Resume Language CRUD ──────────────────────────────────────────────────


@resume_router.post("/{resume_id}/languages", response_model=ResumeLanguageFull)
async def create_resume_language(
    resume_id: int,
    lang_data: ResumeLanguageCreate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeLanguageFull:
    """Создать язык в резюме"""
    try:
        lang = await resume_service.create_resume_language(resume_id, lang_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    else:
        return ResumeLanguageFull.model_validate(lang)


@resume_router.put("/languages/{lang_id}", response_model=ResumeLanguageFull)
async def update_resume_language(
    lang_id: int,
    lang_data: ResumeLanguageUpdate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeLanguageFull:
    """Обновить язык в резюме"""
    try:
        lang = await resume_service.update_resume_language(lang_id, lang_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not lang:
        raise HTTPException(status_code=404, detail="Language not found")
    return ResumeLanguageFull.model_validate(lang)


# ─── Resume Experience CRUD ────────────────────────────────────────────────


@resume_router.post("/{resume_id}/experiences", response_model=ResumeExperienceFull)
async def create_resume_experience(
    resume_id: int,
    exp_data: ResumeExperienceCreate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeExperienceFull:
    """Создать запись об опыте в резюме"""
    try:
        exp = await resume_service.create_resume_experience(resume_id, exp_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    else:
        return ResumeExperienceFull.model_validate(exp)


@resume_router.put("/experiences/{exp_id}", response_model=ResumeExperienceFull)
async def update_resume_experience(
    exp_id: int,
    exp_data: ResumeExperienceUpdate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeExperienceFull:
    """Обновить запись об опыте в резюме"""
    try:
        exp = await resume_service.update_resume_experience(exp_id, exp_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    return ResumeExperienceFull.model_validate(exp)


@resume_router.delete("/experiences/{exp_id}")
async def delete_resume_experience(
    exp_id: int,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Удалить запись об опыте из резюме"""
    try:
        success = await resume_service.delete_resume_experience(exp_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not success:
        raise HTTPException(status_code=404, detail="Experience not found")
    return {"message": "Experience deleted successfully"}


# ─── ResumeSkill CRUD ──────────────────────────────────────────────────────


@resume_router.post("/{resume_id}/skills", response_model=ResumeSkillFull)
async def create_resume_skill(
    resume_id: int,
    skill_data: ResumeSkillCreate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeSkillFull:
    """Добавить навык в резюме"""
    try:
        skill = await resume_service.create_resume_skill(resume_id, skill_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    else:
        return ResumeSkillFull.model_validate(skill)


@resume_router.put("/skills/{skill_id}", response_model=ResumeSkillFull)
async def update_resume_skill(
    skill_id: int,
    skill_data: ResumeSkillUpdate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeSkillFull:
    """Обновить навык в резюме"""
    try:
        skill = await resume_service.update_resume_skill(skill_id, skill_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return ResumeSkillFull.model_validate(skill)


@resume_router.delete("/skills/{skill_id}")
async def delete_resume_skill(
    skill_id: int,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Удалить навык из резюме"""
    try:
        success = await resume_service.delete_resume_skill(skill_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not success:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"message": "Skill deleted successfully"}


# ─── ResumeInterest CRUD ──────────────────────────────────────────────────


@resume_router.post("/{resume_id}/interests", response_model=ResumeInterestFull)
async def create_resume_interest(
    resume_id: int,
    interest_data: ResumeInterestCreate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeInterestFull:
    """Добавить интерес в резюме"""
    try:
        interest = await resume_service.create_resume_interest(resume_id, interest_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    else:
        return ResumeInterestFull.model_validate(interest)


@resume_router.put("/interests/{interest_id}", response_model=ResumeInterestFull)
async def update_resume_interest(
    interest_id: int,
    interest_data: ResumeInterestUpdate,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> ResumeInterestFull:
    """Обновить интерес в резюме"""
    try:
        interest = await resume_service.update_resume_interest(interest_id, interest_data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not interest:
        raise HTTPException(status_code=404, detail="Interest not found")
    return ResumeInterestFull.model_validate(interest)


@resume_router.delete("/interests/{interest_id}")
async def delete_resume_interest(
    interest_id: int,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Удалить интерес из резюме"""
    try:
        success = await resume_service.delete_resume_interest(interest_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not success:
        raise HTTPException(status_code=404, detail="Interest not found")
    return {"message": "Interest deleted successfully"}


@resume_router.delete("/languages/{lang_id}")
async def delete_resume_language(
    lang_id: int,
    resume_service: ResumeService = Depends(get_resume_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Удалить язык из резюме"""
    try:
        success = await resume_service.delete_resume_language(lang_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not success:
        raise HTTPException(status_code=404, detail="Language not found")
    return {"message": "Language deleted successfully"}
