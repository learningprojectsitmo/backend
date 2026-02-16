from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.container import get_grading_criteria_service
from src.services.grading_criteria_service import GradingCriteriaService
from src.schema.grading_criteria import (
    GradingCriteriaCreate,
    GradingCriteriaUpdate,
    GradingCriteriaResponse,
    GradingCriteriaListResponse,
)
from src.model.models import User




router = APIRouter(prefix="/grading-criteria", tags=["Grading Criteria"])


@router.post(
    "/",
    response_model=GradingCriteriaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать критерий оценивания"
)
async def create_criteria(
        criteria_data: GradingCriteriaCreate,
        service: GradingCriteriaService = Depends(get_grading_criteria_service),
        # current_user: User = Depends(get_current_user)
):
    """
    Создать новый критерий оценивания (только для преподавателей)

    - **project_type_id**: ID типа проекта
    - **name**: Название критерия
    - **max_score**: Максимальный балл (1-100)
    - **weight**: Вес критерия (1-5)
    - **order_index**: Порядок отображения
    """

    # if current_user.role != "teacher":
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Only teachers can create grading criteria"
    #     )

    criteria = await service.create_criteria(criteria_data)
    return GradingCriteriaResponse.model_validate(criteria)


@router.get(
    "/project-type/{project_type_id}",
    response_model=GradingCriteriaListResponse,
    summary="Получить критерии для типа проекта"
)
async def get_criteria_by_project_type(
        project_type_id: int,
        service: GradingCriteriaService = Depends(get_grading_criteria_service),
        # current_user: User = Depends(get_current_user)
):
    """
    Получить все критерии оценивания для указанного типа проекта

    Возвращает список критериев с метаданными:
    - Общее количество критериев
    - Суммарный максимальный балл
    - Список всех критериев отсортированный по order_index
    """
    return await service.get_by_project_type(project_type_id)


@router.get(
    "/{criteria_id}",
    response_model=GradingCriteriaResponse,
    summary="Получить критерий по ID"
)
async def get_criteria(
        criteria_id: int,
        service: GradingCriteriaService = Depends(get_grading_criteria_service),
        # current_user: User = Depends(get_current_user)
):
    """Получить детальную информацию о критерии по его ID"""
    criteria = await service.get_by_id(criteria_id)
    return GradingCriteriaResponse.model_validate(criteria)


@router.patch(
    "/{criteria_id}",
    response_model=GradingCriteriaResponse,
    summary="Обновить критерий"
)
async def update_criteria(
        criteria_id: int,
        criteria_data: GradingCriteriaUpdate,
        service: GradingCriteriaService = Depends(get_grading_criteria_service),
        # current_user: User = Depends(get_current_user)
):
    """
    Обновить критерий оценивания (только для преподавателей)

    Обновляются только переданные поля.
    Можно обновить:
    - name
    - description
    - max_score
    - weight
    - order_index
    """
    # if current_user.role != "teacher":
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Only teachers can update grading criteria"
    #     )

    criteria = await service.update_criteria(criteria_id, criteria_data)
    return GradingCriteriaResponse.model_validate(criteria)


@router.delete(
    "/{criteria_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить критерий"
)
async def delete_criteria(
        criteria_id: int,
        service: GradingCriteriaService = Depends(get_grading_criteria_service),
        # current_user: User = Depends(get_current_user)
):
    """Удалить критерий оценивания (только для преподавателей)"""
    # if current_user.role != "teacher":
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Only teachers can delete grading criteria"
    #     )

    await service.delete_criteria(criteria_id)


@router.get(
    "/project-type/{project_type_id}/total-score",
    summary="Получить максимальную сумму баллов"
)
async def get_total_max_score(
        project_type_id: int,
        service: GradingCriteriaService = Depends(get_grading_criteria_service),
        # current_user: User = Depends(get_current_user)
):
    """
    Получить суммарный максимальный балл для типа проекта

    Вычисляется как: sum(max_score * weight) для всех критериев
    """
    total = await service.get_total_max_score(project_type_id)
    return {
        "project_type_id": project_type_id,
        "total_max_score": total
    }
