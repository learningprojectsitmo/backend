from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.core.container import (
    get_education_service,
    get_language_service,
    get_portfolio_service,
    get_profile_service,
)
from src.core.dependencies import get_current_user
from src.core.exceptions import PermissionError
from src.model.user import User
from src.schema.education import EducationCreate, EducationFull, EducationUpdate
from src.schema.language import LanguageCreate, LanguageFull, LanguageUpdate
from src.schema.portfolio import PortfolioCreate, PortfolioFull, PortfolioUpdate
from src.schema.profile import ProfileResponse
from src.services.education_service import EducationService
from src.services.language_service import LanguageService
from src.services.portfolio_service import PortfolioService
from src.services.profile_service import ProfileService

profile_router = APIRouter(prefix="/profile", tags=["profile"])


@profile_router.get("/", response_model=ProfileResponse)
async def fetch_profile(
    current_user: User = Depends(get_current_user),
    profile_service: ProfileService = Depends(get_profile_service),
) -> ProfileResponse:
    """Получить профиль текущего пользователя"""
    try:
        return await profile_service.get_profile(current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ─── Portfolio CRUD ──────────────────────────────────────────────────────


@profile_router.get("/portfolio", response_model=list[PortfolioFull])
async def fetch_portfolio(
    current_user: User = Depends(get_current_user),
    portfolio_service: PortfolioService = Depends(get_portfolio_service),
) -> list[PortfolioFull]:
    """Получить список портфолио текущего пользователя"""
    items = await portfolio_service.get_by_user_id(current_user.id)
    return [PortfolioFull.model_validate(i) for i in items]


@profile_router.post("/portfolio", response_model=PortfolioFull)
async def create_portfolio(
    data: PortfolioCreate,
    current_user: User = Depends(get_current_user),
    portfolio_service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioFull:
    """Создать запись портфолио"""
    item = await portfolio_service.create_portfolio(data, current_user.id)
    return PortfolioFull.model_validate(item)


@profile_router.put("/portfolio/{item_id}", response_model=PortfolioFull)
async def update_portfolio(
    item_id: int,
    data: PortfolioUpdate,
    current_user: User = Depends(get_current_user),
    portfolio_service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioFull:
    """Обновить запись портфолио"""
    try:
        item = await portfolio_service.update_portfolio(item_id, data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not item:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return PortfolioFull.model_validate(item)


@profile_router.delete("/portfolio/{item_id}")
async def delete_portfolio(
    item_id: int,
    current_user: User = Depends(get_current_user),
    portfolio_service: PortfolioService = Depends(get_portfolio_service),
) -> dict[str, str]:
    """Удалить запись портфолио"""
    try:
        success = await portfolio_service.delete_portfolio(item_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not success:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return {"message": "Portfolio deleted successfully"}


# ─── Education CRUD ──────────────────────────────────────────────────────


@profile_router.get("/education", response_model=list[EducationFull])
async def fetch_education(
    current_user: User = Depends(get_current_user),
    education_service: EducationService = Depends(get_education_service),
) -> list[EducationFull]:
    """Получить список образования текущего пользователя"""
    items = await education_service.get_by_user_id(current_user.id)
    return [EducationFull.model_validate(i) for i in items]


@profile_router.post("/education", response_model=EducationFull)
async def create_education(
    data: EducationCreate,
    current_user: User = Depends(get_current_user),
    education_service: EducationService = Depends(get_education_service),
) -> EducationFull:
    """Создать запись об образовании"""
    item = await education_service.create_education(data, current_user.id)
    return EducationFull.model_validate(item)


@profile_router.put("/education/{item_id}", response_model=EducationFull)
async def update_education(
    item_id: int,
    data: EducationUpdate,
    current_user: User = Depends(get_current_user),
    education_service: EducationService = Depends(get_education_service),
) -> EducationFull:
    """Обновить запись об образовании"""
    try:
        item = await education_service.update_education(item_id, data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not item:
        raise HTTPException(status_code=404, detail="Education not found")
    return EducationFull.model_validate(item)


@profile_router.delete("/education/{item_id}")
async def delete_education(
    item_id: int,
    current_user: User = Depends(get_current_user),
    education_service: EducationService = Depends(get_education_service),
) -> dict[str, str]:
    """Удалить запись об образовании"""
    try:
        success = await education_service.delete_education(item_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not success:
        raise HTTPException(status_code=404, detail="Education not found")
    return {"message": "Education deleted successfully"}


# ─── Language CRUD ───────────────────────────────────────────────────────


@profile_router.get("/languages", response_model=list[LanguageFull])
async def fetch_languages(
    current_user: User = Depends(get_current_user),
    language_service: LanguageService = Depends(get_language_service),
) -> list[LanguageFull]:
    """Получить список языков текущего пользователя"""
    items = await language_service.get_by_user_id(current_user.id)
    return [LanguageFull.model_validate(i) for i in items]


@profile_router.post("/languages", response_model=LanguageFull)
async def create_language(
    data: LanguageCreate,
    current_user: User = Depends(get_current_user),
    language_service: LanguageService = Depends(get_language_service),
) -> LanguageFull:
    """Создать запись о языке"""
    item = await language_service.create_language(data, current_user.id)
    return LanguageFull.model_validate(item)


@profile_router.put("/languages/{item_id}", response_model=LanguageFull)
async def update_language(
    item_id: int,
    data: LanguageUpdate,
    current_user: User = Depends(get_current_user),
    language_service: LanguageService = Depends(get_language_service),
) -> LanguageFull:
    """Обновить запись о языке"""
    try:
        item = await language_service.update_language(item_id, data, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not item:
        raise HTTPException(status_code=404, detail="Language not found")
    return LanguageFull.model_validate(item)


@profile_router.delete("/languages/{item_id}")
async def delete_language(
    item_id: int,
    current_user: User = Depends(get_current_user),
    language_service: LanguageService = Depends(get_language_service),
) -> dict[str, str]:
    """Удалить запись о языке"""
    try:
        success = await language_service.delete_language(item_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    if not success:
        raise HTTPException(status_code=404, detail="Language not found")
    return {"message": "Language deleted successfully"}
