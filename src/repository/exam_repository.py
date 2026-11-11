from __future__ import annotations

from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.exam import Exam, ExamSettingsProjectType, ExamSettingsRevision
from src.schema.exam import ExamConfiguration, ExamWeights


class ExamRepository:
    def __init__(self, uow: IUnitOfWork):
        self.uow = uow

    async def get_scoped(self, workspace_id: int, exam_id: int, *, lock: bool = False) -> Exam | None:
        query = (
            select(Exam)
            .where(Exam.id == exam_id, Exam.workspace_id == workspace_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        return (await self.uow.session.execute(query)).scalar_one_or_none()

    async def create_root(self, workspace_id: int, user_id: int) -> Exam:
        exam = Exam(workspace_id=workspace_id, created_by=user_id, status="draft", current_settings_version=1)
        self.uow.session.add(exam)
        await self.uow.session.flush()
        return exam

    async def append_revision(
        self, exam: Exam, configuration: ExamConfiguration, *, changed_by: int, reason: str | None
    ) -> ExamSettingsRevision:
        version = 1 if reason is None else exam.current_settings_version + 1
        values = configuration.model_dump(exclude={"weights", "project_type_ids", "connection_url"})
        revision = ExamSettingsRevision(
            exam_id=exam.id,
            version=version,
            workspace_id=exam.workspace_id,
            **values,
            connection_url=str(configuration.connection_url) if configuration.connection_url else None,
            teacher_weight=configuration.weights.teacher,
            manager_weight=configuration.weights.manager,
            member_weight=configuration.weights.member,
            changed_by=changed_by,
            reason=reason,
        )
        self.uow.session.add(revision)
        await self.uow.session.flush()
        self.uow.session.add_all(
            [
                ExamSettingsProjectType(
                    exam_id=exam.id, settings_version=version, workspace_id=exam.workspace_id, project_type_id=t
                )
                for t in configuration.project_type_ids
            ]
        )
        exam.current_settings_version = version
        await self.uow.session.flush()
        return revision

    async def get_revision(self, exam_id: int, version: int) -> ExamSettingsRevision | None:
        return await self.uow.session.get(ExamSettingsRevision, (exam_id, version))

    async def configuration(self, revision: ExamSettingsRevision) -> ExamConfiguration:
        ids = (
            (
                await self.uow.session.execute(
                    select(ExamSettingsProjectType.project_type_id)
                    .where(
                        ExamSettingsProjectType.exam_id == revision.exam_id,
                        ExamSettingsProjectType.settings_version == revision.version,
                    )
                    .order_by(ExamSettingsProjectType.project_type_id)
                )
            )
            .scalars()
            .all()
        )
        values = {
            key: getattr(revision, key)
            for key in ExamConfiguration.model_fields
            if key not in {"weights", "project_type_ids"}
        }
        return ExamConfiguration(
            **values,
            project_type_ids=tuple(ids),
            weights=ExamWeights(
                teacher=revision.teacher_weight, manager=revision.manager_weight, member=revision.member_weight
            ),
        )

    async def list_scoped(
        self, workspace_id: int, *, include_drafts: bool, status: str | None, limit: int, offset: int
    ) -> list[Exam]:
        query = (
            select(Exam)
            .join(
                ExamSettingsRevision,
                (ExamSettingsRevision.exam_id == Exam.id)
                & (ExamSettingsRevision.version == Exam.current_settings_version),
            )
            .where(Exam.workspace_id == workspace_id)
        )
        if not include_drafts:
            query = query.where(Exam.status == "published")
        if status is not None:
            query = query.where(Exam.status == status)
        return list(
            (
                await self.uow.session.execute(
                    query.order_by(ExamSettingsRevision.starts_at, Exam.id).limit(limit + 1).offset(offset)
                )
            ).scalars()
        )

    async def list_revisions(self, exam_id: int, *, limit: int, offset: int) -> list[ExamSettingsRevision]:
        return list(
            (
                await self.uow.session.execute(
                    select(ExamSettingsRevision)
                    .where(ExamSettingsRevision.exam_id == exam_id)
                    .order_by(ExamSettingsRevision.version)
                    .limit(limit + 1)
                    .offset(offset)
                )
            ).scalars()
        )
