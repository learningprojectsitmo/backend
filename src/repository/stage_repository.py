from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.uow import IUnitOfWork
from src.model.project import ProjectStage, ProjectType, StageTransition
from src.repository.base_repository import BaseRepository
from src.schema.stage import ProjectStageCreate, ProjectStageUpdate, ProjectTypeCreate, ProjectTypeUpdate


class ProjectTypeRepository(BaseRepository[ProjectType, ProjectTypeCreate, ProjectTypeUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = ProjectType

    async def get_by_id_with_stages(self, id: int) -> ProjectType | None:
        query = select(ProjectType).where(ProjectType.id == id).options(selectinload(ProjectType.stages))
        result = await self.uow.session.execute(query)
        return result.scalar_one_or_none()

    async def list_with_stages(self, workspace_id: int | None = None) -> list[ProjectType]:
        query = select(ProjectType)
        if workspace_id is not None:
            query = query.where(ProjectType.workspace_id == workspace_id)
        query = query.options(selectinload(ProjectType.stages)).order_by(ProjectType.id)
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def get_stage_by_id(self, stage_id: int) -> ProjectStage | None:
        result = await self.uow.session.execute(select(ProjectStage).where(ProjectStage.id == stage_id))
        return result.scalar_one_or_none()

    async def create_stage(self, project_type_id: int, data: ProjectStageCreate) -> ProjectStage:
        stage = ProjectStage(
            project_type_id=project_type_id,
            name=data.name,
            order=data.order,
            requires_approval=data.requires_approval,
            duration_days=data.duration_days,
        )
        self.uow.session.add(stage)
        await self.uow.session.flush()
        return stage

    async def update_stage(self, stage_id: int, data: ProjectStageUpdate) -> ProjectStage | None:
        stage = await self.get_stage_by_id(stage_id)
        if not stage:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(stage, field, value)
        await self.uow.session.flush()
        return stage

    async def delete_stage(self, stage_id: int) -> bool:
        stage = await self.get_stage_by_id(stage_id)
        if not stage:
            return False
        await self.uow.session.delete(stage)
        await self.uow.session.flush()
        return True

    async def copy_system_types_to_workspace(self, workspace_id: int) -> int:
        """Скопировать системные типы (workspace_id IS NULL) как шаблоны в пространство."""
        system_types = await self.uow.session.execute(
            select(ProjectType).where(ProjectType.workspace_id.is_(None)).options(selectinload(ProjectType.stages))
        )
        count = 0
        for st in system_types.scalars().all():
            existing = await self.uow.session.execute(
                select(ProjectType).where(
                    ProjectType.workspace_id == workspace_id,
                    ProjectType.name == st.name,
                )
            )
            if existing.scalar_one_or_none():
                continue
            new_type = ProjectType(
                workspace_id=workspace_id,
                name=st.name,
                description=st.description,
            )
            self.uow.session.add(new_type)
            await self.uow.session.flush()
            for idx, stage in enumerate(sorted(st.stages or [], key=lambda s: s.order)):
                self.uow.session.add(
                    ProjectStage(
                        project_type_id=new_type.id,
                        name=stage.name,
                        order=idx,
                        requires_approval=stage.requires_approval,
                        duration_days=stage.duration_days,
                    )
                )
            await self.uow.session.flush()
            count += 1
        return count


class StageTransitionRepository(BaseRepository[StageTransition, dict, dict]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = StageTransition

    async def create_transition(
        self,
        project_id: int,
        stage_id: int,
        actor_id: int,
        action: str,
        from_stage_id: int | None = None,
        comment: str | None = None,
    ) -> StageTransition:
        transition = StageTransition(
            project_id=project_id,
            stage_id=stage_id,
            from_stage_id=from_stage_id,
            action=action,
            comment=comment,
            actor_id=actor_id,
        )
        self.uow.session.add(transition)
        await self.uow.session.flush()
        return transition

    async def get_transitions_by_project(self, project_id: int) -> list[StageTransition]:
        query = (
            select(StageTransition)
            .where(StageTransition.project_id == project_id)
            .options(
                selectinload(StageTransition.stage),
                selectinload(StageTransition.from_stage),
                selectinload(StageTransition.actor),
            )
            .order_by(StageTransition.created_at.desc())
        )
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())
