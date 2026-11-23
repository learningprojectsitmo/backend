from __future__ import annotations

from sqlalchemy import delete, exists, func, select, update

from src.core.uow import IUnitOfWork
from src.model.exam import Exam, ExamSettingsProjectType, ExamSettingsRevision
from src.model.exam_attempt import ExamAttempt
from src.model.exam_registration import ExamRegistration, ExamSlot
from src.schema.exam import ExamConfiguration, ExamListStatus, ExamWeights


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

    async def delete_empty_draft(self, exam: Exam) -> None:
        # The current-revision FK is deferred. Delete the selected types and revisions before the root.
        await self.uow.session.execute(
            delete(ExamSettingsProjectType).where(ExamSettingsProjectType.exam_id == exam.id)
        )
        await self.uow.session.execute(delete(ExamSettingsRevision).where(ExamSettingsRevision.exam_id == exam.id))
        await self.uow.session.delete(exam)
        await self.uow.session.flush()

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

    async def event_seq(self, workspace_id: int, exam_id: int) -> int | None:
        return await self.uow.session.scalar(
            select(Exam.stream_seq).where(Exam.id == exam_id, Exam.workspace_id == workspace_id)
        )

    async def revision_state(self, workspace_id: int, exam_id: int) -> tuple[int, int] | None:
        """Return (queue_revision, current_settings_version) for the ETA snapshot check."""
        row = (
            await self.uow.session.execute(
                select(Exam.queue_revision, Exam.current_settings_version).where(
                    Exam.id == exam_id,
                    Exam.workspace_id == workspace_id,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return int(row[0]), int(row[1])

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
        return self._configuration(revision, tuple(ids))

    async def revision_configuration(self, exam_id: int, version: int) -> ExamConfiguration | None:
        rows = (
            await self.uow.session.execute(
                select(ExamSettingsRevision, ExamSettingsProjectType.project_type_id)
                .outerjoin(
                    ExamSettingsProjectType,
                    (ExamSettingsProjectType.exam_id == ExamSettingsRevision.exam_id)
                    & (ExamSettingsProjectType.settings_version == ExamSettingsRevision.version),
                )
                .where(ExamSettingsRevision.exam_id == exam_id, ExamSettingsRevision.version == version)
                .order_by(ExamSettingsProjectType.project_type_id)
            )
        ).all()
        if not rows:
            return None
        return self._configuration(rows[0][0], tuple(type_id for _, type_id in rows if type_id is not None))

    @staticmethod
    def _configuration(revision: ExamSettingsRevision, ids: tuple[int, ...]) -> ExamConfiguration:
        values = {
            key: getattr(revision, key)
            for key in ExamConfiguration.model_fields
            if key not in {"weights", "project_type_ids"}
        }
        return ExamConfiguration(
            **values,
            project_type_ids=ids,
            weights=ExamWeights(
                teacher=revision.teacher_weight, manager=revision.manager_weight, member=revision.member_weight
            ),
        )

    async def list_scoped(
        self, workspace_id: int, *, include_drafts: bool, status: ExamListStatus | None, limit: int, offset: int
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
        if status == "archived":
            if not include_drafts:
                return []
            query = query.where(Exam.archived_at.is_not(None))
        else:
            query = query.where(Exam.archived_at.is_(None))
            if not include_drafts:
                query = query.where(Exam.status == "published")
            if status == "completed":
                query = query.where(Exam.completed_at.is_not(None))
            elif status is not None:
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

    async def has_unresolved_registrations(self, exam_id: int) -> bool:
        finished = exists().where(
            ExamAttempt.registration_id == ExamRegistration.id,
            ExamAttempt.status == "finished",
        )
        unresolved = exists().where(
            ExamRegistration.exam_id == exam_id,
            ExamRegistration.status == "active",
            ExamRegistration.queue_hold.is_distinct_from("no_show"),
            ~finished,
        )
        return bool(await self.uow.session.scalar(select(unresolved)))

    async def has_registrations(self, exam_id: int) -> bool:
        return bool(await self.uow.session.scalar(select(exists().where(ExamRegistration.exam_id == exam_id))))

    async def has_attempts(self, exam_id: int) -> bool:
        return bool(await self.uow.session.scalar(select(exists().where(ExamAttempt.exam_id == exam_id))))

    async def earliest_slot_start(self, exam_id: int):
        return await self.uow.session.scalar(select(func.min(ExamSlot.starts_at)).where(ExamSlot.exam_id == exam_id))

    async def bump_queue_revision(self, exam_id: int) -> int:
        self.uow.mark_exam_changed(exam_id, "queue")
        revision = await self.uow.session.scalar(
            update(Exam)
            .where(Exam.id == exam_id)
            .values(queue_revision=Exam.queue_revision + 1)
            .returning(Exam.queue_revision)
            .execution_options(synchronize_session=False)
        )
        return int(revision)
