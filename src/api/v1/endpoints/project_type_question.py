from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from src.core.container import get_project_type_question_service, get_question_template_service
from src.core.dependencies import get_current_user, setup_audit
from src.model.user import User
from src.schema.project_type_question import (
    ProjectTypeQuestionsRead,
    QuestionListReplace,
    QuestionTemplateRead,
    TemplateApply,
)
from src.services.project_type_question_service import ProjectTypeQuestionService
from src.services.question_template_service import QuestionTemplateService

question_template_router = APIRouter(
    prefix="/assessment/question-templates",
    tags=["assessment-question-template"],
    dependencies=[Depends(get_current_user)],
)
project_type_question_router = APIRouter(
    prefix="/workspaces/{workspace_id}/project-types/{type_id}/questions",
    tags=["project-type-question"],
    dependencies=[Depends(setup_audit)],
)


@question_template_router.get("", response_model=list[QuestionTemplateRead])
async def list_question_templates(
    service: QuestionTemplateService = Depends(get_question_template_service),
) -> tuple[QuestionTemplateRead, ...]:
    return service.list_templates()


@project_type_question_router.get("", response_model=ProjectTypeQuestionsRead)
async def get_questions(
    workspace_id: int = Path(ge=1),
    type_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    service: ProjectTypeQuestionService = Depends(get_project_type_question_service),
) -> ProjectTypeQuestionsRead:
    return await service.get_questions(workspace_id, type_id, current_user)


@project_type_question_router.put("", response_model=ProjectTypeQuestionsRead)
async def replace_questions(
    data: QuestionListReplace,
    workspace_id: int = Path(ge=1),
    type_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    service: ProjectTypeQuestionService = Depends(get_project_type_question_service),
) -> ProjectTypeQuestionsRead:
    return await service.replace_questions(workspace_id, type_id, data, current_user)


@project_type_question_router.post("/apply-template", response_model=ProjectTypeQuestionsRead)
async def apply_template(
    data: TemplateApply,
    workspace_id: int = Path(ge=1),
    type_id: int = Path(ge=1),
    current_user: User = Depends(get_current_user),
    service: ProjectTypeQuestionService = Depends(get_project_type_question_service),
) -> ProjectTypeQuestionsRead:
    return await service.apply_template(workspace_id, type_id, data.template_code, current_user)
