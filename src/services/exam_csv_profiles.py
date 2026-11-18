from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import HTTPException

from src.util.csv_export import CsvColumn, CsvExporter, CsvExportLimitError

if TYPE_CHECKING:
    from src.services.exam_csv_service import ExamCsvSnapshot

MAX_CSV_BYTES = 50 * 1024 * 1024


def _columns(spec):
    return tuple(CsvColumn(key, key, kind, nullable) for key, kind, nullable in spec)


COMMON_COLUMNS = _columns(
    (
        ("schema_version", "text", False),
        ("export_id", "text", False),
        ("snapshot_at", "datetime", False),
        ("workspace_id", "integer", False),
        ("exam_id", "integer", False),
        ("exam_title", "text", False),
        ("registration_id", "integer", False),
        ("project_id", "integer", False),
        ("project_name", "text", False),
        ("project_type_id", "integer", False),
    )
)
REGISTER_COLUMNS = COMMON_COLUMNS + _columns(
    (
        ("project_type_name", "text", False),
        ("registration_status", "text", False),
        ("attempt_id", "integer", True),
        ("presence", "text", False),
        ("defense_status", "text", False),
        ("queue_hold", "text", True),
        ("started_at", "datetime", True),
        ("finished_at", "datetime", True),
        ("postponed_at", "datetime", True),
        ("eligible_count", "integer", True),
        ("submitted_count", "integer", True),
        ("not_submitted_count", "integer", True),
        ("excluded_count", "integer", True),
        ("decision_state", "text", False),
        ("calculated_score", "decimal", True),
        ("final_score", "decimal", True),
        ("max_score", "decimal", False),
        ("teacher_weight", "integer", False),
        ("manager_weight", "integer", False),
        ("member_weight", "integer", False),
        ("settings_version", "integer", False),
        ("sheet_max", "integer", False),
        ("result_id", "integer", True),
        ("result_version", "integer", True),
        ("result_teacher_sheets", "integer", True),
        ("result_manager_sheets", "integer", True),
        ("result_member_sheets", "integer", True),
        ("used_weight", "integer", True),
        ("result_kind", "text", True),
        ("decided_by_id", "integer", True),
        ("decided_by_name", "text", True),
        ("decided_at", "datetime", True),
        ("reason", "text", True),
        ("published_at", "datetime", True),
        ("published_by", "integer", True),
    )
)
PARTICIPATION_COLUMNS = COMMON_COLUMNS + _columns(
    (
        ("attempt_id", "integer", False),
        ("assessor_id", "integer", False),
        ("assessor_name", "text", False),
        ("role", "text", False),
        ("own_project_ids", "text", False),
        ("audience_source", "text", False),
        ("admitted", "boolean", True),
        ("exclusion_reason", "text", True),
        ("response_status", "text", False),
        ("submission_version", "integer", True),
        ("submitted_at", "datetime", True),
        ("total", "integer", True),
    )
)


@dataclass
class _ByteBudget:
    remaining: int

    def consume(self, count: int) -> None:
        if count > self.remaining:
            raise HTTPException(413, detail={"code": "csv_export_limit_exceeded", "message": "CSV byte limit exceeded"})
        self.remaining -= count


class _Utf8Target:
    """Text sink with one BOM and a shared pre-write bound on actual encoded bytes."""

    def __init__(self, stream: io.BytesIO, budget: _ByteBudget):
        self._stream = stream
        self._budget = budget
        budget.consume(3)
        stream.write(b"\xef\xbb\xbf")

    def write(self, value: str) -> int:
        data = value.encode("utf-8")
        self._budget.consume(len(data))
        self._stream.write(data)
        return len(value)


def _utc_rows(rows):
    for row in rows:
        yield {key: value.astimezone(UTC) if isinstance(value, datetime) else value for key, value in row.items()}


def render_archive(snapshot: ExamCsvSnapshot, *, max_bytes: int = MAX_CSV_BYTES) -> bytes:
    """No partial success or temporary paths: all owned buffers close on any BaseException."""
    criteria = tuple(
        column
        for index in range(1, snapshot.criterion_count + 1)
        for column in _columns(
            (
                (f"criterion_{index}_question_id", "integer", True),
                (f"criterion_{index}_text", "text", True),
                (f"criterion_{index}_score", "integer", True),
            )
        )
    )
    budget = _ByteBudget(max_bytes)
    with io.BytesIO() as output:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, columns, rows in (
                ("assessment-register.csv", REGISTER_COLUMNS, snapshot.register),
                ("assessment-participation.csv", PARTICIPATION_COLUMNS + criteria, snapshot.participation),
            ):
                with io.BytesIO() as csv_buffer:
                    try:
                        CsvExporter().write(
                            columns=columns, rows=_utc_rows(rows), target=_Utf8Target(csv_buffer, budget)
                        )
                    except CsvExportLimitError as error:
                        raise HTTPException(
                            413, detail={"code": "csv_export_limit_exceeded", "message": str(error)}
                        ) from error
                    archive.writestr(name, csv_buffer.getvalue())
        return output.getvalue()
