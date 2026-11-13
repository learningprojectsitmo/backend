from __future__ import annotations

from src.core.exceptions import NotFoundError, PermissionError
from src.model.user import User
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.project_type_question import (
    ProjectTypeQuestionsRead,
    QuestionListReplace,
    QuestionRead,
    QuestionWrite,
    TemplateCode,
)
from src.services.question_template_service import QuestionTemplateService


class ProjectTypeQuestionService:
    def __init__(self, repository: ProjectTypeQuestionRepository, templates: QuestionTemplateService) -> None:
        self._repository = repository
        self._templates = templates

    async def _require_scope(self, workspace_id: int, type_id: int, user: User, *, write: bool = False) -> None:
        workspace = await self._repository.get_workspace(workspace_id)
        ptype = await self._repository.get_type(workspace_id, type_id)
        if workspace is None or ptype is None:
            raise NotFoundError("Project type not found in this workspace")
        global_role = user.role.name if user.role else None
        if global_role != "admin":
            member, local_role = await self._repository.get_membership_role(workspace_id, user.id)
            if not member and workspace.author_id != user.id:
                raise NotFoundError("Workspace not found")
            if write and global_role != "teacher" and local_role not in {"teacher", "admin"}:
                raise PermissionError("Only workspace teacher/admin can manage questions")
        if write and await self._repository.get_type(workspace_id, type_id, lock=True) is None:
            raise NotFoundError("Project type not found in this workspace")

    @staticmethod
    def _response(type_id: int, questions: list) -> ProjectTypeQuestionsRead:
        return ProjectTypeQuestionsRead(
            project_type_id=type_id, questions=[QuestionRead.model_validate(q) for q in questions]
        )

    async def get_questions(self, workspace_id: int, type_id: int, user: User) -> ProjectTypeQuestionsRead:
        await self._require_scope(workspace_id, type_id, user)
        return self._response(type_id, await self._repository.list_questions(type_id))

    async def replace_questions(
        self, workspace_id: int, type_id: int, data: QuestionListReplace, user: User
    ) -> ProjectTypeQuestionsRead:
        await self._require_scope(workspace_id, type_id, user, write=True)
        return self._response(type_id, await self._repository.replace_questions(type_id, data))

    async def apply_template(
        self, workspace_id: int, type_id: int, template_code: TemplateCode, user: User
    ) -> ProjectTypeQuestionsRead:
        template = self._templates.get_template(template_code)
        data = QuestionListReplace(
            questions=[
                QuestionWrite(text=q.text, description=q.description, levels=q.levels) for q in template.questions
            ]
        )
        return await self.replace_questions(workspace_id, type_id, data, user)
