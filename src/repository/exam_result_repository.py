from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased

from src.core.uow import IUnitOfWork
from src.model.exam import Exam, ExamSettingsRevision
from src.model.exam_attempt import AssessmentWindow, ExamAttempt
from src.model.exam_result import ExamResultEdition
from src.model.project import Project, ProjectType
from src.model.project_type_question import ProjectTypeQuestion
from src.model.user import User

RegistryState = Literal["undecided", "accepted", "published"]


@dataclass(frozen=True)
class ExamResultRegistryCurrent:
    """Latest accepted edition of an attempt (independent of the HTTP schemas)."""

    version: int
    kind: str
    calculated_score: Decimal | None
    final_score: Decimal
    max_score: Decimal
    reason: str | None
    decided_by_id: int
    decided_by_first_name: str
    decided_by_last_name: str | None
    decided_at: datetime
    published_at: datetime | None
    published_by_id: int | None


@dataclass(frozen=True)
class ExamResultRegistryRow:
    """One finished attempt of an exam with its decision state; reused by the CSV statement (#121)."""

    attempt_id: int
    registration_id: int
    project_id: int
    project_name: str
    project_type_id: int
    finished_at: datetime
    editions_count: int
    current: ExamResultRegistryCurrent | None
    previous_final_score: Decimal | None
    settings_outdated: bool

    @property
    def state(self) -> RegistryState:
        if self.current is None:
            return "undecided"
        return "accepted" if self.current.published_at is None else "published"


def escape_like(value: str) -> str:
    """Escape LIKE wildcards so user input is matched literally (escape character is a backslash)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ExamResultRepository:
    def __init__(self, uow: IUnitOfWork):
        self.uow = uow

    async def latest(self, attempt_id: int) -> ExamResultEdition | None:
        query = (
            select(ExamResultEdition)
            .where(ExamResultEdition.attempt_id == attempt_id)
            .order_by(ExamResultEdition.version.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        return (await self.uow.session.scalars(query)).one_or_none()

    async def editions(self, attempt_id: int) -> list[ExamResultEdition]:
        query = (
            select(ExamResultEdition)
            .where(ExamResultEdition.attempt_id == attempt_id)
            .order_by(ExamResultEdition.version)
            .execution_options(populate_existing=True)
        )
        return list((await self.uow.session.scalars(query)).all())

    async def add(self, edition: ExamResultEdition) -> ExamResultEdition:
        self.uow.session.add(edition)
        await self.uow.session.flush()
        return edition

    async def sheet_max(self, project_type_id: int) -> int:
        return int(
            await self.uow.session.scalar(
                select(func.count(ProjectTypeQuestion.id) * ProjectType.question_max_score)
                .select_from(ProjectType)
                .join(ProjectTypeQuestion, ProjectTypeQuestion.project_type_id == ProjectType.id)
                .where(ProjectType.id == project_type_id)
                .group_by(ProjectType.question_max_score)
            )
            or 0
        )

    async def list_results(
        self,
        workspace_id: int,
        exam_id: int,
        *,
        q: str | None = None,
        state: RegistryState | None = None,
        limit: int,
        offset: int,
    ) -> list[ExamResultRegistryRow]:
        """One row per finished attempt (with an assessment window) of the exam, in a single SQL query.

        Editions are ranked once in a window-function subquery (latest = rn 1, previous value = lag over
        version, editions_count = count over the attempt), so there is no per-attempt follow-up query.
        Order is (attempt.started_at, attempt.id); up to limit+1 rows are returned so the caller can compute has_more.
        """
        ranked = (
            select(
                ExamResultEdition.id.label("id"),
                ExamResultEdition.attempt_id.label("attempt_id"),
                func.row_number()
                .over(partition_by=ExamResultEdition.attempt_id, order_by=ExamResultEdition.version.desc())
                .label("rn"),
                func.count().over(partition_by=ExamResultEdition.attempt_id).label("editions_count"),
                func.lag(ExamResultEdition.final_score)
                .over(partition_by=ExamResultEdition.attempt_id, order_by=ExamResultEdition.version)
                .label("previous_final_score"),
            )
            .where(ExamResultEdition.workspace_id == workspace_id, ExamResultEdition.exam_id == exam_id)
            .subquery("ranked")
        )
        edition = aliased(ExamResultEdition)
        decider = aliased(User)
        revision = aliased(ExamSettingsRevision)
        outdated = and_(
            edition.id.is_not(None),
            or_(
                edition.settings_version != Exam.current_settings_version,
                edition.teacher_weight != revision.teacher_weight,
                edition.manager_weight != revision.manager_weight,
                edition.member_weight != revision.member_weight,
                edition.max_score != revision.max_score,
            ),
        )
        query = (
            select(
                ExamAttempt.id,
                ExamAttempt.registration_id,
                ExamAttempt.project_id,
                Project.name,
                ExamAttempt.project_type_id,
                ExamAttempt.finished_at,
                func.coalesce(ranked.c.editions_count, 0),
                ranked.c.previous_final_score,
                outdated.label("settings_outdated"),
                edition,
                decider.first_name,
                decider.last_name,
            )
            .select_from(ExamAttempt)
            .join(
                AssessmentWindow,
                and_(AssessmentWindow.attempt_id == ExamAttempt.id, AssessmentWindow.exam_id == ExamAttempt.exam_id),
            )
            .join(Project, Project.id == ExamAttempt.project_id)
            .join(Exam, and_(Exam.id == ExamAttempt.exam_id, Exam.workspace_id == ExamAttempt.workspace_id))
            .join(
                revision,
                and_(revision.exam_id == Exam.id, revision.version == Exam.current_settings_version),
            )
            .outerjoin(ranked, and_(ranked.c.attempt_id == ExamAttempt.id, ranked.c.rn == 1))
            .outerjoin(edition, edition.id == ranked.c.id)
            .outerjoin(decider, decider.id == edition.decided_by)
            .where(
                ExamAttempt.workspace_id == workspace_id,
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.status == "finished",
            )
        )
        if q:
            query = query.where(Project.name.ilike(f"%{escape_like(q)}%", escape="\\"))
        if state == "undecided":
            query = query.where(edition.id.is_(None))
        elif state == "accepted":
            query = query.where(edition.id.is_not(None), edition.published_at.is_(None))
        elif state == "published":
            query = query.where(edition.published_at.is_not(None))
        query = query.order_by(ExamAttempt.started_at, ExamAttempt.id).limit(limit + 1).offset(offset)
        rows = (await self.uow.session.execute(query.execution_options(populate_existing=True))).all()
        return [self._registry_row(row) for row in rows]

    @staticmethod
    def _registry_row(row) -> ExamResultRegistryRow:
        (attempt_id, registration_id, project_id, project_name, type_id, finished_at, count, previous, stale) = row[:9]
        edition, first_name, last_name = row[9:]
        current = None
        if edition is not None:
            current = ExamResultRegistryCurrent(
                version=edition.version,
                kind=edition.kind,
                calculated_score=edition.calculated_score,
                final_score=edition.final_score,
                max_score=edition.max_score,
                reason=edition.reason,
                decided_by_id=edition.decided_by,
                decided_by_first_name=first_name,
                decided_by_last_name=last_name,
                decided_at=edition.decided_at,
                published_at=edition.published_at,
                published_by_id=edition.published_by,
            )
        return ExamResultRegistryRow(
            attempt_id=attempt_id,
            registration_id=registration_id,
            project_id=project_id,
            project_name=project_name,
            project_type_id=type_id,
            finished_at=finished_at,
            editions_count=int(count),
            current=current,
            previous_final_score=previous,
            settings_outdated=bool(stale),
        )
