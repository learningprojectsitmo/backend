from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest
from fastapi.security import OAuth2PasswordRequestForm

from src.model.models import Project, Resume, User
from src.schema import Token, UserCreate
from src.schema.project import ProjectCreate
from src.schema.resume import ResumeCreate


@pytest.fixture
def mock_user():
    """Фикстура для мока пользователя"""
    return User(
        id=1,
        email="test@example.com",
        first_name="Test",
        middle_name="User",
        password_hashed="hashed_password",
        is_active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def mock_project():
    """Фикстура для мока проекта"""
    return Project(
        id=1,
        name="Test Project",
        description="Test Description",
        author_id=1,
        status="active",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def mock_resume():
    """Фикстура для мока резюме"""
    return Resume(
        id=1,
        title="Senior Developer",
        description="Experienced Python developer",
        user_id=1,
        is_public=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def mock_user_repository(mock_user):
    """Фикстура для мока репозитория пользователей"""
    repository = Mock()
    repository.get_by_id.return_value = mock_user
    repository.get_by_email.return_value = mock_user
    repository.create.return_value = mock_user
    repository.update.return_value = mock_user
    repository.delete.return_value = True
    repository.exists.return_value = True
    repository.count.return_value = 1
    repository.get_multi.return_value = [mock_user]
    repository.authenticate_user.return_value = mock_user
    return repository


@pytest.fixture
def mock_project_repository(mock_project):
    """Фикстура для мока репозитория проектов"""
    repository = Mock()
    repository.get_by_id.return_value = mock_project
    repository.create.return_value = mock_project
    repository.update.return_value = mock_project
    repository.delete.return_value = True
    repository.exists.return_value = True
    repository.count.return_value = 1
    repository.get_multi.return_value = [mock_project]
    repository.get_by_author_id.return_value = [mock_project]
    repository.search.return_value = ([mock_project], 1)
    repository.get_popular_search_terms.return_value = ["python", "javascript"]
    repository.get_available_filters.return_value = {"status": ["active", "inactive"]}
    return repository


@pytest.fixture
def mock_resume_repository(mock_resume):
    """Фикстура для мока репозитория резюме"""
    repository = Mock()
    repository.get_by_id.return_value = mock_resume
    repository.create.return_value = mock_resume
    repository.update.return_value = mock_resume
    repository.delete.return_value = True
    repository.exists.return_value = True
    repository.count.return_value = 1
    repository.get_multi.return_value = [mock_resume]
    repository.get_by_user_id.return_value = [mock_resume]
    repository.get_public_resumes.return_value = [mock_resume]
    repository.search.return_value = ([mock_resume], 1)
    repository.get_popular_search_terms.return_value = ["python", "developer"]
    repository.get_available_filters.return_value = {"experience_level": ["junior", "senior"]}
    return repository


@pytest.fixture
def mock_auth_service(mock_user):
    """Фикстура для мока AuthService"""
    service = Mock()
    service.authenticate_user.return_value = mock_user
    service.create_access_token.return_value = "fake_jwt_token"
    service.verify_password.return_value = True
    service.get_current_user.return_value = mock_user
    service.login_for_access_token.return_value = Token(access_token="fake_jwt_token", token_type="bearer")
    return service


@pytest.fixture
def user_create_data():
    """Фикстура для данных создания пользователя"""
    return UserCreate(email="test@example.com", first_name="Test", middle_name="User", password_string="plain_password")


@pytest.fixture
def project_create_data():
    """Фикстура для данных создания проекта"""
    return ProjectCreate(name="Test Project", description="Test Description", author_id=1)


@pytest.fixture
def resume_create_data():
    """Фикстура для данных создания резюме"""
    return ResumeCreate(title="Senior Developer", description="Experienced Python developer", user_id=1, is_public=True)


@pytest.fixture
def oauth2_form_data():
    """Фикстура для данных формы OAuth2"""
    return OAuth2PasswordRequestForm(username="test@example.com", password="password")


@pytest.fixture
def mock_uow():
    """Фикстура для мока Unit of Work"""
    uow = Mock()
    uow.session = Mock()
    return uow


@pytest.fixture(autouse=True)
def reset_mocks():
    """Автоматическая фикстура для сброса всех моков после каждого теста"""
    yield
    # Моки будут автоматически сброшены после каждого теста
    # благодаря области видимости function
