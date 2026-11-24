from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from src.schema.exam_queue import (
    EtaCertainty,
    EtaCurrentRead,
    EtaItemRead,
    EtaReason,
    QueueEtaRead,
)


@dataclass(frozen=True)
class EtaTiming:
    presentation_seconds: int
    questions_seconds: int
    transition_seconds: int


@dataclass(frozen=True)
class EtaCurrentState:
    registration_id: int
    attempt_id: int
    status: Literal["speaking", "questions"]
    paused: bool
    phase_remaining_seconds: int
    overdue_seconds: int
    settings_version: int
    timing: EtaTiming


@dataclass(frozen=True)
class EtaBreak:
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class EtaWaitingState:
    registration_id: int
    position: int
    state: Literal["waiting", "postponed"]
    timing: EtaTiming
    postponed_phase: Literal["speaking", "questions"] | None = None
    planned_start_at: datetime | None = None


def full_slot_seconds(timing: EtaTiming) -> int:
    return timing.presentation_seconds + timing.questions_seconds + timing.transition_seconds


def current_slot_seconds(current: EtaCurrentState) -> int:
    """Remaining full slot of the running attempt, including following phases and transition."""
    if current.overdue_seconds > 0:
        return 0
    following = current.timing.questions_seconds if current.status == "speaking" else 0
    return max(0, current.phase_remaining_seconds) + following + current.timing.transition_seconds


def waiting_slot_seconds(waiting: EtaWaitingState) -> int:
    """Expected full slot of a waiting team.

    A returned postponed attempt restarts the timer at the full duration of its postponed
    phase (see #108), so teams behind it must use that phase, not the frozen remainder.
    """
    if waiting.state == "postponed":
        if waiting.postponed_phase == "questions":
            return waiting.timing.questions_seconds + waiting.timing.transition_seconds
        if waiting.postponed_phase == "speaking":
            return full_slot_seconds(waiting.timing)
    return full_slot_seconds(waiting.timing)


def _certainty_and_reason(
    current: EtaCurrentState | None, now: datetime, exam_starts_at: datetime, exam_started: bool
) -> tuple[EtaCertainty, EtaReason | None]:
    if current is not None and current.paused:
        return "lower_bound", "paused"
    if current is not None and current.overdue_seconds > 0:
        return "lower_bound", "overdue"
    if current is None and now < exam_starts_at and not exam_started:
        return "certain", "before_start"
    return "certain", None


def _eta_seconds(eta_at: datetime, now: datetime) -> int:
    return max(0, math.floor((eta_at - now).total_seconds()))


def build_queue_eta(
    *,
    now: datetime,
    exam_starts_at: datetime,
    current: EtaCurrentState | None,
    waiting: Sequence[EtaWaitingState],
    exam_started: bool = False,
    breaks: Sequence[EtaBreak] = (),
) -> QueueEtaRead:
    certainty, reason = _certainty_and_reason(current, now, exam_starts_at, exam_started)

    cursor = now
    if current is None:
        cursor = now if exam_started else max(now, exam_starts_at)
        current_read = None
    else:
        cursor = now + timedelta(seconds=current_slot_seconds(current))
        current_read = EtaCurrentRead(
            registration_id=current.registration_id,
            attempt_id=current.attempt_id,
            status=current.status,
            paused=current.paused,
            phase_remaining_seconds=max(0, current.phase_remaining_seconds),
            slot_remaining_seconds=current_slot_seconds(current),
            overdue_seconds=max(0, current.overdue_seconds),
            settings_version=current.settings_version,
        )

    upcoming_breaks: deque[EtaBreak] = deque()
    for pause in sorted(breaks, key=lambda item: item.starts_at):
        if pause.starts_at > now:
            upcoming_breaks.append(pause)
        elif now < pause.ends_at:
            cursor = max(cursor, pause.ends_at)

    items: list[EtaItemRead] = []
    for team in sorted(waiting, key=lambda item: (item.position, item.registration_id)):
        duration = timedelta(seconds=waiting_slot_seconds(team))
        while upcoming_breaks:
            pause = upcoming_breaks[0]
            scheduled_after_break = team.planned_start_at is not None and team.planned_start_at >= pause.ends_at
            if not scheduled_after_break and cursor + duration <= pause.starts_at:
                break
            # The live queue can compress empty slots. Add the break's duration
            # without treating other gaps in the timetable as waiting time.
            cursor += pause.ends_at - pause.starts_at
            upcoming_breaks.popleft()
        eta_at = cursor
        items.append(
            EtaItemRead(
                registration_id=team.registration_id,
                position=team.position,
                state=team.state,
                eta_seconds=_eta_seconds(eta_at, now),
                eta_at=eta_at,
                certainty=certainty,
                reason=reason,
            )
        )
        cursor += duration

    return QueueEtaRead(current=current_read, items=items)
