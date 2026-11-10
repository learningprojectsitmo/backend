from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration
PREVIOUS_REVISION = "b2c3d4e5f6a7"
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def isolated_database():
    """Never migrate the supplied DB: create and drop a uniquely owned test DB."""
    explicit_url = os.environ.get("RUBRIC_TEST_DATABASE_URL")
    if not explicit_url:
        pytest.skip("Set RUBRIC_TEST_DATABASE_URL to a disposable PostgreSQL with CREATE DATABASE privileges")
    url = make_url(explicit_url)
    if url.get_backend_name() != "postgresql":
        pytest.fail("RUBRIC_TEST_DATABASE_URL must point to PostgreSQL")
    database_name = f"rubric_test_{uuid4().hex}"
    admin = create_engine(url.set(drivername="postgresql+psycopg2"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    own_url = url.set(database=database_name)
    engine = create_engine(own_url.set(drivername="postgresql+psycopg2"))
    try:
        yield engine, own_url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
        admin.dispose()


def migrate(url, *args):
    env = dict(os.environ, DATABASE_URL=url, AUTO_CREATE_TABLES="false", ENVIRONMENT="ci")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_mapping_migration_preserves_old_types_and_enforces_constraint(isolated_database):
    engine, url = isolated_database
    migrate(url, "upgrade", PREVIOUS_REVISION)
    with engine.begin() as connection:
        type_id = connection.execute(
            text("INSERT INTO project_type (name, description) VALUES ('Курсовой проект', 'Старый тип') RETURNING id")
        ).scalar_one()
        stage_id = connection.execute(
            text(
                "INSERT INTO project_stage (project_type_id, name, \"order\", requires_approval, visible_to_participants) VALUES (:type_id, 'Защита', 0, true, true) RETURNING id"
            ),
            {"type_id": type_id},
        ).scalar_one()
    migrate(url, "upgrade", "head")
    migrate(url, "check")
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT name, assessment_kind FROM project_type WHERE id=:id"), {"id": type_id}
        ).one()
        assert tuple(row) == ("Курсовой проект", None)
    for kind in ["product", "technical_integration", "research", None]:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE project_type SET assessment_kind=:kind WHERE id=:id"), {"kind": kind, "id": type_id}
            )
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT assessment_kind FROM project_type WHERE id=:id"), {"id": type_id}
                ).scalar_one()
                == kind
            )
    with pytest.raises(IntegrityError) as error, engine.begin() as connection:
        connection.execute(text("UPDATE project_type SET assessment_kind='unknown' WHERE id=:id"), {"id": type_id})
    assert error.value.orig.diag.constraint_name == "ck_project_type_assessment_kind"
    migrate(url, "downgrade", PREVIOUS_REVISION)
    assert "assessment_kind" not in {c["name"] for c in inspect(engine).get_columns("project_type")}
    migrate(url, "upgrade", "head")
    migrate(url, "check")
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT name, description, assessment_kind FROM project_type WHERE id=:id"), {"id": type_id}
        ).one() == ("Курсовой проект", "Старый тип", None)
        assert connection.execute(
            text('SELECT id, name, "order", requires_approval FROM project_stage WHERE project_type_id=:id'),
            {"id": type_id},
        ).one() == (stage_id, "Защита", 0, True)
