"""Verifiable source of project relationships for assessment.

Provides the single authoritative answer for:
- Who is the manager of a project?       → project.author_id
- Who are the students of a project?     → project_participation.participant_id
- Who are the teachers of the workspace? → workspace_participation with
  effective role teacher or admin (local role priority over global).

Explicitly rejects:
- Workspace.author_id as automatic teacher
- ProjectParticipation.role (free text) as trusted assessment role
- Cross-workspace ID substitution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import aliased

from src.core.exceptions import NotFoundError
from src.model.user import Role as RoleModel
from src.model.user import User
from src.model.workspace import WorkSpaceParticipation

if TYPE_CHECKING:
    from src.repository.project_repository import ProjectRepository
    from src.repository.workspace_repository import WorkspaceRepository


@dataclass(frozen=True)
class ProjectRelations:
    """Complete snapshot of project relationships at query time."""

    project_id: int
    workspace_id: int
    manager_id: int
    member_ids: list[int] = field(default_factory=list)
    workspace_teacher_ids: list[int] = field(default_factory=list)


class ProjectRelationsService:
    """Single verifiable source of project→person relationships.

    All methods validate workspace scope: a project belongs to exactly one
    workspace, and queries with a mismatched workspace_id raise NotFoundError.
    """

    def __init__(
        self,
        project_repository: ProjectRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self._project_repo = project_repository
        self._workspace_repo = workspace_repository

    async def get_manager_id(self, project_id: int, *, workspace_id: int) -> int:
        """Return the manager (author) of the project.

        Always ``project.author_id``. Raises ``NotFoundError`` when the
        project does not exist or belongs to a different workspace.
        """
        project = await self._require_project_in_workspace(project_id, workspace_id)
        return project.author_id

    async def get_member_ids(self, project_id: int, *, workspace_id: int) -> list[int]:
        """Return student/participant IDs for the project.

        Reads ``project_participation.participant_id`` only. The free-text
        ``ProjectParticipation.role`` column is intentionally ignored — it is
        not a trusted assessment role.
        """
        project = await self._require_project_in_workspace(project_id, workspace_id)
        return sorted(p.participant_id for p in project.participants)

    async def get_workspace_teacher_ids(self, workspace_id: int) -> list[int]:
        """Return user IDs with effective role teacher or admin in the workspace."""
        session = self._workspace_repo.uow.session

        local_role = aliased(RoleModel)
        global_role = aliased(RoleModel)

        stmt = (
            select(
                WorkSpaceParticipation.participant_id,
                local_role.name.label("local_role_name"),
                global_role.name.label("global_role_name"),
            )
            .join(User, User.id == WorkSpaceParticipation.participant_id)
            .outerjoin(local_role, local_role.id == WorkSpaceParticipation.role_id)
            .outerjoin(global_role, global_role.id == User.role_id)
            .where(WorkSpaceParticipation.workspace_id == workspace_id)
        )
        result = await session.execute(stmt)
        rows = result.all()

        teacher_ids: set[int] = set()
        for row in rows:
            effective = self._resolve_effective_role(
                local_role_name=row.local_role_name,
                global_role_name=row.global_role_name,
            )
            if effective in ("teacher", "admin"):
                teacher_ids.add(row.participant_id)

        return sorted(teacher_ids)

    async def is_workspace_teacher(self, user_id: int, *, workspace_id: int) -> bool:
        """Check whether *user_id* has effective teacher/admin role in the workspace."""
        session = self._workspace_repo.uow.session

        local_role = aliased(RoleModel)
        global_role = aliased(RoleModel)

        stmt = (
            select(
                local_role.name.label("local_role_name"),
                global_role.name.label("global_role_name"),
            )
            .select_from(WorkSpaceParticipation)
            .join(User, User.id == WorkSpaceParticipation.participant_id)
            .outerjoin(local_role, local_role.id == WorkSpaceParticipation.role_id)
            .outerjoin(global_role, global_role.id == User.role_id)
            .where(
                WorkSpaceParticipation.workspace_id == workspace_id,
                WorkSpaceParticipation.participant_id == user_id,
            )
        )
        result = await session.execute(stmt)
        row = result.one_or_none()

        if row is None:
            return False

        effective = self._resolve_effective_role(
            local_role_name=row.local_role_name,
            global_role_name=row.global_role_name,
        )
        return effective in ("teacher", "admin")

    async def get_project_relations(self, project_id: int, *, workspace_id: int) -> ProjectRelations:
        """Return the full relationship snapshot for a project."""
        project = await self._require_project_in_workspace(project_id, workspace_id)

        member_ids = sorted(p.participant_id for p in project.participants)
        teacher_ids = await self.get_workspace_teacher_ids(workspace_id)

        return ProjectRelations(
            project_id=project.id,
            workspace_id=workspace_id,
            manager_id=project.author_id,
            member_ids=member_ids,
            workspace_teacher_ids=teacher_ids,
        )

    async def _require_project_in_workspace(self, project_id: int, workspace_id: int):
        """Load the project and ensure it belongs to *workspace_id*."""
        project = await self._project_repo.get_by_id(project_id)
        if project is None or project.workspace_id != workspace_id:
            raise NotFoundError("Project not found in this workspace")
        return project

    @staticmethod
    def _resolve_effective_role(
        local_role_name: str | None,
        global_role_name: str | None,
    ) -> str | None:
        """Resolve effective role with local priority.

        Returns one of ``'teacher'``, ``'admin'``, ``'manager'``, ``'member'``,
        or ``None`` when both roles are absent.
        """
        if local_role_name is not None:
            return local_role_name
        return global_role_name
