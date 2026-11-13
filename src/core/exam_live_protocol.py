from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, cast

EXAM_LIVE_CHANNEL = "exam_live"
MAX_POSTGRES_NOTIFY_BYTES = 8000

ExamLiveChange = Literal["queue", "attempt", "settings", "window", "exam"]
EXAM_LIVE_CHANGES: frozenset[str] = frozenset({"queue", "attempt", "settings", "window", "exam"})


def normalize_change(change: str) -> ExamLiveChange:
    if change not in EXAM_LIVE_CHANGES:
        raise ValueError(f"Unknown exam live change: {change}")
    return cast("ExamLiveChange", change)


@dataclass(frozen=True, slots=True)
class ExamLiveNotification:
    workspace_id: int
    exam_id: int
    stream_seq: int
    changed: tuple[str, ...]

    def to_payload(self) -> str:
        payload = json.dumps(
            {
                "workspace_id": self.workspace_id,
                "exam_id": self.exam_id,
                "stream_seq": self.stream_seq,
                "changed": list(self.changed),
            },
            separators=(",", ":"),
            ensure_ascii=True,
        )
        if len(payload.encode("utf-8")) > MAX_POSTGRES_NOTIFY_BYTES:
            raise ValueError("Exam live notification exceeds PostgreSQL NOTIFY limit")
        return payload

    @classmethod
    def from_payload(cls, payload: str) -> ExamLiveNotification:
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise TypeError("Exam live notification must be an object")
        workspace_id = data.get("workspace_id")
        exam_id = data.get("exam_id")
        stream_seq = data.get("stream_seq")
        changed = data.get("changed")
        if not isinstance(workspace_id, int) or isinstance(workspace_id, bool) or workspace_id <= 0:
            raise ValueError("Exam live notification has invalid workspace_id")
        if not isinstance(exam_id, int) or isinstance(exam_id, bool) or exam_id <= 0:
            raise ValueError("Exam live notification has invalid exam_id")
        if not isinstance(stream_seq, int) or isinstance(stream_seq, bool) or stream_seq < 0:
            raise ValueError("Exam live notification has invalid stream_seq")
        if not isinstance(changed, list) or not all(isinstance(item, str) for item in changed):
            raise ValueError("Exam live notification has invalid changed list")
        return cls(
            workspace_id=workspace_id,
            exam_id=exam_id,
            stream_seq=stream_seq,
            changed=tuple(sorted({normalize_change(item) for item in changed})),
        )
