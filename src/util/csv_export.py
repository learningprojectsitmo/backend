from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from io import StringIO
from typing import Literal, TextIO

type CsvScalar = str | int | Decimal | bool | datetime | None
type CsvKind = Literal["text", "integer", "decimal", "boolean", "datetime"]

_KINDS = frozenset(("text", "integer", "decimal", "boolean", "datetime"))
_SURROGATE_START = 0xD800
_SURROGATE_END = 0xDFFF
_LAST_ASCII_CONTROL = 0x1F
_ASCII_DELETE = 0x7F
_BITS_PER_DECIMAL_DIGIT_BOUND = 4


class CsvExportError(ValueError):
    """Invalid export schema, options or row data; the caller discards the output."""


@dataclass(frozen=True)
class CsvColumn:
    key: str
    header: str
    kind: CsvKind
    nullable: bool = False


@dataclass(frozen=True)
class CsvOptions:
    delimiter: str = ";"
    quotechar: str = '"'
    lineterminator: str = "\r\n"
    max_field_chars: int = 1_000_000
    max_row_chars: int = 5_000_000
    spreadsheet_safe: bool = True


@dataclass(frozen=True)
class ExportStats:
    row_count: int


class CsvExporter:
    """Write one profile without owning the source, stream or transport lifecycle."""

    def write(
        self,
        *,
        columns: Sequence[CsvColumn],
        rows: Iterable[Mapping[str, CsvScalar]],
        target: TextIO,
        options: CsvOptions = CsvOptions(),
    ) -> ExportStats:
        _validate_options(options)
        columns = tuple(columns)
        _validate_columns(columns, options)
        keys = frozenset(column.key for column in columns)
        headers = tuple(_spreadsheet_text(column.header, options) for column in columns)
        if len(set(headers)) != len(headers):
            raise CsvExportError("Headers must remain unique after spreadsheet text conversion")
        target.write(_render_record(headers, options))
        row_count = 0
        for row in rows:
            if not isinstance(row, Mapping) or row.keys() != keys:
                raise CsvExportError("A row must contain exactly the schema's keys")
            values = (_serialize(column, row[column.key], options) for column in columns)
            target.write(_render_record(values, options))
            row_count += 1
        return ExportStats(row_count=row_count)


def _validate_options(options: CsvOptions) -> None:
    if not isinstance(options, CsvOptions):
        raise CsvExportError("Options must be CsvOptions")
    for character in (options.delimiter, options.quotechar):
        if not isinstance(character, str) or len(character) != 1 or character in "\r\n\x00":
            raise CsvExportError("Delimiter and quotechar must be single non-control characters")
        _validate_text(character)
    if options.delimiter == options.quotechar:
        raise CsvExportError("Delimiter and quotechar must differ")
    if options.lineterminator not in ("\n", "\r\n"):
        raise CsvExportError("Line terminator must be LF or CRLF")
    for limit in (options.max_field_chars, options.max_row_chars):
        if type(limit) is not int or limit <= 0:
            raise CsvExportError("Character limits must be positive integers")
    if type(options.spreadsheet_safe) is not bool:
        raise CsvExportError("spreadsheet_safe must be boolean")


def _validate_columns(columns: tuple[CsvColumn, ...], options: CsvOptions) -> None:
    if not columns:
        raise CsvExportError("At least one column is required")
    keys: set[str] = set()
    headers: set[str] = set()
    for column in columns:
        if not isinstance(column, CsvColumn):
            raise CsvExportError("Schema entries must be CsvColumn")
        if not isinstance(column.key, str) or not column.key:
            raise CsvExportError("Column keys must be non-empty strings")
        if not isinstance(column.header, str) or not column.header:
            raise CsvExportError("Column headers must be non-empty strings")
        if len(column.key) > options.max_field_chars or len(column.header) > options.max_field_chars:
            raise CsvExportError("Column key or header exceeds max_field_chars")
        _validate_text(column.key)
        _validate_text(column.header)
        if not isinstance(column.kind, str) or column.kind not in _KINDS or type(column.nullable) is not bool:
            raise CsvExportError("Invalid column kind or nullable flag")
        if column.key in keys or column.header in headers:
            raise CsvExportError("Column keys and headers must be unique")
        keys.add(column.key)
        headers.add(column.header)


def _validate_text(value: str) -> None:
    if "\x00" in value or any(_SURROGATE_START <= ord(character) <= _SURROGATE_END for character in value):
        raise CsvExportError("NUL and Unicode surrogate characters are not supported")


def _serialize(column: CsvColumn, value: CsvScalar, options: CsvOptions) -> str:
    if value is None:
        if not column.nullable:
            raise CsvExportError(f"Column {column.key!r} does not allow null")
        return ""
    if column.kind == "text" and isinstance(value, str):
        result = _spreadsheet_text(value, options)
        _validate_text(result)
        return result
    if column.kind == "integer" and type(value) is int:
        limit = min(options.max_field_chars, options.max_row_chars)
        if value.bit_length() > limit * _BITS_PER_DECIMAL_DIGIT_BOUND:
            raise CsvExportError("Integer exceeds the field or row budget")
        try:
            return str(value)
        except ValueError as error:
            raise CsvExportError("Integer exceeds the interpreter's conversion limit") from error
    if column.kind == "decimal" and isinstance(value, Decimal) and value.is_finite():
        _check_decimal_size(value, min(options.max_field_chars, options.max_row_chars))
        return format(value, "f")
    if column.kind == "boolean" and type(value) is bool:
        return "true" if value else "false"
    if column.kind == "datetime" and isinstance(value, datetime) and value.utcoffset() is not None:
        return value.isoformat()
    raise CsvExportError(f"Column {column.key!r} requires a valid {column.kind} value")


def _spreadsheet_text(value: str, options: CsvOptions) -> str:
    if len(value) > min(options.max_field_chars, options.max_row_chars):
        raise CsvExportError("Text exceeds max_field_chars")
    if not options.spreadsheet_safe:
        return value
    dangerous = value.startswith(("\t", "\r", "\n"))
    for character in value:
        if character.isspace() or ord(character) <= _LAST_ASCII_CONTROL or ord(character) == _ASCII_DELETE:
            continue
        dangerous = dangerous or character in "=+-@"
        break
    return "'" + value if dangerous else value


def _check_decimal_size(value: Decimal, limit: int) -> None:
    """Bound the coefficient before inspecting it, then bound fixed-point zeros."""
    # General format caps precision without padding small values. Exact total
    # comparison also rejects lost trailing zeros before as_tuple copies digits.
    bounded = Decimal(format(value, f".{limit}g"))
    if value.compare_total(bounded) != 0:
        raise CsvExportError("Decimal coefficient exceeds the field or row budget")
    sign, digits, exponent = value.as_tuple()
    if exponent >= 0:
        length = sign + (1 if value.is_zero() else len(digits) + exponent)
    else:
        length = sign + max(len(digits) + exponent, 1) + 1 - exponent
    if length > limit:
        raise CsvExportError("Decimal exceeds max_field_chars")


def _render_record(values: Iterable[str], options: CsvOptions) -> str:
    cells: list[str] = []
    length = len(options.lineterminator)
    for value in values:
        if len(value) > options.max_field_chars:
            raise CsvExportError("Field exceeds max_field_chars")
        length += len(value) + bool(cells)
        if length > options.max_row_chars:
            raise CsvExportError("Row exceeds max_row_chars")
        cells.append(value)
    buffer = StringIO(newline="")
    csv.writer(
        buffer,
        delimiter=options.delimiter,
        quotechar=options.quotechar,
        lineterminator=options.lineterminator,
    ).writerow(cells)
    record = buffer.getvalue()
    if len(record) > options.max_row_chars:
        raise CsvExportError("CSV quoting exceeds max_row_chars")
    return record
