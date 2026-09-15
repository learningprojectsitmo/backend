# ruff: noqa: PLR2004
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from src.model.audit import AuditLog
from src.model.auth import Session
from src.model.user import User
from src.repository.audit_repository import AuditRepository
from src.repository.ideas_repository import IdeaRepository
from src.repository.project_repository import ProjectRepository
from src.repository.role_repository import RoleRepository
from src.repository.session_repository import SessionRepository
from src.repository.user_repository import UserRepository
from src.repository.workspace_repository import WorkSpaceRepository
from src.services.admin_service import AdminService


def _make_user(user_id: int, email: str, first_name: str) -> User:
    return User(
        id=user_id,
        email=email,
        first_name=first_name,
        middle_name="",
        last_name="Примеров",
    )


def _make_session(session_id: str, user: User, is_active: bool = True) -> Session:
    now = datetime.now(UTC)
    return Session(
        id=session_id,
        user_id=user.id,
        user=user,
        device_name="Desktop",
        browser_name="Chrome",
        operating_system="Linux",
        device_type="desktop",
        ip_address="127.0.0.1",
        is_active=is_active,
        is_current=False,
        created_at=now,
        last_activity=now,
        expires_at=now + timedelta(days=30),
    )


def _make_log(log_id: int, user: User, entity_type: str = "project", action: str = "UPDATE") -> AuditLog:
    return AuditLog(
        id=log_id,
        entity_type=entity_type,
        entity_id=1,
        action=action,
        old_values=None,
        new_values={"name": "Проект"},
        performed_by=user.id,
        performed_at=datetime.now(UTC),
        user=user,
    )


def _build_service(*, sessions, logs, session_counts=None, audit_total=0, entity_counts=None) -> AdminService:
    session_repo = Mock(spec=SessionRepository)
    session_repo.get_all = AsyncMock(return_value=sessions)
    session_repo.count_all = AsyncMock(return_value=(session_counts or {}).get("total", len(sessions)))
    session_repo.count_active_all = AsyncMock(return_value=(session_counts or {}).get("active", 0))
    session_repo.count_expired_all = AsyncMock(return_value=(session_counts or {}).get("expired", 0))
    session_repo.count_active_users = AsyncMock(return_value=(session_counts or {}).get("users", 0))

    audit_repo = Mock(spec=AuditRepository)
    audit_repo.get_all_logs = AsyncMock(return_value=logs)
    audit_repo.count_all = AsyncMock(return_value=audit_total)

    counts = entity_counts or {}
    user_repo = Mock(spec=UserRepository)
    user_repo.count = AsyncMock(return_value=counts.get("users", 0))
    role_repo = Mock(spec=RoleRepository)
    role_repo.count = AsyncMock(return_value=counts.get("roles", 0))
    idea_repo = Mock(spec=IdeaRepository)
    idea_repo.count = AsyncMock(return_value=counts.get("ideas", 0))
    project_repo = Mock(spec=ProjectRepository)
    project_repo.count = AsyncMock(return_value=counts.get("projects", 0))
    workspace_repo = Mock(spec=WorkSpaceRepository)
    workspace_repo.count = AsyncMock(return_value=counts.get("workspaces", 0))

    return AdminService(user_repo, role_repo, idea_repo, project_repo, workspace_repo, session_repo, audit_repo)


class TestAdminOverview:
    @pytest.mark.asyncio
    async def test_should_return_counts_and_recent_activity(self):
        # given
        user = _make_user(1, "admin@example.com", "Admin")
        logs = [_make_log(10, user), _make_log(9, user)]
        service = _build_service(
            sessions=[],
            logs=logs,
            session_counts={"total": 20, "active": 6, "users": 4},
            entity_counts={"users": 5, "roles": 4, "ideas": 12, "projects": 8, "workspaces": 3},
        )

        # when
        result = await service.get_overview()

        # then
        assert result.total_users == 5
        assert result.total_roles == 4
        assert result.total_ideas == 12
        assert result.total_projects == 8
        assert result.total_workspaces == 3
        assert result.total_sessions == 20
        assert result.active_sessions == 6
        assert result.active_users == 4
        assert [item.id for item in result.recent_activity] == [10, 9]
        assert result.recent_activity[0].user_name == "Admin Примеров"
        assert result.recent_activity[0].user_email == "admin@example.com"


class TestAdminSessions:
    @pytest.mark.asyncio
    async def test_should_build_paginated_sessions_with_user_info(self):
        # given
        user = _make_user(1, "admin@example.com", "Admin")
        sessions = [_make_session("aaa", user), _make_session("bbb", user)]
        service = _build_service(sessions=sessions, logs=[], session_counts={"total": 2})

        # when
        result = await service.get_all_sessions(page=1, limit=20)

        # then
        assert result.total == 2
        assert result.total_pages == 1
        assert len(result.items) == 2
        assert result.items[0].id == "aaa"
        assert result.items[0].user_name == "Admin Примеров"
        assert result.items[0].user_email == "admin@example.com"
        assert result.items[0].browser_name == "Chrome"
        assert result.items[0].is_active is True

    @pytest.mark.asyncio
    async def test_should_compute_total_pages(self):
        # given
        user = _make_user(1, "admin@example.com", "Admin")
        service = _build_service(
            sessions=[_make_session("aaa", user)],
            logs=[],
            session_counts={"total": 25},
        )

        # when
        result = await service.get_all_sessions(page=2, limit=20)

        # then
        assert result.page == 2
        assert result.total == 25
        assert result.total_pages == 2


class TestAdminSessionStats:
    @pytest.mark.asyncio
    async def test_should_return_global_session_stats(self):
        # given
        service = _build_service(
            sessions=[],
            logs=[],
            session_counts={"total": 50, "active": 10, "expired": 3, "users": 7},
        )

        # when
        result = await service.get_session_stats()

        # then
        assert result.total_sessions == 50
        assert result.active_sessions == 10
        assert result.expired_sessions == 3
        assert result.active_users == 7


class TestAdminAudit:
    @pytest.mark.asyncio
    async def test_should_return_paginated_audit_logs(self):
        # given
        user = _make_user(1, "admin@example.com", "Admin")
        logs = [_make_log(10, user), _make_log(9, user)]
        service = _build_service(sessions=[], logs=logs, audit_total=30)

        # when
        result = await service.get_all_audit_logs(page=1, limit=20)

        # then
        assert result.total == 30
        assert result.total_pages == 2
        assert len(result.items) == 2
        assert result.items[0].action == "UPDATE"
        assert result.items[0].user_name == "Admin Примеров"
