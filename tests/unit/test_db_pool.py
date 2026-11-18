from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.core.config import Settings
from src.core.database import engine
from src.core.dependencies import get_current_user

PRODUCTION_WORKERS = 4  # Dockerfile.prod: uvicorn --workers 4
POSTGRES_DEFAULT_MAX_CONNECTIONS = 100
SUPERUSER_RESERVED = 3


def connections_per_process(config: Settings) -> int:
    """Pool + the single LISTEN connection of the exam live hub."""
    return config.DB_POOL_SIZE + config.DB_MAX_OVERFLOW + 1


def test_default_pool_of_all_production_workers_fits_the_default_max_connections():
    config = Settings()
    total = PRODUCTION_WORKERS * connections_per_process(config)
    assert total <= POSTGRES_DEFAULT_MAX_CONNECTIONS - SUPERUSER_RESERVED - 10  # room for migrations and admin sessions


def test_engine_uses_the_configured_pool():
    config = Settings()
    assert engine.pool.size() == config.DB_POOL_SIZE
    assert engine.pool._max_overflow == config.DB_MAX_OVERFLOW


def test_pool_settings_are_validated():
    with pytest.raises(ValueError):
        Settings(DB_POOL_SIZE=0)
    with pytest.raises(ValueError):
        Settings(DB_MAX_OVERFLOW=-1)


class RecordingUow:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


async def test_authentication_releases_its_transaction_before_the_handler_runs():
    user = SimpleNamespace(id=1, email="a@example.com")

    class Auth:
        async def get_current_user(self, token):  # noqa: ARG002
            return user

    uow = RecordingUow()
    assert await get_current_user(token="t", auth_service=Auth(), uow=uow) is user
    assert uow.commits == 1


async def test_failed_authentication_does_not_commit():
    class Auth:
        async def get_current_user(self, token):  # noqa: ARG002
            raise HTTPException(401)

    uow = RecordingUow()
    with pytest.raises(HTTPException):
        await get_current_user(token="t", auth_service=Auth(), uow=uow)
    assert uow.commits == 0
