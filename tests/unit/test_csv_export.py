from __future__ import annotations

import csv
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO, StringIO, TextIOWrapper

import pytest

from src.util.csv_export import CsvColumn, CsvExporter, CsvExportError, CsvOptions


def test_writes_columns_in_schema_order_from_one_shot_source() -> None:
    columns = (
        CsvColumn(key="project", header="Команда", kind="text"),
        CsvColumn(key="score", header="Балл", kind="integer"),
    )
    rows = iter(({"score": 19, "project": "Альфа"}, {"score": 0, "project": "Бета"}))
    target = StringIO(newline="")

    stats = CsvExporter().write(columns=columns, rows=rows, target=target)

    assert target.getvalue() == "Команда;Балл\r\nАльфа;19\r\nБета;0\r\n"
    assert stats.row_count == 2
    assert next(rows, None) is None
    assert not target.closed


@pytest.mark.parametrize(
    ("kind", "value", "expected"),
    [
        ("text", "Привет", "Привет"),
        ("integer", -4, "-4"),
        ("decimal", Decimal("19.50"), "19.50"),
        ("decimal", Decimal("1E+2"), "100"),
        ("boolean", True, "true"),
        ("boolean", False, "false"),
        ("datetime", datetime(2026, 11, 9, 14, 0, tzinfo=UTC), "2026-11-09T14:00:00+00:00"),
    ],
)
def test_serializes_typed_values_without_locale(kind, value, expected) -> None:
    target = StringIO(newline="")
    CsvExporter().write(columns=(CsvColumn("value", "Value", kind),), rows=({"value": value},), target=target)
    assert list(csv.reader(StringIO(target.getvalue()), delimiter=";")) == [["Value"], [expected]]


def test_empty_source_still_has_headers_and_nullable_is_distinct_from_zero() -> None:
    columns = (CsvColumn("score", "Балл", "integer", nullable=True),)
    target = StringIO(newline="")
    stats = CsvExporter().write(columns=columns, rows=iter(()), target=target)
    assert target.getvalue() == "Балл\r\n"
    assert stats.row_count == 0
    target = StringIO(newline="")
    CsvExporter().write(columns=columns, rows=({"score": None}, {"score": 0}), target=target)
    assert list(csv.reader(StringIO(target.getvalue()), delimiter=";")) == [["Балл"], [""], ["0"]]


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("text", 42),
        ("integer", True),
        ("integer", 1.5),
        ("decimal", 1.5),
        ("decimal", Decimal("NaN")),
        ("decimal", Decimal("Infinity")),
        ("boolean", 1),
        ("datetime", datetime(2026, 11, 9)),
        ("text", None),
        ("text", ["nested"]),
        ("text", {"nested": "value"}),
        ("text", "NUL\x00text"),
        ("text", "invalid\ud800"),
    ],
)
def test_rejects_invalid_scalar_without_writing_the_bad_row(kind, value) -> None:
    target = StringIO(newline="")
    with pytest.raises(ValueError):
        CsvExporter().write(columns=(CsvColumn("value", "Value", kind),), rows=({"value": value},), target=target)
    assert target.getvalue() == "Value\r\n"


@pytest.mark.parametrize("row", [{}, {"name": "x", "extra": "y"}, ["x"]])
def test_rejects_rows_that_do_not_match_the_schema(row) -> None:
    target = StringIO(newline="")
    with pytest.raises(ValueError):
        CsvExporter().write(columns=(CsvColumn("name", "Name", "text"),), rows=(row,), target=target)
    assert target.getvalue() == "Name\r\n"


@pytest.mark.parametrize(
    "columns",
    [
        (),
        (CsvColumn("", "Name", "text"),),
        (CsvColumn("name", "", "text"),),
        (CsvColumn("name", "Name", "unknown"),),
        (CsvColumn("name", "Name", "text", nullable="yes"),),
        (CsvColumn("name", "Name", "text"), CsvColumn("name", "Other", "text")),
        (CsvColumn("name", "Name", "text"), CsvColumn("other", "Name", "text")),
        (CsvColumn("name", "bad\x00header", "text"),),
    ],
)
def test_invalid_schema_fails_before_output_or_reading_rows(columns) -> None:
    def rows():
        pytest.fail("Invalid schema must not consume rows")
        yield {}

    target = StringIO(newline="")
    with pytest.raises(ValueError):
        CsvExporter().write(columns=columns, rows=rows(), target=target)
    assert target.getvalue() == ""


@pytest.mark.parametrize(
    "changes",
    [
        {"delimiter": ""},
        {"delimiter": ";;"},
        {"delimiter": "\n"},
        {"delimiter": '"'},
        {"quotechar": ""},
        {"quotechar": "\x00"},
        {"lineterminator": ""},
        {"max_field_chars": 0},
        {"max_row_chars": True},
    ],
)
def test_invalid_options_fail_before_output(changes) -> None:
    target = StringIO(newline="")
    with pytest.raises(ValueError):
        CsvExporter().write(
            columns=(CsvColumn("name", "Name", "text"),),
            rows=iter(()),
            target=target,
            options=CsvOptions(**changes),
        )
    assert target.getvalue() == ""


def test_one_pass_source_is_written_before_requesting_the_next_row() -> None:
    target = StringIO(newline="")

    class OnePassRows:
        def __init__(self):
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            assert self.iterations == 1, "Rows were read twice"
            for index in range(1000):
                if index:
                    assert target.getvalue().endswith(f"{index - 1}\r\n"), "Writer buffered the source"
                yield {"value": index}

    stats = CsvExporter().write(columns=(CsvColumn("value", "Value", "integer"),), rows=OnePassRows(), target=target)
    assert stats.row_count == 1000


def test_reuses_one_exporter_with_two_profiles_and_distinct_options_in_parallel() -> None:
    exporter = CsvExporter()

    def export_profile(profile):
        target = StringIO(newline="")
        if profile == "teams":
            exporter.write(columns=(CsvColumn("team", "Team", "text"),), rows=({"team": "Alpha"},), target=target)
        else:
            exporter.write(
                columns=(CsvColumn("user", "User", "integer"), CsvColumn("sent", "Sent", "boolean")),
                rows=({"sent": True, "user": 7},),
                target=target,
                options=CsvOptions(delimiter=",", lineterminator="\n"),
            )
        return target.getvalue()

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(export_profile, ("teams", "people")))
    assert result == ["Team\r\nAlpha\r\n", "User,Sent\n7,true\n"]


def test_propagates_source_error_and_keeps_caller_stream_open() -> None:
    def rows():
        yield {"value": 1}
        raise RuntimeError("Source failed")

    target = StringIO(newline="")
    with pytest.raises(RuntimeError, match="Source failed"):
        CsvExporter().write(columns=(CsvColumn("value", "Value", "integer"),), rows=rows(), target=target)
    assert target.getvalue() == "Value\r\n1\r\n"
    assert not target.closed


def test_propagates_write_error_without_closing_the_callers_stream() -> None:
    class BrokenStream(StringIO):
        def write(self, _value):
            raise OSError("Disk full")

    target = BrokenStream(newline="")
    with pytest.raises(OSError, match="Disk full"):
        CsvExporter().write(columns=(CsvColumn("value", "Value", "text"),), rows=(), target=target)
    assert not target.closed


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("=1+1", "'=1+1"),
        ("+SUM(A1:A2)", "'+SUM(A1:A2)"),
        ("-12", "'-12"),
        ("@A1", "'@A1"),
        ("  =1+1", "'  =1+1"),
        ("\t=1+1", "'\t=1+1"),
        ("\rhello", "'\rhello"),
        ("\nhello", "'\nhello"),
        ("\x01 =1+1", "'\x01 =1+1"),
        ("\u2003=1+1", "'\u2003=1+1"),
        ('Текст;"цитата"\nстрока', 'Текст;"цитата"\nстрока'),
        (" space", " space"),
        ("", ""),
    ],
)
def test_neutralizes_spreadsheet_text_before_csv_quoting(text, expected) -> None:
    target = StringIO(newline="")
    CsvExporter().write(columns=(CsvColumn("text", "Text", "text"),), rows=({"text": text},), target=target)
    assert list(csv.reader(StringIO(target.getvalue(), newline=""), delimiter=";")) == [["Text"], [expected]]


def test_header_is_also_spreadsheet_text() -> None:
    target = StringIO(newline="")
    CsvExporter().write(columns=(CsvColumn("text", " =1+1", "text"),), rows=(), target=target)
    assert target.getvalue() == "' =1+1\r\n"


def test_rejects_headers_that_collide_after_safe_text_conversion() -> None:
    target = StringIO(newline="")
    with pytest.raises(ValueError):
        CsvExporter().write(
            columns=(CsvColumn("a", "=1+1", "text"), CsvColumn("b", "'=1+1", "text")), rows=(), target=target
        )
    assert target.getvalue() == ""


def test_can_explicitly_disable_spreadsheet_policy_for_machine_reading() -> None:
    target = StringIO(newline="")
    CsvExporter().write(
        columns=(CsvColumn("text", "Text", "text"),),
        rows=({"text": "=1+1"},),
        target=target,
        options=CsvOptions(spreadsheet_safe=False),
    )
    assert target.getvalue() == "Text\r\n=1+1\r\n"


@pytest.mark.parametrize("text", ["first\rsecond", "first\nsecond", "first\r\nsecond"])
def test_lf_output_still_quotes_both_record_separator_characters(text) -> None:
    target = StringIO(newline="")
    CsvExporter().write(
        columns=(CsvColumn("text", "Text", "text"),),
        rows=({"text": text},),
        target=target,
        options=CsvOptions(lineterminator="\n"),
    )
    assert list(csv.reader(StringIO(target.getvalue(), newline=""), delimiter=";")) == [["Text"], [text]]


@pytest.mark.parametrize(
    ("kind", "value"),
    [("text", "x" * 9), ("text", "=1234567"), ("decimal", Decimal("1E+100000")), ("decimal", Decimal("1E-100000"))],
)
def test_field_budget_applies_before_emitting_the_row(kind, value) -> None:
    target = StringIO(newline="")
    with pytest.raises(ValueError):
        CsvExporter().write(
            columns=(CsvColumn("v", "Value", kind),),
            rows=({"v": value},),
            target=target,
            options=CsvOptions(max_field_chars=8),
        )
    assert target.getvalue() == "Value\r\n"


def test_row_budget_counts_csv_quote_expansion() -> None:
    target = StringIO(newline="")
    with pytest.raises(ValueError):
        CsvExporter().write(
            columns=(CsvColumn("v", "Value", "text"),),
            rows=({"v": '"""'},),
            target=target,
            options=CsvOptions(max_row_chars=9),
        )
    assert target.getvalue() == "Value\r\n"


def test_header_obeys_the_field_budget_before_output() -> None:
    target = StringIO(newline="")
    with pytest.raises(ValueError):
        CsvExporter().write(
            columns=(CsvColumn("v", "Too long", "text"),),
            rows=(),
            target=target,
            options=CsvOptions(max_field_chars=5),
        )
    assert target.getvalue() == ""


def test_caller_controls_encoding_with_one_bom_and_crlf() -> None:
    output = BytesIO()
    target = TextIOWrapper(output, encoding="utf-8-sig", newline="")
    try:
        CsvExporter().write(
            columns=(CsvColumn("name", "Имя", "text"), CsvColumn("score", "Балл", "decimal")),
            rows=({"name": 'Аня; "текст"\nстрока', "score": Decimal("19.50")},),
            target=target,
        )
        target.flush()
        expected = 'Имя;Балл\r\n"Аня; ""текст""\nстрока";19.50\r\n'
        assert output.getvalue() == b"\xef\xbb\xbf" + expected.encode("utf-8")
    finally:
        target.detach()


@pytest.mark.parametrize("case", ["text", "header", "decimal_integer", "decimal_fraction", "decimal_trailing"])
@pytest.mark.parametrize("limited_by", ["field", "row"])
def test_oversized_input_is_rejected_before_allocating_a_proportional_copy(case, limited_by) -> None:
    column = CsvColumn("v", "V", "text")
    value = "=" + "1" * 999_999
    if case == "header":
        column = CsvColumn("v", value, "text")
        value = "ok"
    elif case.startswith("decimal"):
        column = CsvColumn("v", "V", "decimal")
        if case == "decimal_trailing":
            value = Decimal("0.1" + "0" * 1_000_000)
        else:
            value = Decimal(("0." if case == "decimal_fraction" else "") + "1" * 1_000_000)
    options = (
        CsvOptions(max_field_chars=8, max_row_chars=16)
        if limited_by == "field"
        else CsvOptions(max_field_chars=1_000_000, max_row_chars=8)
    )
    target = StringIO(newline="")
    # Construct the hostile input before tracing: only writer allocations count.
    tracemalloc.start()
    try:
        with pytest.raises(ValueError):
            CsvExporter().write(columns=(column,), rows=({"v": value},), target=target, options=options)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # csv.writer has a fixed record buffer; the ceiling allows that constant
    # overhead while rejecting a new copy of the million-character input.
    assert peak < 256_000, "Field rejection allocated a copy of the oversized input"


@pytest.mark.parametrize(
    ("value", "limit", "expected"),
    [("19.50", 5, "19.50"), ("-0", 2, "-0"), ("0E+2000000000", 1, "0"), ("-0E+2000000000", 2, "-0")],
)
def test_decimal_preflight_preserves_scale_and_signed_zero(value, limit, expected) -> None:
    target = StringIO(newline="")
    CsvExporter().write(
        columns=(CsvColumn("v", "V", "decimal"),),
        rows=({"v": Decimal(value)},),
        target=target,
        options=CsvOptions(max_field_chars=limit),
    )
    assert target.getvalue() == f"V\r\n{expected}\r\n"


def test_huge_integer_is_rejected_by_export_budget_before_integer_formatting() -> None:
    target = StringIO(newline="")
    with pytest.raises(CsvExportError):
        CsvExporter().write(
            columns=(CsvColumn("v", "V", "integer"),),
            rows=({"v": 10**100_000},),
            target=target,
            options=CsvOptions(max_field_chars=8),
        )
    assert target.getvalue() == "V\r\n"
