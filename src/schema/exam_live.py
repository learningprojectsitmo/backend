from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.schema.exam_queue import QueueRead

ExamLiveReason = Literal["connected", "reconnect", "changed", "resync"]
ExamLiveChange = Literal["queue", "attempt", "settings", "window", "exam"]
ExamLiveRole = Literal["organizer", "viewer"]
ExamLiveWindowState = Literal["open", "closed"]


class ExamLiveDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExamLiveAccessRead(ExamLiveDTO):
    role: ExamLiveRole
    can_manage: bool


class ExamLiveExamRead(ExamLiveDTO):
    id: int
    workspace_id: int
    status: Literal["draft", "published"]
    settings_version: int


class ExamLiveWindowRead(ExamLiveDTO):
    attempt_id: int
    registration_id: int
    project_id: int
    project_type_id: int
    opened_at: datetime
    closes_at: datetime
    settings_version: int
    state: ExamLiveWindowState


class ExamLiveSnapshotRead(ExamLiveDTO):
    type: Literal["snapshot"] = "snapshot"
    contract_version: int = 1
    reason: ExamLiveReason
    stream_seq: int
    server_now: datetime
    stale: bool
    changed: list[ExamLiveChange] = Field(default_factory=list)
    exam: ExamLiveExamRead
    queue: QueueRead
    assessment_windows: list[ExamLiveWindowRead] = Field(default_factory=list)


class ExamLiveHelloRead(ExamLiveDTO):
    type: Literal["hello"] = "hello"
    contract_version: int = 1
    access: ExamLiveAccessRead
    server_now: datetime


class ExamLiveHeartbeatRead(ExamLiveDTO):
    type: Literal["heartbeat"] = "heartbeat"
    contract_version: int = 1
    stream_seq: int
    server_now: datetime
    queue_revision: int
    settings_version: int
    stale: bool


class ExamLiveErrorRead(ExamLiveDTO):
    type: Literal["error"] = "error"
    code: str
    message: str
