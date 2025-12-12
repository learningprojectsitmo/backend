from src.repository.user_repository import UserRepository
from src.model.models import User
from src.schema import UserCreate, Token, UserUpdate, UserFull, UserListItem, UserListResponse

# Примеры тестов для AuthService, UserRepository и Container

## Тесты для UserRepository

```python
import pytest
from unittest.mock import Mock, MagicMock
from sqlalchemy.orm import Session

from src.repository.user_repository import UserRepository
from src.model.models import User
from src.schema import UserCreate

def test_user_repository_get_by_id():
    # Мокируем сессию
    mock_session = Mock()
    mock_user = User(id=1, email="test@example.com")
    mock_session.query.return_value.filter.return_value.first.return_value = mock_user
    
    repository = UserRepository(mock_session)
    result = repository.get_by_id(1)
    
    assert result == mock_user
    assert result.id == 1
    assert result.email == "test@example.com"

def test_user_repository_create():
    mock_session = Mock()
    repository = UserRepository(mock_session)
    
    user_data = UserCreate(
        email="test@example.com",
        first_name="Test",
        middle_name="User",
        password_string="hashed_password"
    )
    
    # Мокируем создание пользователя
    mock_user = User(
        email=user_data.email,
        first_name=user_data.first_name,
        middle_name=user_data.middle_name,
        password_hashed=user_data.password_string
    )
    mock_session.add.return_value = None
    mock_session.commit.return_value = None
    mock_session.refresh.return_value = None
    
    result = repository.create(user_data)
    
    assert result.email == user_data.email
    assert result.first_name == user_data.first_name
    assert result.middle_name == user_data.middle_name
    assert result.password_hashed == user_data.password_string

def test_user_repository_authenticate_user():
    mock_session = Mock()
    repository = UserRepository(mock_session)
    
    # Мокируем пользователя
    mock_user = User(
        id=1,
        email="test@example.com",
        password_hashed="hashed_password"
    )
    
    repository.get_by_email = Mock(return_value=mock_user)
    verify_password = Mock(return_value=True)
    
    result = repository.authenticate_user("test@example.com", "password", verify_password)
    
    assert result == mock_user
    verify_password.assert_called_once_with("password", "hashed_password")
```

## Тесты для AuthService

```python
import pytest
from unittest.mock import Mock, MagicMock
from datetime import timedelta

from services.auth_service import AuthService
from src.repository.user_repository import UserRepository
from src.model.models import User
from src.schema import UserCreate, Token
from fastapi.security import OAuth2PasswordRequestForm

def test_auth_service_authenticate_user():
    # Мокируем репозиторий
    mock_repository = Mock()
    mock_user = User(id=1, email="test@example.com")
    mock_repository.authenticate_user.return_value = mock_user
    
    # Создаем сервис
    auth_service = AuthService(mock_repository, Mock())
    
    result = auth_service.authenticate_user("test@example.com", "password")
    
    assert result == mock_user
    mock_repository.authenticate_user.assert_called_once()

def test_auth_service_create_access_token():
    mock_repository = Mock()
    auth_service = AuthService(mock_repository, Mock())
    
    token = auth_service.create_access_token({"sub": "test@example.com"})
    
    assert isinstance(token, str)
    assert len(token) > 0  # JWT токен не должен быть пустым

def test_auth_service_get_current_user():
    mock_repository = Mock()
    mock_user = User(id=1, email="test@example.com")
    mock_repository.get_by_email.return_value = mock_user
    
    auth_service = AuthService(mock_repository, Mock())
    
    # Мокируем jwt.decode
    with patch('services.auth_service.jwt.decode') as mock_decode:
        mock_decode.return_value = {"sub": "test@example.com"}
        
        result = auth_service.get_current_user("fake_token")
        
        assert result == mock_user
        mock_repository.get_by_email.assert_called_once_with("test@example.com")

@pytest.mark.asyncio
async def test_auth_service_login_for_access_token():
    mock_repository = Mock()
    mock_user = User(id=1, email="test@example.com")
    mock_repository.authenticate_user.return_value = mock_user
    
    auth_service = AuthService(mock_repository, Mock())
    
    # Создаем мок для OAuth2PasswordRequestForm
    form_data = OAuth2PasswordRequestForm(
        username="test@example.com",
        password="password"
    )
    
    with patch.object(auth_service, 'create_access_token') as mock_create_token:
        mock_create_token.return_value = "fake_jwt_token"
        
        result = await auth_service.login_for_access_token(form_data)
        
        assert isinstance(result, Token)
        assert result.access_token == "fake_jwt_token"
        assert result.token_type == "bearer"
```

## Тесты для UserService

```python
import pytest
from unittest.mock import Mock

from services.user_service import UserService
from src.repository.user_repository import UserRepository
from src.model.models import User
from src.schema import UserCreate, UserUpdate, UserFull, UserListItem, UserListResponse

def test_user_service_create_user():
    mock_repository = Mock()
    mock_user = User(
        id=1,
        email="test@example.com",
        first_name="Test",
        middle_name="User",
        password_hashed="hashed_password"
    )
    mock_repository.create.return_value = mock_user
    
    user_service = UserService(mock_repository, Mock())
    
    user_data = UserCreate(
        email="test@example.com",
        first_name="Test",
        middle_name="User",
        password_string="plain_password"
    )
    
    with patch('services.user_service.hash_password') as mock_hash:
        mock_hash.return_value = "hashed_password"
        
        result = user_service.create_user(user_data)
        
        assert result == mock_user
        mock_hash.assert_called_once_with("plain_password")
        mock_repository.create.assert_called_once()

def test_user_service_get_users_paginated():
    mock_repository = Mock()
    
    # Мокируем список пользователей
    mock_users = [
        User(id=1, email="user1@example.com", first_name="User", middle_name="One"),
        User(id=2, email="user2@example.com", first_name="User", middle_name="Two")
    ]
    
    mock_repository.get_multi.return_value = mock_users
    mock_repository.count.return_value = 2
    
    user_service = UserService(mock_repository, Mock())
    
    result = user_service.get_users_paginated(page=1, limit=10)
    
    assert isinstance(result, UserListResponse)
    assert result.total == 2
    assert len(result.items) == 2
    assert result.page == 1
    assert result.limit == 10
    assert result.total_pages == 1
```

## Интеграционные тесты

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock

from main import app
from core.container import Container

@pytest.fixture
def mock_container():
    """Фикстура для мокирования Container"""
    with patch('core.dependencies.Container') as mock_container_class:
        mock_auth_service = Mock()
        mock_user_service = Mock()
        
        mock_container = Mock()
        mock_container.auth_service = mock_auth_service
        mock_container.user_service = mock_user_service
        mock_container_class.return_value = mock_container
        
        yield {
            'container': mock_container,
            'auth_service': mock_auth_service,
            'user_service': mock_user_service
        }

def test_login_endpoint(mock_container):
    client = TestClient(app)
    
    # Мокируем ответ AuthService
    mock_token = Token(access_token="fake_token", token_type="bearer")
    mock_container['auth_service'].login_for_access_token.return_value = mock_token
    
    response = client.post(
        "/auth/token",
        data={"username": "test@example.com", "password": "password"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    assert response.status_code == 200
    assert response.json()["access_token"] == "fake_token"
    assert response.json()["token_type"] == "bearer"

def test_get_current_user_endpoint(mock_container):
    client = TestClient(app)
    
    # Мокируем пользователя
    mock_user = User(
        id=1,
        email="test@example.com",
        first_name="Test",
        middle_name="User"
    )
    mock_container['auth_service'].get_current_user.return_value = mock_user
    
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer fake_token"}
    )
    
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"
    assert response.json()["first_name"] == "Test"

def test_create_user_endpoint(mock_container):
    client = TestClient(app)
    
    # Мокируем создание пользователя
    mock_user = User(
        id=1,
        email="test@example.com",
        first_name="Test",
        middle_name="User"
    )
    mock_container['user_service'].create_user.return_value = mock_user
    
    response = client.post(
        "/users/",
        json={
            "email": "test@example.com",
            "first_name": "Test",
            "middle_name": "User",
            "password_string": "password"
        }
    )
    
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"
    assert response.json()["first_name"] == "Test"
```

## Запуск тестов

```bash
# Установка pytest
pip install pytest pytest-asyncio

# Запуск всех тестов
pytest

# Запуск с подробным выводом
pytest -v

# Запуск конкретного файла тестов
pytest tests/test_auth_service.py

# Запуск с покрытием кода
pytest --cov=services --cov=repository
```

## Мокирование для тестов

Для unit тестов рекомендуется использовать:

1. **Mock** для мокирования репозиториев и сервисов
2. **patch** для мокирования внешних зависимостей (JWT, БД)
3. **MagicMock** для более сложных сценариев

Для интеграционных тестов:

1. **TestClient** от FastAPI
2. **Фикстуры** для настройки тестового окружения
3. **Временные базы данных** для тестирования БД операций