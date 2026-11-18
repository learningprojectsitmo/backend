from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from uuid import uuid4

import anyio
from sqlalchemy import text

from src.core.exceptions import BusinessLogicError, PermissionError
from src.core.uow import IUnitOfWork
from src.model.user import User
from src.repository.exam_csv_repository import ExamCsvRepository
from src.repository.exam_repository import ExamRepository
from src.repository.project_repository import ProjectRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.repository.workspace_repository import WorkSpaceRepository
from src.services.exam_csv_participation import participation_rows
from src.services.exam_csv_profiles import MAX_CSV_BYTES, render_archive
from src.services.exam_score import ExamScoreError, ScoreWeights, SheetScore, calculate_exam_score
from src.services.exam_service import ExamService
from src.services.project_relations import ProjectRelationsService

MAX_SOURCE_ROWS = 100_000


@dataclass(frozen=True)
class ExamCsvSnapshot:
    export_id: str
    snapshot_at: datetime
    register: list[dict]
    participation: list[dict]
    criterion_count: int


class ExamCsvService:
    def __init__(
        self, uow_factory: Callable[[], IUnitOfWork], *, max_rows: int = MAX_SOURCE_ROWS, max_bytes: int = MAX_CSV_BYTES
    ):
        self._uow_factory = uow_factory
        self._max_rows = max_rows
        self._max_bytes = max_bytes

    async def download(self, workspace_id: int, exam_id: int, user: User) -> bytes:
        data = await self.snapshot(workspace_id, exam_id, user)
        # Snapshot's UoW has closed; worker serialization never holds a database connection.
        return await anyio.to_thread.run_sync(partial(render_archive, data, max_bytes=self._max_bytes))

    async def snapshot(self, workspace_id: int, exam_id: int, user: User) -> ExamCsvSnapshot:
        # A separate UoW is essential: authentication may already have SELECTed in its own session.
        async with self._uow_factory() as uow:
            await uow.session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            snapshot_at = await uow.session.scalar(text("SELECT transaction_timestamp()"))
            exams = ExamRepository(uow)
            await ExamService(exams, ProjectTypeQuestionRepository(uow)).require_read_access(
                workspace_id, exam_id, user
            )
            relations = ProjectRelationsService(ProjectRepository(uow), WorkSpaceRepository(uow))
            if not await relations.is_workspace_teacher(user.id, workspace_id=workspace_id):
                raise PermissionError("Only workspace teacher/admin can export exam CSV")
            exam = await exams.get_scoped(workspace_id, exam_id)
            settings = await exams.get_revision(exam_id, exam.current_settings_version)
            repo = ExamCsvRepository(uow, workspace_id, exam_id, max_rows=self._max_rows)
            registrations = await repo.registrations()
            editions = {row["attempt_id"]: row for row in await repo.editions()}
            questions = defaultdict(list)
            for question in await repo.questions():
                questions[question["project_type_id"]].append(question)
            audience = defaultdict(list)
            for assessor in await repo.audience():
                audience[assessor["attempt_id"]].append(assessor)
            answers = await repo.answers(
                [a["submission_id"] for people in audience.values() for a in people if a["submission_id"] is not None]
            )
            preview = await repo.preview() if any(r["attempt_id"] and not r["window_id"] for r in registrations) else []
            criterion_count = max(5, max((len(q) for q in questions.values()), default=0))
            common = {
                "export_id": str(uuid4()),
                "snapshot_at": snapshot_at.astimezone(UTC),
                "workspace_id": workspace_id,
                "exam_id": exam_id,
                "exam_title": settings.title,
            }
            register = [
                self._register(
                    row,
                    editions.get(row["attempt_id"]),
                    audience[row["attempt_id"]],
                    questions[row["project_type_id"]],
                    settings,
                    common,
                )
                for row in registrations
            ]
            participation = participation_rows(
                registrations, audience, preview, questions, answers, common, criterion_count
            )
        return ExamCsvSnapshot(common["export_id"], common["snapshot_at"], register, participation, criterion_count)

    @staticmethod
    def _register(row, edition, audience, questions, settings, common):
        known = row["window_id"] is not None
        if known and not audience:
            raise BusinessLogicError(
                {"code": "audience_snapshot_unavailable", "message": "Historical audience unavailable"}
            )
        submitted = [a for a in audience if a["admitted"] and a["submission_id"] is not None]
        eligible = sum(a["admitted"] for a in audience)
        state = "undecided"
        calculated = None
        calculation = None
        source = edition or settings
        if edition:
            state = "published" if edition["published_at"] else "accepted"
            calculated = edition["calculated_score"]
        elif row["defense_status"] == "finished" and known:
            if not questions:
                raise BusinessLogicError({"code": "questions_missing", "message": "Questions missing"})
            try:
                calculation = calculate_exam_score(
                    sheets=[SheetScore(a["role"], a["total"]) for a in submitted],
                    weights=ScoreWeights(settings.teacher_weight, settings.manager_weight, settings.member_weight),
                    sheet_max=5 * len(questions),
                    max_score=settings.max_score,
                )
            except ExamScoreError as error:
                raise BusinessLogicError({"code": "invalid_sheet_data", "message": "Invalid sheet data"}) from error
            calculated = calculation.score
            state = "preliminary" if calculated is not None else "no_calculation"

        def value(key):
            return source[key] if edition else getattr(source, key)

        result = {
            "schema_version": "assessment-register.v1",
            **common,
            **{
                key: row[key]
                for key in (
                    "registration_id",
                    "project_id",
                    "project_name",
                    "project_type_id",
                    "project_type_name",
                    "registration_status",
                    "attempt_id",
                    "started_at",
                    "finished_at",
                    "postponed_at",
                )
            },
            "presence": "present"
            if row["attempt_id"]
            else ("no_show" if row["queue_hold"] == "no_show" else "unknown"),
            "defense_status": row["defense_status"] or row["queue_hold"] or "not_started",
            "queue_hold": row["queue_hold"],
            "eligible_count": eligible if known else None,
            "submitted_count": len(submitted) if known else None,
            "not_submitted_count": eligible - len(submitted) if known else None,
            "excluded_count": len(audience) - eligible if known else None,
            "decision_state": state,
            "calculated_score": calculated,
            "final_score": edition["final_score"] if edition else None,
            "max_score": value("max_score"),
            "settings_version": edition["settings_version"] if edition else settings.version,
            **{key: value(key) for key in ("teacher_weight", "manager_weight", "member_weight")},
            "sheet_max": edition["sheet_max"] if edition else 5 * len(questions),
            "result_id": edition["id"] if edition else None,
            "result_version": edition["version"] if edition else None,
            "used_weight": edition["used_weight"] if edition else (calculation.used_weight if calculation else None),
            **{
                f"result_{role}_sheets": edition[f"{role}_sheets"]
                if edition
                else (next(r.sheets_count for r in calculation.roles if r.role == role) if calculation else None)
                for role in ("teacher", "manager", "member")
            },
            "result_kind": edition["kind"] if edition else None,
            **{
                key: edition[key] if edition else None
                for key in (
                    "decided_at",
                    "reason",
                    "decided_by_name",
                    "published_at",
                    "published_by",
                )
            },
            "decided_by_id": edition["decided_by"] if edition else None,
        }
        return result
