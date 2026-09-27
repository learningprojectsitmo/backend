from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from src.core.exceptions import NotFoundError, PermissionError, ValidationError
from src.model.project import Project, ProjectParticipation
from src.model.user import Role
from src.model.wiki import WIKI_VISIBILITY_PRIVATE, WIKI_VISIBILITY_PUBLIC, WikiPage
from src.model.workspace import WorkSpaceParticipation
from src.schema.wiki import (
    WikiPageCreate,
    WikiPageFull,
    WikiPageListResponse,
    WikiPageSummary,
    WikiPageUpdate,
)
from src.services.base_service import BaseService
from src.util.html_sanitize import sanitize_html

if TYPE_CHECKING:
    from src.repository.project_repository import ProjectRepository
    from src.repository.wiki_repository import WikiRepository

# Роли пространства, которым доступно редактирование любой страницы вики.
_EDITOR_ROLES = ("admin", "teacher")


class WikiService(BaseService[WikiPage, WikiPageCreate, WikiPageUpdate]):
    """Сервис вики проекта.

    Видимость:
        public  — страницу читает любой, включая анонимного посетителя;
        private — только команда проекта: автор проекта, участники проекта,
                  и участники пространства с ролью admin или teacher.

    Приватная страница для постороннего отдаёт 404, а не 403: иначе по id
    перебираются существующие страницы. Все выборки проходят через
    _allowed_visibilities, поэтому приватное содержимое не может утечь через
    список или дерево даже при подделанном параметре запроса.
    """

    def __init__(
        self,
        wiki_repository: WikiRepository,
        project_repository: ProjectRepository,
    ) -> None:
        super().__init__(wiki_repository)
        self._wiki_repository = wiki_repository
        self._project_repository = project_repository

    # ─── права ────────────────────────────────────────────────────────────

    async def _is_workspace_editor(self, user_id: int, workspace_id: int | None) -> bool:
        if not workspace_id:
            return False
        result = await self._wiki_repository.uow.session.execute(
            select(WorkSpaceParticipation)
            .join(Role, Role.id == WorkSpaceParticipation.role_id)
            .where(
                WorkSpaceParticipation.workspace_id == workspace_id,
                WorkSpaceParticipation.participant_id == user_id,
                Role.name.in_(_EDITOR_ROLES),
            )
        )
        return result.first() is not None

    async def _is_project_participant(self, project_id: int, user_id: int) -> bool:
        result = await self._wiki_repository.uow.session.execute(
            select(ProjectParticipation).where(
                ProjectParticipation.project_id == project_id,
                ProjectParticipation.participant_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def _is_team_member(self, project: Project, user_id: int) -> bool:
        """Свой ли проект для пользователя — по образцу SpecificationService._can_view."""
        if project.author_id == user_id:
            return True
        if await self._is_project_participant(project.id, user_id):
            return True
        return bool(project.workspace_id) and await self._is_workspace_editor(user_id, project.workspace_id)

    async def _get_project(self, project_id: int) -> Project:
        project = await self._project_repository.get_by_id(project_id)
        if not project:
            raise NotFoundError("Project not found")
        return project

    async def _allowed_visibilities(
        self,
        project: Project,
        user_id: int | None,
        *,
        is_admin: bool = False,
    ) -> list[str]:
        """Срез видимостей, доступный конкретному читателю.

        Анонимному и постороннему — только public.
        """
        if user_id is not None and (is_admin or await self._is_team_member(project, user_id)):
            return [WIKI_VISIBILITY_PUBLIC, WIKI_VISIBILITY_PRIVATE]
        return [WIKI_VISIBILITY_PUBLIC]

    async def _can_read(
        self,
        page: WikiPage,
        project: Project,
        user_id: int | None,
        *,
        is_admin: bool = False,
    ) -> bool:
        if page.visibility == WIKI_VISIBILITY_PUBLIC:
            return True
        if user_id is None:
            return False
        return is_admin or await self._is_team_member(project, user_id)

    async def _can_edit(
        self,
        page: WikiPage,
        project: Project,
        user_id: int,
        *,
        is_admin: bool = False,
    ) -> bool:
        """Править страницу может её автор, лид проекта, teacher/admin.

        Обычный участник команды правит только страницы, которые сам создал.
        """
        if is_admin or user_id in (page.author_id, project.author_id):
            return True
        return await self._is_workspace_editor(user_id, project.workspace_id)

    async def _can_change_visibility(
        self,
        project: Project,
        user_id: int,
        *,
        is_admin: bool = False,
    ) -> bool:
        """Публикацию страницы наружу решает лид проекта или teacher/admin.

        Рядовой участник команды может завести приватную страницу, но не может
        выставить её публичной — иначе любой участник обнародовал бы документ.
        """
        if is_admin or project.author_id == user_id:
            return True
        return await self._is_workspace_editor(user_id, project.workspace_id)

    # ─── чтение ───────────────────────────────────────────────────────────

    @staticmethod
    def _to_full(page: WikiPage) -> WikiPageFull:
        """Собрать ответ. Страница обязана быть загружена через get_with_author.

        author — relationship, а lazy load в async упал бы с MissingGreenlet,
        поэтому все пути чтения и записи идут через get_with_author.
        """
        author = None
        if page.author is not None:
            author = {
                "id": page.author.id,
                "username": page.author.first_name or page.author.email or "Unknown",
            }
        return WikiPageFull(
            id=page.id,
            project_id=page.project_id,
            parent_id=page.parent_id,
            title=page.title,
            content=page.content,
            visibility=page.visibility,
            position=page.position,
            author=author,
            created_at=page.created_at,
            updated_at=page.updated_at,
        )

    async def list_pages(
        self,
        project_id: int,
        user_id: int | None = None,
        *,
        is_admin: bool = False,
        parent_id: int | None = None,
        search: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> WikiPageListResponse:
        """Страницы вики, доступные читателю (без содержимого)."""
        project = await self._get_project(project_id)
        visibilities = await self._allowed_visibilities(project, user_id, is_admin=is_admin)

        page = max(page, 1)
        limit = max(min(limit, 200), 1)

        total = await self._wiki_repository.count_by_project(
            project_id,
            visibilities=visibilities,
            parent_id=parent_id,
            search=search,
        )
        pages = await self._wiki_repository.get_by_project(
            project_id,
            visibilities=visibilities,
            parent_id=parent_id,
            search=search,
            offset=(page - 1) * limit,
            limit=limit,
        )

        return WikiPageListResponse(
            items=[WikiPageSummary.model_validate(item) for item in pages],
            total=total,
            page=page,
            limit=limit,
            total_pages=(total + limit - 1) // limit if total else 0,
        )

    async def get_tree(
        self,
        project_id: int,
        user_id: int | None = None,
        *,
        is_admin: bool = False,
    ) -> list[WikiPageSummary]:
        """Плоский список всех доступных страниц — фронт собирает дерево сам.

        Отдаётся без содержимого: сайдбар не должен тянуть HTML каждой страницы.
        """
        project = await self._get_project(project_id)
        visibilities = await self._allowed_visibilities(project, user_id, is_admin=is_admin)
        pages = await self._wiki_repository.get_by_project(project_id, visibilities=visibilities)
        return [WikiPageSummary.model_validate(item) for item in pages]

    async def get_page(
        self,
        project_id: int,
        page_id: int,
        user_id: int | None = None,
        *,
        is_admin: bool = False,
    ) -> WikiPageFull:
        project = await self._get_project(project_id)
        page = await self._get_page_of_project(project_id, page_id)

        if not await self._can_read(page, project, user_id, is_admin=is_admin):
            # 404 вместо 403 — иначе по id перебираются приватные страницы.
            raise NotFoundError("Wiki page not found")

        return self._to_full(page)

    async def _get_page_of_project(self, project_id: int, page_id: int) -> WikiPage:
        page = await self._wiki_repository.get_with_author(page_id)
        if not page or page.project_id != project_id:
            raise NotFoundError("Wiki page not found")
        return page

    # ─── запись ───────────────────────────────────────────────────────────

    async def create_page(
        self,
        project_id: int,
        author_id: int,
        data: WikiPageCreate,
        *,
        is_admin: bool = False,
    ) -> WikiPageFull:
        project = await self._get_project(project_id)

        if not (is_admin or await self._is_team_member(project, author_id)):
            raise PermissionError("Only project team can create wiki pages")

        if data.parent_id is not None and await self._resolve_parent(data.parent_id, project_id) is None:
            raise NotFoundError("Parent wiki page not found")

        if data.visibility == WIKI_VISIBILITY_PUBLIC and not await self._can_change_visibility(
            project, author_id, is_admin=is_admin
        ):
            raise PermissionError("Only project lead or teacher can publish wiki pages")

        position = data.position
        if position is None:
            position = await self._wiki_repository.get_max_position(project_id, data.parent_id) + 1

        page = WikiPage(
            project_id=project_id,
            parent_id=data.parent_id,
            author_id=author_id,
            title=data.title.strip(),
            content=sanitize_html(data.content),
            visibility=data.visibility,
            position=position,
        )
        self._wiki_repository.uow.session.add(page)
        await self._wiki_repository.uow.session.flush()

        # Перечитываем с автором: у только что созданного объекта relationship
        # не загружен, а _to_full к нему обращается.
        created = await self._wiki_repository.get_with_author(page.id)
        return self._to_full(created or page)

    async def update_page(
        self,
        project_id: int,
        page_id: int,
        user_id: int,
        data: WikiPageUpdate,
        *,
        is_admin: bool = False,
    ) -> WikiPageFull:
        project = await self._get_project(project_id)
        page = await self._get_page_of_project(project_id, page_id)

        if not await self._can_edit(page, project, user_id, is_admin=is_admin):
            raise PermissionError("You cannot edit this wiki page")

        if data.title is not None:
            page.title = data.title.strip()
        if data.content is not None:
            page.content = sanitize_html(data.content)
        if data.position is not None:
            page.position = data.position

        if data.visibility is not None and data.visibility != page.visibility:
            if not await self._can_change_visibility(project, user_id, is_admin=is_admin):
                raise PermissionError("Only project lead or teacher can change wiki visibility")
            page.visibility = data.visibility

        if "parent_id" in data.model_fields_set:
            if data.parent_id == page_id:
                raise ValidationError("Wiki page cannot be its own parent")
            if data.parent_id is not None:
                if await self._resolve_parent(data.parent_id, project_id) is None:
                    raise NotFoundError("Parent wiki page not found")
                if await self._wiki_repository.is_descendant(page_id, data.parent_id):
                    raise ValidationError("Wiki page cannot be nested into its own descendant")
            page.parent_id = data.parent_id

        await self._wiki_repository.uow.session.flush()
        # После flush ORM expire'ит атрибуты, и page.author попытался бы
        # загрузиться лениво — в async это MissingGreenlet. Перечитываем
        # через get_with_author, как в create_page.
        refreshed = await self._wiki_repository.get_with_author(page_id)
        return self._to_full(refreshed or page)

    async def delete_page(
        self,
        project_id: int,
        page_id: int,
        user_id: int,
        *,
        is_admin: bool = False,
    ) -> bool:
        project = await self._get_project(project_id)
        page = await self._get_page_of_project(project_id, page_id)

        if not await self._can_edit(page, project, user_id, is_admin=is_admin):
            raise PermissionError("You cannot delete this wiki page")

        # Внешний ключ parent_id без ON DELETE CASCADE заставит Postgres
        # отклонить удаление родителя, пока существуют вложенные страницы.
        subtree = await self._wiki_repository.get_subtree_ids(page_id)
        for child_id in reversed(subtree):
            child = await self._wiki_repository.get_by_id(child_id)
            if child:
                await self._wiki_repository.uow.session.delete(child)
        await self._wiki_repository.uow.session.delete(page)
        await self._wiki_repository.uow.session.flush()
        return True

    async def _resolve_parent(self, parent_id: int | None, project_id: int) -> WikiPage | None:
        if parent_id is None:
            return None
        parent = await self._wiki_repository.get_by_id(parent_id)
        if not parent or parent.project_id != project_id:
            return None
        return parent
