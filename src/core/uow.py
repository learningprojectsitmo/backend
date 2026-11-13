from __future__ import annotations

from typing import Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal
from src.core.exam_live_protocol import EXAM_LIVE_CHANNEL, ExamLiveNotification, normalize_change


class IUnitOfWork(Protocol):
    session: AsyncSession

    def mark_exam_changed(self, exam_id: int, change: str) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
    async def __aenter__(self) -> IUnitOfWork: ...
    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None: ...


class SqlAlchemyUoW:
    def __init__(self) -> None:
        self.session_factory = AsyncSessionLocal
        self._exam_changes: dict[int, set[str]] = {}

    async def __aenter__(self) -> SqlAlchemyUoW:
        self.session = self.session_factory()
        return self

    async def __aexit__(self, _exc_type: object, exc: object, _tb: object) -> None:  # type: ignore[override]
        try:
            if exc:
                await self.session.rollback()
            else:
                await self.commit()
        finally:
            self._exam_changes.clear()
            await self.session.close()

    def mark_exam_changed(self, exam_id: int, change: str) -> None:
        if exam_id <= 0:
            raise ValueError("exam_id must be positive")
        self._exam_changes.setdefault(exam_id, set()).add(normalize_change(change))

    async def _publish_exam_changes(self) -> None:
        if not self._exam_changes:
            return
        for exam_id in sorted(self._exam_changes):
            stream_seq = await self.session.scalar(
                text(
                    """
                    UPDATE exam
                    SET stream_seq = stream_seq + 1
                    WHERE id = :exam_id
                    RETURNING stream_seq
                    """
                ),
                {"exam_id": exam_id},
            )
            if stream_seq is None:
                raise RuntimeError(f"Exam {exam_id} disappeared while publishing live changes")
            notification = ExamLiveNotification(
                exam_id=exam_id,
                stream_seq=int(stream_seq),
                changed=tuple(sorted(self._exam_changes[exam_id])),
            )
            await self.session.execute(
                text("SELECT pg_notify(:channel, :payload)"),
                {"channel": EXAM_LIVE_CHANNEL, "payload": notification.to_payload()},
            )

    async def commit(self) -> None:
        try:
            await self._publish_exam_changes()
            await self.session.commit()
        finally:
            self._exam_changes.clear()

    async def rollback(self) -> None:
        try:
            await self.session.rollback()
        finally:
            self._exam_changes.clear()
