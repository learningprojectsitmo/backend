from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.model.user import User
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam import (
    AssessmentWindowSettings,
    ExamCreate,
    ExamListRead,
    ExamPublish,
    ExamRead,
    ExamSettingsHistoryRead,
    ExamSettingsReplace,
    ExamSettingsRevisionRead,
)


class ExamService:
    def __init__(self, repository: ExamRepository, questions: ProjectTypeQuestionRepository):
        self._repository = repository
        self._questions = questions

    @staticmethod
    def _conflict(code: str):
        raise BusinessLogicError({"code": code, "message": code.replace("_", " ")})

    async def _scope(self, workspace_id: int, user: User) -> bool:
        workspace = await self._questions.get_workspace(workspace_id)
        if workspace is None:
            raise NotFoundError("Workspace not found")
        role = await self._questions.get_global_role(user.id)
        if role == "admin":
            return True
        member, local = await self._questions.get_membership_role(workspace_id, user.id)
        if not member and workspace.author_id != user.id:
            raise NotFoundError("Workspace not found")
        return role == "teacher" or local in {"teacher", "admin"}

    async def read_access(self, workspace_id, exam_id, user, *, lock=False):
        writer = await self._scope(workspace_id, user)
        exam = await self._repository.get_scoped(workspace_id, exam_id, lock=lock)
        if exam is None or (exam.status == "draft" and (not writer)):
            raise NotFoundError("Exam not found")
        return exam, writer

    async def _exam(self, workspace_id, exam_id, user, *, write=False, lock=False):
        exam, writer = await self.read_access(workspace_id, exam_id, user, lock=lock)
        if write and (not writer):
            raise PermissionError("Only workspace teacher/admin can manage exams")
        return exam

    async def _types(self, workspace_id, ids, *, ready=False):
        if ready and (not ids):
            self._conflict("questions_not_ready")
        for tid in sorted(ids):
            if await self._questions.get_type(workspace_id, tid, lock=True) is None:
                raise NotFoundError("Project type not found in this workspace")
            if ready:
                questions = await self._questions.list_questions(tid)
                if not questions or any(
                    {level.score for level in q.levels} != {1, 2, 3, 4, 5}
                    or any(not level.description.strip() for level in q.levels)
                    for q in questions
                ):
                    self._conflict("questions_not_ready")

    async def _read(self, exam) -> ExamRead:
        revision = await self._repository.get_revision(exam.id, exam.current_settings_version)
        return ExamRead(
            id=exam.id,
            workspace_id=exam.workspace_id,
            status=exam.status,
            current_settings_version=exam.current_settings_version,
            configuration=await self._repository.configuration(revision),
            created_by=exam.created_by,
            created_at=exam.created_at,
            published_by=exam.published_by,
            published_at=exam.published_at,
        )

    async def _revision_read(self, revision) -> ExamSettingsRevisionRead:
        return ExamSettingsRevisionRead(
            exam_id=revision.exam_id,
            version=revision.version,
            configuration=await self._repository.configuration(revision),
            changed_by=revision.changed_by,
            changed_at=revision.changed_at,
            reason=revision.reason,
        )

    async def create(self, workspace_id: int, data: ExamCreate, user: User) -> ExamRead:
        if not await self._scope(workspace_id, user):
            raise PermissionError("Only workspace teacher/admin can manage exams")
        config = data.to_configuration()
        await self._types(workspace_id, config.project_type_ids)
        exam = await self._repository.create_root(workspace_id, user.id)
        await self._repository.append_revision(exam, config, changed_by=user.id, reason=None)
        return await self._read(exam)

    async def get(self, workspace_id: int, exam_id: int, user: User) -> ExamRead:
        return await self._read(await self._exam(workspace_id, exam_id, user))

    async def list(self, workspace_id: int, user: User, *, status: str | None, limit: int, offset: int) -> ExamListRead:
        writer = await self._scope(workspace_id, user)
        rows = await self._repository.list_scoped(
            workspace_id, include_drafts=writer, status=status, limit=limit, offset=offset
        )
        return ExamListRead(
            items=[await self._read(e) for e in rows[:limit]], limit=limit, offset=offset, has_more=len(rows) > limit
        )

    async def replace_settings(
        self, workspace_id: int, exam_id: int, data: ExamSettingsReplace, user: User
    ) -> ExamRead:
        exam = await self._exam(workspace_id, exam_id, user, write=True, lock=True)
        if exam.current_settings_version != data.expected_version:
            self._conflict("settings_version_conflict")
        old = (await self._read(exam)).configuration
        config = data.configuration
        if exam.status == "published" and any(
            getattr(old, k) != getattr(config, k)
            for k in ["starts_at", "project_type_ids", "registration_opens_at", "registration_closes_at"]
        ):
            self._conflict("published_schedule_locked")
        if old != config:
            earliest = await self._repository.earliest_slot_start(exam_id)
            if earliest is not None and earliest < config.starts_at:
                self._conflict("slot_schedule_conflict")
            await self._types(workspace_id, config.project_type_ids, ready=exam.status == "published")
            await self._repository.append_revision(exam, config, changed_by=user.id, reason=data.reason)
        return await self._read(exam)

    async def publish(self, workspace_id: int, exam_id: int, data: ExamPublish, user: User) -> ExamRead:
        exam = await self._exam(workspace_id, exam_id, user, write=True, lock=True)
        if exam.current_settings_version != data.expected_version:
            self._conflict("settings_version_conflict")
        if exam.status == "draft":
            config = (await self._read(exam)).configuration
            await self._types(workspace_id, config.project_type_ids, ready=True)
            exam.status = "published"
            exam.published_by = user.id
            exam.published_at = datetime.now(UTC)
            await self._repository.uow.session.flush()
        return await self._read(exam)

    async def list_settings(
        self, workspace_id: int, exam_id: int, user: User, *, limit: int, offset: int
    ) -> ExamSettingsHistoryRead:
        await self._exam(workspace_id, exam_id, user, write=True)
        rows = await self._repository.list_revisions(exam_id, limit=limit, offset=offset)
        return ExamSettingsHistoryRead(
            items=[await self._revision_read(r) for r in rows[:limit]],
            limit=limit,
            offset=offset,
            has_more=len(rows) > limit,
        )

    async def get_settings(self, workspace_id: int, exam_id: int, version: int, user: User) -> ExamSettingsRevisionRead:
        await self._exam(workspace_id, exam_id, user, write=True)
        revision = await self._repository.get_revision(exam_id, version)
        if revision is None:
            raise NotFoundError("Settings revision not found")
        return await self._revision_read(revision)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone is required")
        return value.astimezone(UTC)

    async def require_self_registration_open(
        self, workspace_id: int, exam_id: int, user: User, *, now: datetime
    ) -> ExamSettingsRevisionRead:
        await self._scope(workspace_id, user)
        exam = await self._repository.get_scoped(workspace_id, exam_id, lock=True)
        if exam is None:
            raise NotFoundError("Exam not found")
        if exam.status != "published":
            self._conflict("exam_not_published")
        revision = await self._repository.get_revision(exam_id, exam.current_settings_version)
        opens = max(exam.published_at, revision.registration_opens_at or exam.published_at)
        closes = min(revision.starts_at, revision.registration_closes_at or revision.starts_at)
        if not opens <= self._utc(now) < closes:
            self._conflict("registration_closed")
        return await self._revision_read(revision)

    async def require_questions_ready(self, workspace_id: int, project_type_id: int) -> None:
        await self._types(workspace_id, [project_type_id], ready=True)

    async def prepare_assessment_window(
        self, workspace_id: int, exam_id: int, project_type_id: int, *, expected_version: int, opened_at: datetime
    ) -> AssessmentWindowSettings:
        opened_at = self._utc(opened_at)
        exam = await self._repository.get_scoped(workspace_id, exam_id, lock=True)
        if exam is None:
            raise NotFoundError("Exam not found")
        if exam.status != "published":
            self._conflict("exam_not_published")
        if exam.current_settings_version != expected_version:
            self._conflict("settings_version_conflict")
        config = (await self._read(exam)).configuration
        if project_type_id not in config.project_type_ids:
            raise NotFoundError("Project type not selected for this exam")
        await self._types(workspace_id, [project_type_id], ready=True)
        await self._questions.add_question_lock(workspace_id, project_type_id, exam_id, locked_at=opened_at)
        return AssessmentWindowSettings(
            exam_id=exam_id,
            workspace_id=workspace_id,
            project_type_id=project_type_id,
            settings_version=expected_version,
            opened_at=opened_at,
            closes_at=opened_at + timedelta(minutes=config.assessment_window_minutes),
        )

    async def require_read_access(self, workspace_id: int, exam_id: int, user: User) -> None:
        await self.read_access(workspace_id, exam_id, user)

    async def require_organizer(self, workspace_id: int, exam_id: int, user: User) -> None:
        await self._exam(workspace_id, exam_id, user, write=True)
