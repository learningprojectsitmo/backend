from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from sqlalchemy import select

from src.core.exceptions import NotFoundError, PermissionError, ValidationError
from src.model.project import Project, ProjectParticipation, ProjectType, StageTransition
from src.model.user import Role, User
from src.model.workspace import WorkSpaceParticipation
from src.schema.stage import (
    ProjectStageCreate,
    ProjectStageInfo,
    ProjectStageUpdate,
    ProjectTypeCreate,
    ProjectTypeFull,
    ProjectTypeUpdate,
    StageHistoryResponse,
    StageTransitionItem,
)
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.stage_repository import ProjectTypeRepository, StageTransitionRepository


class ProjectStageService(BaseService[Project, dict, dict]):
    """Сервис управления типами проектов, этапами и их переходами"""

    TEACHER_ROLES: ClassVar[set[str]] = {"teacher", "admin"}
    MANAGE_ROLES: ClassVar[set[str]] = {"teacher", "admin", "manager"}

    def __init__(
        self,
        type_repository: ProjectTypeRepository,
        transition_repository: StageTransitionRepository,
    ) -> None:
        super().__init__(type_repository)  # type: ignore[arg-type]
        self._type_repository = type_repository
        self._transition_repository = transition_repository

    async def copy_system_types_to_workspace(self, workspace_id: int) -> int:
        """Скопировать системные типы проектов в пространство (идемпотентно)."""
        return await self._type_repository.copy_system_types_to_workspace(workspace_id)

    # ====== Workspace permission helpers ======

    async def _can_manage_workspace(self, workspace_id: int | None, user_id: int) -> bool:
        """Может ли пользователь управлять типами проектов в данном пространстве."""
        user = await self._type_repository.uow.session.get(User, user_id)
        if not user:
            return False
        role_name = user.role.name if user.role else ""
        if role_name in self.TEACHER_ROLES:
            return True
        if workspace_id is None:
            return False
        result = await self._type_repository.uow.session.execute(
            select(WorkSpaceParticipation, Role)
            .join(Role, Role.id == WorkSpaceParticipation.role_id)
            .where(
                WorkSpaceParticipation.workspace_id == workspace_id,
                WorkSpaceParticipation.participant_id == user_id,
            )
        )
        row = result.first()
        return bool(row and row[1].name in self.MANAGE_ROLES)

    def _ensure_type_belongs(self, ptype: ProjectType, workspace_id: int | None) -> None:
        if ptype.workspace_id != workspace_id:
            raise PermissionError("Project type does not belong to this workspace")

    # ====== ProjectType CRUD ======

    async def list_project_types(self, workspace_id: int | None = None) -> list[ProjectTypeFull]:
        """Получить список типов проектов (для пространства или системных) с этапами"""
        types = await self._type_repository.list_with_stages(workspace_id)
        return [
            ProjectTypeFull(
                id=t.id,
                name=t.name,
                description=t.description,
                stages=[self._stage_info(s) for s in (t.stages or [])],
            )
            for t in types
        ]

    async def get_project_type(self, type_id: int) -> ProjectTypeFull:
        ptype = await self._type_repository.get_by_id_with_stages(type_id)
        if not ptype:
            raise NotFoundError("Project type not found")
        return ProjectTypeFull(
            id=ptype.id,
            name=ptype.name,
            description=ptype.description,
            stages=[self._stage_info(s) for s in (ptype.stages or [])],
        )

    @staticmethod
    def _stage_info(s) -> ProjectStageInfo:
        return ProjectStageInfo(
            id=s.id, name=s.name, order=s.order, requires_approval=s.requires_approval, is_current=False
        )

    async def create_project_type(
        self, data: ProjectTypeCreate, workspace_id: int | None, user_id: int
    ) -> ProjectTypeFull:
        if not await self._can_manage_workspace(workspace_id, user_id):
            raise PermissionError("Only admin/teacher can manage project types")
        saved = await self._type_repository.create(data)
        return ProjectTypeFull(id=saved.id, name=saved.name, description=saved.description, stages=[])

    async def update_project_type(
        self, type_id: int, workspace_id: int | None, data: ProjectTypeUpdate, user_id: int
    ) -> ProjectTypeFull:
        ptype = await self._type_repository.get_by_id(type_id)
        if not ptype:
            raise NotFoundError("Project type not found")
        if not await self._can_manage_workspace(ptype.workspace_id, user_id):
            raise PermissionError("Only admin/teacher can manage project types")
        self._ensure_type_belongs(ptype, workspace_id)
        await self._type_repository.update(type_id, data)
        return await self.get_project_type(type_id)

    async def delete_project_type(self, type_id: int, workspace_id: int | None, user_id: int) -> bool:
        ptype = await self._type_repository.get_by_id(type_id)
        if not ptype:
            return False
        if not await self._can_manage_workspace(ptype.workspace_id, user_id):
            raise PermissionError("Only admin/teacher can manage project types")
        self._ensure_type_belongs(ptype, workspace_id)
        await self._type_repository.delete(type_id)
        return True

    # ====== Stage CRUD ======

    async def add_stage(
        self, type_id: int, workspace_id: int | None, data: ProjectStageCreate, user_id: int
    ) -> ProjectTypeFull:
        ptype = await self._type_repository.get_by_id(type_id)
        if not ptype:
            raise NotFoundError("Project type not found")
        if not await self._can_manage_workspace(workspace_id, user_id):
            raise PermissionError("Only admin/teacher can manage project stages")
        self._ensure_type_belongs(ptype, workspace_id)
        await self._type_repository.create_stage(type_id, data)
        return await self.get_project_type(type_id)

    async def update_stage(
        self, type_id: int, stage_id: int, workspace_id: int | None, data: ProjectStageUpdate, user_id: int
    ) -> ProjectTypeFull:
        ptype = await self._type_repository.get_by_id(type_id)
        if not ptype:
            raise NotFoundError("Project type not found")
        if not await self._can_manage_workspace(workspace_id, user_id):
            raise PermissionError("Only admin/teacher can manage project stages")
        self._ensure_type_belongs(ptype, workspace_id)
        stage = await self._type_repository.update_stage(stage_id, data)
        if not stage:
            raise NotFoundError("Stage not found")
        if stage.project_type_id != type_id:
            raise ValidationError("Stage does not belong to this project type")
        return await self.get_project_type(type_id)

    async def remove_stage(
        self, type_id: int, stage_id: int, workspace_id: int | None, user_id: int
    ) -> bool:
        ptype = await self._type_repository.get_by_id(type_id)
        if not ptype:
            raise NotFoundError("Project type not found")
        if not await self._can_manage_workspace(workspace_id, user_id):
            raise PermissionError("Only admin/teacher can manage project stages")
        self._ensure_type_belongs(ptype, workspace_id)
        stage = await self._type_repository.get_stage_by_id(stage_id)
        if not stage:
            return False
        if stage.project_type_id != type_id:
            raise ValidationError("Stage does not belong to this project type")
        await self._type_repository.delete_stage(stage_id)
        return True

    # ====== Workflow: advance / approve / reject ======

    async def _get_project(self, project_id: int) -> Project:
        return await self._type_repository.uow.session.get(Project, project_id)

    async def _get_ordered_stages(self, project: Project) -> list:
        ptype = project.project_type
        if not ptype:
            raise ValidationError("Project has no type set; stages are not available")
        return sorted(ptype.stages or [], key=lambda s: s.order)

    async def _ensure_can_advance(self, project: Project, user_id: int) -> None:
        if project.author_id != user_id:
            raise PermissionError("Only project author can advance the project")

    async def _is_teacher(self, project: Project, user_id: int) -> bool:
        user = await self._type_repository.uow.session.get(User, user_id)
        if not user:
            return False
        role_name = user.role.name if user.role else ""
        if role_name in self.TEACHER_ROLES:
            return True
        # Для workspace проверяем роль преподавателя в этом пространстве
        if project.workspace_id:
            result = await self._type_repository.uow.session.execute(
                select(WorkSpaceParticipation, Role)
                .join(Role, Role.id == WorkSpaceParticipation.role_id)
                .where(
                    WorkSpaceParticipation.workspace_id == project.workspace_id,
                    WorkSpaceParticipation.participant_id == user_id,
                )
            )
            row = result.first()
            if row and row[1].name in ("teacher", "admin", "manager"):
                return True
        return False

    async def advance_stage(self, project_id: int, user_id: int) -> Project:
        """Автор инициирует переход на следующий этап."""
        project = await self._get_project(project_id)
        if not project:
            raise NotFoundError("Project not found")
        await self._ensure_can_advance(project, user_id)

        stages = await self._get_ordered_stages(project)
        if not stages:
            raise ValidationError("No stages defined for this project type")

        if project.stage_pending_approval:
            raise ValidationError("Current stage is awaiting approval; cannot advance")

        current_id = project.current_stage_id
        current_order = None
        for i, s in enumerate(stages):
            if s.id == current_id:
                current_order = i
                break

        # Первый этап (не задан) -> переходим на первый
        if current_id is None:
            target = stages[0]
            return await self._apply_advance(project, None, target, user_id)

        if current_order is None:
            raise ValidationError("Project current stage is not among its type stages")

        # Последний этап — проект завершён, двигаться некуда
        if current_order == len(stages) - 1:
            raise ValidationError("Project already on the final stage")

        target = stages[current_order + 1]
        return await self._apply_advance(project, stages[current_order], target, user_id)

    async def _apply_advance(self, project: Project, from_stage, target, user_id: int) -> Project:
        await self._transition_repository.create_transition(
            project_id=project.id,
            stage_id=target.id,
            from_stage_id=from_stage.id if from_stage else None,
            actor_id=user_id,
            action="advance",
        )
        project.current_stage_id = target.id
        if target.requires_approval:
            project.stage_pending_approval = True
        else:
            project.stage_pending_approval = False
        await self._type_repository.uow.session.flush()
        return project

    async def approve_stage(self, project_id: int, user_id: int) -> Project:
        """Преподаватель утверждает текущий этап."""
        project = await self._get_project(project_id)
        if not project:
            raise NotFoundError("Project not found")
        if not await self._is_teacher(project, user_id):
            raise PermissionError("Only a teacher can approve project stages")
        if not project.stage_pending_approval:
            raise ValidationError("Stage is not awaiting approval")
        if not project.current_stage_id:
            raise ValidationError("Project has no current stage")

        await self._transition_repository.create_transition(
            project_id=project.id,
            stage_id=project.current_stage_id,
            from_stage_id=None,
            actor_id=user_id,
            action="approve",
        )
        project.stage_pending_approval = False
        await self._type_repository.uow.session.flush()
        return project

    async def reject_stage(self, project_id: int, user_id: int, comment: str | None = None) -> Project:
        """Преподаватель отклоняет текущий этап — возврат на предыдущий."""
        project = await self._get_project(project_id)
        if not project:
            raise NotFoundError("Project not found")
        if not await self._is_teacher(project, user_id):
            raise PermissionError("Only a teacher can reject project stages")
        if not project.stage_pending_approval:
            raise ValidationError("Stage is not awaiting approval")
        if not project.current_stage_id:
            raise ValidationError("Project has no current stage")

        stages = await self._get_ordered_stages(project)
        current_id = project.current_stage_id
        current_order = next((i for i, s in enumerate(stages) if s.id == current_id), None)
        if current_order is None:
            raise ValidationError("Project current stage is not among its type stages")

        await self._transition_repository.create_transition(
            project_id=project.id,
            stage_id=project.current_stage_id,
            from_stage_id=project.current_stage_id,
            actor_id=user_id,
            action="reject",
            comment=comment,
        )

        # Возврат на предыдущий этап (или снятие pending, если это первый)
        if current_order > 0:
            project.current_stage_id = stages[current_order - 1].id
        project.stage_pending_approval = False
        await self._type_repository.uow.session.flush()
        return project

    async def get_stage_history(self, project_id: int, user_id: int) -> StageHistoryResponse:
        """Получить историю переходов этапов проекта (участники/автор/преподаватель)."""
        project = await self._get_project(project_id)
        if not project:
            raise NotFoundError("Project not found")
        # Доступ: автор, участник, преподаватель, админ
        if project.author_id != user_id:
            participant = await self._type_repository.uow.session.execute(
                select(WorkSpaceParticipation).where(
                    WorkSpaceParticipation.workspace_id == project.workspace_id,
                    WorkSpaceParticipation.participant_id == user_id,
                )
            )
            in_project = await self._type_repository.uow.session.execute(
                select(ProjectParticipation).where(
                    ProjectParticipation.project_id == project_id,
                    ProjectParticipation.participant_id == user_id,
                )
            )
            is_teacher = await self._is_teacher(project, user_id)
            if not in_project.scalar_one_or_none() and not is_teacher and not participant.scalar_one_or_none():
                raise PermissionError("You do not have access to this project's stage history")

        transitions = await self._transition_repository.get_transitions_by_project(project_id)
        items = []
        for t in transitions:
            actor = t.actor if isinstance(t, StageTransition) else None
            actor_name = ""
            if actor:
                actor_name = f"{actor.first_name} {actor.last_name or ''}".strip()
            items.append(
                StageTransitionItem(
                    id=t.id,
                    project_id=t.project_id,
                    stage_name=t.stage.name if t.stage else "",
                    from_stage_name=t.from_stage.name if t.from_stage else None,
                    action=t.action,
                    comment=t.comment,
                    actor_name=actor_name,
                    created_at=t.created_at,
                )
            )
        return StageHistoryResponse(items=items, total=len(items))
