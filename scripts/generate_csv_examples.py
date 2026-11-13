from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from src.util.csv_export import CsvColumn, CsvExporter, CsvScalar  # noqa: E402


def team_rows() -> Iterator[Mapping[str, CsvScalar]]:
    yield {
        "demo_team": 'Демо «Альфа»; команда "А"',
        "note": "Первая строка\nВторая строка",
        "items": 0,
        "adjustment": Decimal("-1.25"),
        "active": True,
        "recorded_at": datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
    }
    yield {
        "demo_team": "Демо Бета",
        "note": None,
        "items": -2,
        "adjustment": Decimal("0"),
        "active": False,
        "recorded_at": datetime(2026, 11, 9, 12, 1, tzinfo=UTC),
    }
    yield {
        "demo_team": "Демо Гамма",
        "note": "  =SUM(1;2)",
        "items": 3,
        "adjustment": Decimal("2.50"),
        "active": True,
        "recorded_at": datetime(2026, 11, 9, 12, 2, tzinfo=UTC),
    }


def participant_rows() -> Iterator[Mapping[str, CsvScalar]]:
    yield {
        "demo_participant": "Участник D-01",
        "demo_team": "Демо Альфа",
        "comment": 'Искусственный текст: "кавычки"; разделитель',
        "items": 0,
        "adjustment": Decimal("-0.50"),
        "active": True,
    }
    yield {
        "demo_participant": "Участник D-02",
        "demo_team": "Демо Бета",
        "comment": "\t=1+1",
        "items": -1,
        "adjustment": Decimal("0"),
        "active": False,
    }
    yield {
        "demo_participant": "Участник D-03",
        "demo_team": "Демо Гамма",
        "comment": "@SUM(1;2)",
        "items": 1,
        "adjustment": Decimal("1.25"),
        "active": True,
    }
    yield {
        "demo_participant": "Участник D-04",
        "demo_team": "Демо Альфа",
        "comment": None,
        "items": 2,
        "adjustment": Decimal("3.00"),
        "active": True,
    }


def write_example(
    output_dir: Path,
    filename: str,
    columns: Sequence[CsvColumn],
    rows: Iterator[Mapping[str, CsvScalar]],
) -> None:
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=output_dir,
            prefix=f".{filename}.",
            suffix=".tmp",
            delete=False,
        ) as target:
            temporary_path = Path(target.name)
            CsvExporter().write(columns=columns, rows=rows, target=target)
            target.flush()
        temporary_path.replace(output_dir / filename)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic examples of two independent CSV profiles.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for generated CSV files")
    output_dir = parser.parse_args().output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    team_columns = (
        CsvColumn("demo_team", "Демо-команда", "text"),
        CsvColumn("note", "Заметка", "text", nullable=True),
        CsvColumn("items", "Количество", "integer"),
        CsvColumn("adjustment", "Коррекция", "decimal"),
        CsvColumn("active", "Активна", "boolean"),
        CsvColumn("recorded_at", "Условное время", "datetime"),
    )
    participant_columns = (
        CsvColumn("demo_participant", "Демо-участник", "text"),
        CsvColumn("demo_team", "Демо-команда", "text"),
        CsvColumn("comment", "Комментарий", "text", nullable=True),
        CsvColumn("items", "Количество", "integer"),
        CsvColumn("adjustment", "Коррекция", "decimal"),
        CsvColumn("active", "Активен", "boolean"),
    )
    write_example(output_dir, "teams-demo.csv", team_columns, team_rows())
    write_example(output_dir, "participants-demo.csv", participant_columns, participant_rows())
    print("teams-demo.csv")
    print("participants-demo.csv")


if __name__ == "__main__":
    main()
