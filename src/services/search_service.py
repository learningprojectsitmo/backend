from __future__ import annotations

from src.schema.search import (
    SearchProjectItem,
    SearchResponse,
    SearchSpaceItem,
    SearchUserItem,
)
from src.services.project_service import ProjectService
from src.services.user_service import UserService
from src.services.workspace_service import WorkSpaceService

MIN_QUERY_LENGTH = 2


class SearchService:
    """Глобальный поиск по проектам, пространствам и участникам"""

    def __init__(
        self,
        project_service: ProjectService,
        workspace_service: WorkSpaceService,
        user_service: UserService,
    ) -> None:
        self._project_service = project_service
        self._workspace_service = workspace_service
        self._user_service = user_service

    def _query_valid(self, query: str) -> bool:
        return len(query) >= MIN_QUERY_LENGTH

    async def _search_projects(self, query: str, user_id: int, limit: int) -> list[SearchProjectItem]:
        projects = await self._project_service.search_projects_by_text(query, limit=limit, viewer_id=user_id)
        return [
            SearchProjectItem(
                id=p.id,
                name=p.name,
                description=p.description,
                workspace_id=p.workspace_id,
                workspace_name=p.workspace.name if p.workspace else None,
                status=p.status.name if p.status else None,
                progress=p.progress or 0,
            )
            for p in projects
        ]

    async def _search_spaces(self, query: str, user_id: int, limit: int) -> list[SearchSpaceItem]:
        rows = await self._workspace_service.search_spaces_by_text(query, user_id, limit=limit)
        return [
            SearchSpaceItem(
                id=row["id"],
                title=row["title"],
                description=row.get("description"),
                category=row.get("category"),
                projects_count=row.get("projects_count") or 0,
                members_count=row.get("members_count") or 0,
            )
            for row in rows
        ]

    async def _search_users(self, query: str, limit: int) -> list[SearchUserItem]:
        users = await self._user_service.search_users_by_text(query, limit=limit)
        return [
            SearchUserItem(
                id=user.id,
                first_name=user.first_name,
                last_name=user.last_name,
                middle_name=user.middle_name,
                email=user.email,
                role=user.role.name if user.role else None,
            )
            for user in users
        ]

    async def search(
        self,
        query: str,
        user_id: int,
        project_limit: int = 5,
        space_limit: int = 5,
        user_limit: int = 10,
    ) -> SearchResponse:
        """Выполнить поиск. Короткие/пустые запросы возвращают пустой ответ."""
        query = (query or "").strip()
        if not self._query_valid(query):
            return SearchResponse(projects=[], spaces=[], users=[])

        projects = await self._search_projects(query, user_id, project_limit)
        spaces = await self._search_spaces(query, user_id, space_limit)
        users = await self._search_users(query, user_limit)

        return SearchResponse(projects=projects, spaces=spaces, users=users)
