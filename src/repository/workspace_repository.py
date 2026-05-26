from __future__ import annotations

from sqlalchemy import Date, cast, func, or_, select
from sqlalchemy.orm import selectinload

from src.core.uow import IUnitOfWork
from src.model.project import Project, ProjectParticipation
from src.model.resume import Resume
from src.model.settings import SpaceSettings
from src.model.user import User
from src.model.workspace import WorkSpace, WorkSpaceCategories, WorkSpaceParticipation
from src.repository.base_repository import BaseRepository
from src.schema.workspace import WorkSpaceCreate, WorkSpaceUpdate


class WorkSpaceRepository(BaseRepository[WorkSpace, WorkSpaceCreate, WorkSpaceUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = WorkSpace

    async def get_by_author_id(self, author_id: int) -> list[WorkSpace]:
        """Получить все workspace по author_id"""
        query = select(WorkSpace).where(WorkSpace.author_id == author_id).options(selectinload(WorkSpace.category))
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def get_by_status_id(self, status_id: int) -> list[WorkSpace]:
        """Получить все workspace по status_id"""
        query = select(WorkSpace).where(WorkSpace.status_id == status_id).options(selectinload(WorkSpace.category))
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def get_workspaces_with_stats(self, skip: int = 0, limit: int = 10) -> tuple[list[WorkSpace], int]:
        """Получить workspace с подсчетом проектов и участников"""
        total_result = await self.uow.session.execute(select(func.count()).select_from(WorkSpace))
        total = total_result.scalar()

        query = (
            select(WorkSpace).options(selectinload(WorkSpace.category)).order_by(WorkSpace.id).offset(skip).limit(limit)
        )
        workspaces_result = await self.uow.session.execute(query)
        workspaces = list(workspaces_result.scalars().all())

        return workspaces, total

    async def add_participation(self, workspace_id: int, participant_id: int) -> None:
        participation = WorkSpaceParticipation(
            workspace_id=workspace_id,
            participant_id=participant_id,
        )
        self.uow.session.add(participation)

    async def get_participants_count(self, workspace_id: int) -> int:
        result = await self.uow.session.execute(
            select(func.count()).where(WorkSpaceParticipation.workspace_id == workspace_id)
        )
        return result.scalar()

    async def get_all_categories(self) -> list[WorkSpaceCategories]:
        result = await self.uow.session.execute(select(WorkSpaceCategories).order_by(WorkSpaceCategories.id))
        return list(result.scalars().all())

    async def get_category_name(self, category_id: int) -> str | None:
        result = await self.uow.session.execute(
            select(WorkSpaceCategories).where(WorkSpaceCategories.id == category_id)
        )
        category = result.scalar_one_or_none()
        return category.name if category else None

    async def get_or_create_category(self, category_data: dict) -> WorkSpaceCategories:
        result = await self.uow.session.execute(
            select(WorkSpaceCategories).where(WorkSpaceCategories.name == category_data["name"])
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        category = WorkSpaceCategories(**category_data)
        self.uow.session.add(category)
        return category

    async def remove_participant(self, workspace_id: int, user_id: int) -> bool:
        """Удалить участника из workspace"""
        result = await self.uow.session.execute(
            select(WorkSpaceParticipation).where(
                WorkSpaceParticipation.workspace_id == workspace_id,
                WorkSpaceParticipation.participant_id == user_id,
            )
        )
        participation = result.scalar_one_or_none()
        if not participation:
            return False
        await self.uow.session.delete(participation)
        return True

    async def get_participants(
        self,
        workspace_id: int,
        skip: int = 0,
        limit: int = 10,
        search: str | None = None,
        project_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[list[dict], int]:
        """Получить участников workspace с пагинацией, поиском и фильтрацией"""

        user_name = func.concat_ws(" ", User.last_name, User.first_name, User.middle_name).label("name")

        # Подзапрос: проекты участника в этом workspace (агрегированные в массивы)
        user_projects_query = (
            select(
                ProjectParticipation.participant_id,
                func.array_agg(Project.id).label("project_ids"),
                func.array_agg(Project.name).label("project_names"),
            )
            .join(Project, Project.id == ProjectParticipation.project_id)
            .where(Project.workspace_id == workspace_id)
            .group_by(ProjectParticipation.participant_id)
        )
        user_projects = user_projects_query.subquery()

        # Подзапрос: первое резюме участника
        first_resume = (
            select(Resume.author_id, Resume.id.label("resume_id"))
            .distinct(Resume.author_id)
            .order_by(Resume.author_id, Resume.id)
            .subquery()
        )

        base_query = (
            select(
                WorkSpaceParticipation.id,
                WorkSpaceParticipation.participant_id.label("user_id"),
                user_name,
                User.email,
                User.tg_nickname,
                User.phone,
                user_projects.c.project_ids,
                user_projects.c.project_names,
                first_resume.c.resume_id,
                WorkSpaceParticipation.created_at,
            )
            .join(User, User.id == WorkSpaceParticipation.participant_id)
            .outerjoin(user_projects, user_projects.c.participant_id == WorkSpaceParticipation.participant_id)
            .outerjoin(first_resume, first_resume.c.author_id == WorkSpaceParticipation.participant_id)
            .where(WorkSpaceParticipation.workspace_id == workspace_id)
        )

        # Фильтры
        if search:
            base_query = base_query.where(
                or_(
                    User.first_name.ilike(f"%{search}%"),
                    User.last_name.ilike(f"%{search}%"),
                    User.middle_name.ilike(f"%{search}%"),
                    User.email.ilike(f"%{search}%"),
                    User.tg_nickname.ilike(f"%{search}%"),
                )
            )
        if project_id is not None:
            # Semi-join: только участники, состоящие в указанном проекте
            in_project = (
                select(ProjectParticipation.participant_id)
                .join(Project, Project.id == ProjectParticipation.project_id)
                .where(
                    ProjectParticipation.project_id == project_id,
                    Project.workspace_id == workspace_id,
                )
            )
            base_query = base_query.where(WorkSpaceParticipation.participant_id.in_(in_project))
        if date_from:
            base_query = base_query.where(cast(WorkSpaceParticipation.created_at, Date) >= cast(date_from, Date))
        if date_to:
            base_query = base_query.where(cast(WorkSpaceParticipation.created_at, Date) <= cast(date_to, Date))

        # Total count
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.uow.session.execute(count_query)
        total = total_result.scalar()

        # Paginated results
        query = base_query.order_by(WorkSpaceParticipation.created_at.desc()).offset(skip).limit(limit)
        result = await self.uow.session.execute(query)
        rows = result.mappings().all()

        items = []
        for row in rows:
            projects_list = []
            if row["project_ids"]:
                for pid, pname in zip(row["project_ids"], row["project_names"], strict=False):
                    projects_list.append({"id": pid, "title": pname})

            items.append(
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "name": row["name"] or "",
                    "avatar_url": None,
                    "projects": projects_list,
                    "role": "",
                    "contacts": {
                        "telegram": row["tg_nickname"] or None,
                        "email": row["email"] or None,
                        "linkedin": None,
                    },
                    "resume_url": f"/resume/{row['resume_id']}" if row["resume_id"] else "",
                    "created_at": str(row["created_at"]),
                }
            )

        return items, total

    async def get_workspaces_menu_data(self, user_id: int, skip: int = 0, limit: int = 10) -> tuple[list[dict], int]:
        """Получить workspace с подсчётом участников (только видимые пользователю)"""
        # Подзапрос для подсчёта участников по каждому workspace
        participants_count = (
            select(
                WorkSpaceParticipation.workspace_id,
                func.count(WorkSpaceParticipation.id).label("participants_count"),
            )
            .group_by(WorkSpaceParticipation.workspace_id)
            .subquery()
        )

        # Подзапрос для подсчёта проектов по каждому workspace
        projects_count = (
            select(
                Project.workspace_id,
                func.count(Project.id).label("projects_count"),
            )
            .where(Project.workspace_id.isnot(None))
            .group_by(Project.workspace_id)
            .subquery()
        )

        # Подзапрос для списка workspace, где пользователь — участник
        user_workspace_ids = select(WorkSpaceParticipation.workspace_id).where(
            WorkSpaceParticipation.participant_id == user_id
        )

        # Фильтр: публичные ИЛИ автор ИЛИ участник
        visible_filter = or_(
            SpaceSettings.visibility.is_(None),
            SpaceSettings.visibility == "public",
            WorkSpace.author_id == user_id,
            WorkSpace.id.in_(user_workspace_ids),
        )

        # Подсчёт видимых workspace
        count_query = (
            select(func.count())
            .select_from(WorkSpace)
            .outerjoin(SpaceSettings, WorkSpace.id == SpaceSettings.space_id)
            .where(visible_filter)
        )
        total_result = await self.uow.session.execute(count_query)
        total = total_result.scalar()

        # Основной запрос: сразу возвращаем поля, соответствующие schema.Space.
        query = (
            select(
                WorkSpace.id.label("id"),
                WorkSpace.name.label("title"),
                func.coalesce(projects_count.c.projects_count, 0).label("projectsCount"),
                func.coalesce(participants_count.c.participants_count, 0).label("membersCount"),
                func.coalesce(WorkSpace.color, WorkSpaceCategories.color, "#6366f1").label("color"),
                func.coalesce(WorkSpaceCategories.name, "General").label("category"),
                WorkSpace.category_id.label("category_id"),
                WorkSpace.description.label("description"),
                SpaceSettings.icon_url.label("icon_url"),
                WorkSpace.author_id.label("author_id"),
            )
            .outerjoin(participants_count, WorkSpace.id == participants_count.c.workspace_id)
            .outerjoin(projects_count, WorkSpace.id == projects_count.c.workspace_id)
            .outerjoin(WorkSpaceCategories, WorkSpace.category_id == WorkSpaceCategories.id)
            .outerjoin(SpaceSettings, WorkSpace.id == SpaceSettings.space_id)
            .where(visible_filter)
            .order_by(WorkSpace.id)
            .offset(skip)
            .limit(limit)
        )

        result = await self.uow.session.execute(query)
        return [dict(row) for row in result.mappings().all()], total
