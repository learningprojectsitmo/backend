from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.exceptions import NotFoundError
from src.core.uow import IUnitOfWork
from src.model.project import ProjectType
from src.model.project_type_question import ProjectTypeQuestion, ProjectTypeQuestionLevel
from src.model.user import Role
from src.model.workspace import WorkSpace, WorkSpaceParticipation
from src.schema.project_type_question import QuestionListReplace


class ProjectTypeQuestionRepository:
    def __init__(self, uow: IUnitOfWork) -> None:
        self.uow = uow

    async def get_workspace(self, workspace_id: int) -> WorkSpace | None:
        return await self.uow.session.get(WorkSpace, workspace_id)

    async def get_type(self, workspace_id: int, type_id: int, *, lock: bool = False) -> ProjectType | None:
        query = select(ProjectType).where(ProjectType.id == type_id, ProjectType.workspace_id == workspace_id)
        if lock:
            query = query.with_for_update()
        return (await self.uow.session.execute(query)).scalar_one_or_none()

    async def get_membership_role(self, workspace_id: int, user_id: int) -> tuple[bool, str | None]:
        query = (
            select(Role.name)
            .select_from(WorkSpaceParticipation)
            .outerjoin(Role, Role.id == WorkSpaceParticipation.role_id)
            .where(
                WorkSpaceParticipation.workspace_id == workspace_id, WorkSpaceParticipation.participant_id == user_id
            )
        )
        row = (await self.uow.session.execute(query)).first()
        return (True, row[0]) if row is not None else (False, None)

    async def list_questions(self, type_id: int) -> list[ProjectTypeQuestion]:
        query = (
            select(ProjectTypeQuestion)
            .where(ProjectTypeQuestion.project_type_id == type_id)
            .options(selectinload(ProjectTypeQuestion.levels))
            .order_by(ProjectTypeQuestion.position)
            .execution_options(populate_existing=True)
        )
        return list((await self.uow.session.execute(query)).scalars().all())

    async def replace_questions(self, type_id: int, data: QuestionListReplace) -> list[ProjectTypeQuestion]:
        """Replace under the caller's scoped parent lock; commit belongs to its UoW."""
        existing = {q.id: q for q in await self.list_questions(type_id)}
        requested = {q.id for q in data.questions if q.id is not None}
        if not requested <= existing.keys():
            raise NotFoundError("Question does not belong to this project type")
        for qid, question in existing.items():
            if qid not in requested:
                await self.uow.session.delete(question)
        for position, item in enumerate(data.questions):
            question = existing.get(item.id)
            if question is None:
                question = ProjectTypeQuestion(project_type_id=type_id, position=position, text=item.text, levels=[])
                self.uow.session.add(question)
            question.text = item.text
            question.description = item.description
            question.position = position
            levels = {level.score: level for level in question.levels}
            for item_level in item.levels:
                if item_level.score in levels:
                    levels[item_level.score].description = item_level.description
                else:
                    question.levels.append(
                        ProjectTypeQuestionLevel(score=item_level.score, description=item_level.description)
                    )
        await self.uow.session.flush()
        return await self.list_questions(type_id)
