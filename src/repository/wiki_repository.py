from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.core.uow import IUnitOfWork
from src.model.wiki import WikiPage
from src.repository.base_repository import BaseRepository
from src.schema.wiki import WikiPageUpdate


class WikiRepository(BaseRepository[WikiPage, dict, WikiPageUpdate]):
    """Репозиторий страниц вики проекта."""

    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = WikiPage

    @staticmethod
    def _apply_filters(
        query,
        *,
        visibilities: Sequence[str] | None,
        parent_id: int | None,
        search: str | None,
    ):
        """Навесить общие фильтры списка и подсчёта.

        visibilities — белый список видимостей, доступный читателю. None означает
        «не фильтровать» и используется только внутри сервиса, который и так
        передаёт полный набор строк; пустой список даёт пустую выборку.
        """
        if visibilities is not None:
            if not visibilities:
                return query.where(WikiPage.id.is_(None))
            query = query.where(WikiPage.visibility.in_(list(visibilities)))

        if parent_id is not None:
            query = query.where(WikiPage.parent_id == parent_id)

        if search:
            query = query.where(WikiPage.title.ilike(f"%{search.strip()}%"))

        return query

    async def get_with_author(self, page_id: int) -> WikiPage | None:
        result = await self.uow.session.execute(
            select(WikiPage).where(WikiPage.id == page_id).options(selectinload(WikiPage.author))
        )
        return result.scalar_one_or_none()

    async def get_by_project(
        self,
        project_id: int,
        *,
        visibilities: Sequence[str] | None = None,
        parent_id: int | None = None,
        search: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> list[WikiPage]:
        """Страницы проекта, отсортированные для сайдбара.

        Args:
            project_id: проект-владелец вики
            visibilities: белый список видимостей, доступный читателю; None — все
            parent_id: фильтр по родителю; None — все уровни вложенности
            search: подстрока в заголовке, регистронезависимо
            offset/limit: окно пагинации; None — без ограничения (дерево)
        """
        query = self._apply_filters(
            select(WikiPage).where(WikiPage.project_id == project_id),
            visibilities=visibilities,
            parent_id=parent_id,
            search=search,
        )
        query = query.order_by(WikiPage.position, WikiPage.id)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)

        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def count_by_project(
        self,
        project_id: int,
        *,
        visibilities: Sequence[str] | None = None,
        parent_id: int | None = None,
        search: str | None = None,
    ) -> int:
        query = self._apply_filters(
            select(func.count()).select_from(WikiPage).where(WikiPage.project_id == project_id),
            visibilities=visibilities,
            parent_id=parent_id,
            search=search,
        )
        result = await self.uow.session.execute(query)
        return result.scalar_one()

    async def is_descendant(self, page_id: int, candidate_parent_id: int) -> bool:
        """Входит ли candidate_parent_id в поддерево page_id.

        Страницу нельзя положить внутрь самой себя или своего собственного
        потомка — иначе в дереве появляется цикл и чтение зацикливается.
        Обход вверх по parent_id; visited защищает от уже существующей петли.
        """
        visited: set[int] = set()
        current_id: int | None = candidate_parent_id

        while current_id is not None and current_id not in visited:
            if current_id == page_id:
                return True
            visited.add(current_id)
            result = await self.uow.session.execute(select(WikiPage.parent_id).where(WikiPage.id == current_id))
            current_id = result.scalar_one_or_none()

        return False

    async def get_subtree_ids(self, page_id: int) -> list[int]:
        """Идентификаторы всех потомков page_id.

        Нужны для удаления: внешний ключ parent_id без ON DELETE CASCADE
        заставит Postgres отклонить DELETE родителя, пока существуют дети.
        """
        collected: list[int] = []
        frontier = [page_id]
        visited: set[int] = set()

        while frontier:
            result = await self.uow.session.execute(select(WikiPage.id).where(WikiPage.parent_id.in_(frontier)))
            child_ids = [row[0] for row in result.all()]
            fresh = [child_id for child_id in child_ids if child_id not in visited]
            if not fresh:
                break
            visited.update(fresh)
            collected.extend(fresh)
            frontier = fresh

        return collected

    async def get_max_position(self, project_id: int, parent_id: int | None) -> int:
        """Наибольшая позиция среди соседей — новая страница встанет в конец."""
        query = select(func.max(WikiPage.position)).where(WikiPage.project_id == project_id)
        query = query.where(WikiPage.parent_id.is_(None) if parent_id is None else WikiPage.parent_id == parent_id)
        result = await self.uow.session.execute(query)
        return result.scalar_one() or 0
