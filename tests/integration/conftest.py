from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.uow import SqlAlchemyUoW

REPO_ROOT = Path(__file__).resolve().parents[2]


def migrate(url: str, *args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=dict(os.environ, DATABASE_URL=url, AUTO_CREATE_TABLES="false", ENVIRONMENT="ci"),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def run_migrations():
    return migrate


@pytest.fixture
def question_database_url() -> Iterator[str]:
    explicit = os.environ.get("QUESTION_TEST_DATABASE_URL")
    if not explicit:
        pytest.skip("Set QUESTION_TEST_DATABASE_URL to disposable PostgreSQL with CREATE DATABASE privilege")
    url = make_url(explicit)
    if url.get_backend_name() != "postgresql":
        pytest.fail("QUESTION_TEST_DATABASE_URL must use PostgreSQL")
    name = f"question_test_{uuid4().hex}"
    admin = create_engine(url.set(drivername="postgresql+psycopg2"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield url.set(database=name, drivername="postgresql+asyncpg").render_as_string(hide_password=False)
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest_asyncio.fixture(loop_scope="function")
async def question_db(question_database_url):
    migrate(question_database_url, "upgrade", "head")
    engine = create_async_engine(question_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    def uow():
        instance = SqlAlchemyUoW()
        instance.session_factory = factory
        return instance

    try:
        yield engine, uow
    finally:
        await engine.dispose()
