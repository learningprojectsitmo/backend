from __future__ import annotations

import math
from datetime import datetime

from src.model.exam_attempt import ExamAttempt
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.schema.exam_attempt import AttemptRead, AttemptWindowRead


def remaining_seconds(attempt: ExamAttempt, now: datetime) -> int:
    if attempt.status == "finished":
        return 0
    frozen = attempt.paused_at or attempt.postponed_at or now
    return math.floor((attempt.phase_deadline - frozen).total_seconds())


async def attempt_read(repository: ExamAttemptRepository, attempt: ExamAttempt, *, now: datetime) -> AttemptRead:
    window = await repository.window(attempt.id) if attempt.status == "finished" else None
    return AttemptRead(
        id=attempt.id,
        workspace_id=attempt.workspace_id,
        exam_id=attempt.exam_id,
        registration_id=attempt.registration_id,
        project_id=attempt.project_id,
        project_type_id=attempt.project_type_id,
        status=attempt.status,
        version=attempt.version,
        settings_version=attempt.settings_version,
        started_at=attempt.started_at,
        phase_started_at=attempt.phase_started_at,
        phase_deadline=attempt.phase_deadline,
        paused_at=attempt.paused_at,
        postponed_at=attempt.postponed_at,
        postponed_phase=attempt.postponed_phase,
        paused_seconds=attempt.paused_seconds,
        finished_at=attempt.finished_at,
        created_by=attempt.created_by,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
        remaining_seconds=remaining_seconds(attempt, now),
        server_now=now,
        assessment_window=None
        if window is None
        else AttemptWindowRead(
            opened_at=window.opened_at,
            closes_at=window.closes_at,
            settings_version=window.settings_version,
            project_type_id=window.project_type_id,
        ),
    )
