from __future__ import annotations

import csv
import io
import zipfile
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.services import exam_csv_participation as participation
from src.services import exam_csv_profiles as profiles
from src.services.exam_csv_service import ExamCsvSnapshot
from src.util.csv_export import CsvExporter


def empty_snapshot():
    return ExamCsvSnapshot("test", datetime(2026, 11, 18, tzinfo=UTC), [], [], 5)


def test_combined_actual_utf8_byte_limit_includes_headers_and_boms():
    data = empty_snapshot()
    with zipfile.ZipFile(io.BytesIO(profiles.render_archive(data))) as archive:
        size = sum(item.file_size for item in archive.infolist())
    assert profiles.render_archive(data, max_bytes=size)
    with pytest.raises(HTTPException) as error:
        profiles.render_archive(data, max_bytes=size - 1)
    assert error.value.status_code == 413 and error.value.detail["code"] == "csv_export_limit_exceeded"


def test_second_file_failure_discards_archive_and_closes_every_buffer(monkeypatch):
    opened = []

    class Buffer(io.BytesIO):
        def __init__(self):
            super().__init__()
            opened.append(self)

    original = CsvExporter.write
    calls = []

    def fail_second(self, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("second CSV write failed")
        return original(self, **kwargs)

    monkeypatch.setattr(profiles, "io", SimpleNamespace(BytesIO=Buffer))
    monkeypatch.setattr(CsvExporter, "write", fail_second)
    with pytest.raises(OSError, match="second CSV"):
        profiles.render_archive(empty_snapshot())
    assert len(opened) == 3 and all(buffer.closed for buffer in opened)


def test_empty_profiles_use_shared_writer_real_csv_parser():
    with zipfile.ZipFile(io.BytesIO(profiles.render_archive(empty_snapshot()))) as archive:
        for name in archive.namelist():
            raw = archive.read(name)
            rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), delimiter=";"))
            assert len(rows) == 1 and rows[0][0] == "schema_version"
            assert raw.endswith(b"\r\n")


def test_wide_valid_questionnaire_size_error_is_explicit_413():
    n = 5000
    when = datetime(2026, 11, 18, tzinfo=UTC)
    default = {"integer": 1, "text": "text", "datetime": when, "boolean": True}
    row = {column.key: default[column.kind] for column in profiles.PARTICIPATION_COLUMNS}
    for i in range(1, n + 1):
        row[f"criterion_{i}_question_id"] = i
        row[f"criterion_{i}_text"] = "Я" * 1000
        row[f"criterion_{i}_score"] = None
    data = ExamCsvSnapshot("test", when, [], [row], n)
    with pytest.raises(HTTPException) as error:
        profiles.render_archive(data)
    assert error.value.status_code == 413


def test_preview_affiliation_expansion_is_bounded_before_rendering(monkeypatch):
    registrations = [
        {
            "attempt_id": i,
            "window_id": None,
            "project_type_id": 1,
            "registration_id": i,
            "project_id": i,
            "project_name": "p",
        }
        for i in (1, 2)
    ]
    person = {"user_id": 1, "assessor_name": "name", "role": "teacher", "own_project_ids": list(range(10))}
    monkeypatch.setattr(participation, "MAX_AFFILIATION_BYTES", 25, raising=False)
    with pytest.raises(HTTPException) as error:
        participation.participation_rows(registrations, {}, [person], {1: []}, [], {}, 5)
    assert error.value.status_code == 413
