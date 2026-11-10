from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from src.core.container import get_rubric_catalog_service
from src.core.dependencies import get_current_user
from src.schema.rubric import RubricRead
from src.services.rubric_catalog_service import RubricCatalogService

rubric_router = APIRouter(
    prefix="/assessment/rubrics",
    tags=["assessment-rubric"],
    dependencies=[Depends(get_current_user)],
)


@rubric_router.get("", response_model=list[RubricRead])
async def list_rubrics(service: RubricCatalogService = Depends(get_rubric_catalog_service)) -> tuple[RubricRead, ...]:
    """Return the initial version of each assessment category."""
    return service.list_rubrics()


@rubric_router.get("/{assessment_kind}/versions/{version}", response_model=RubricRead)
async def get_rubric(
    assessment_kind: str,
    version: int = Path(ge=1),
    service: RubricCatalogService = Depends(get_rubric_catalog_service),
) -> RubricRead:
    """Return a fixed rubric version, including every level explanation."""
    return service.get_rubric(assessment_kind, version)
