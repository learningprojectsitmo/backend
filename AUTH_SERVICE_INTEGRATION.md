# Интеграция SessionService в AuthService

## ✅ Что изменено

### 1. Обновленный AuthService

Теперь `AuthService` принимает `SessionService` как зависимость и автоматически создает сессии при входе пользователей.

#### Новые возможности:

- **Автоматическое создание сессий** при входе
- **Парсинг User-Agent** для определения браузера, ОС и устройства
- **Управление сессиями** (завершение, получение информации)
- **Обновление активности** сессий

#### Обновленный конструктор:
```python
def __init__(self, user_repository: UserRepository, session_service: SessionService):
    self._user_repository = user_repository
    self._session_service = session_service
    # ... остальная инициализация
```

### 2. Новые методы в AuthService

#### `login_for_access_token()` - обновлен
- Создает сессию автоматически при успешном входе
- Извлекает информацию об устройстве из User-Agent
- Устанавливает сессию как текущую
- Не прерывает процесс входа при ошибках создания сессии

#### `logout(token, request=None)` - новый
```python
async def logout(self, token: str, request: Request | None = None) -> bool:
    """Завершить все сессии пользователя при выходе"""
```

#### `terminate_all_other_sessions(token, current_session_id=None)` - новый
```python
async def terminate_all_other_sessions(self, token: str, current_session_id: str | None = None) -> dict:
    """Завершить все сессии кроме текущей"""
```

#### `get_user_sessions_info(token)` - новый
```python
async def get_user_sessions_info(self, token: str) -> dict:
    """Получить информацию о сессиях пользователя"""
```

#### `refresh_session_activity(token, session_id=None)` - новый
```python
async def refresh_session_activity(self, token: str, session_id: str | None = None) -> bool:
    """Обновить активность сессии для продления срока действия"""
```

### 3. Вспомогательные методы для парсинга

- `_parse_user_agent(user_agent)` - определение браузера и версии
- `_get_device_name(user_agent)` - определение типа устройства
- `_get_os_name(user_agent)` - определение операционной системы
- `_get_device_type(user_agent)` - определение типа устройства (mobile/tablet/desktop)

### 4. Обновленный контейнер dependency injection

```python
async def get_auth_service(
    user_repository: UserRepository = Depends(get_user_repository),
    session_service: SessionService = Depends(get_session_service),
) -> AuthService:
    return AuthService(user_repository, session_service)
```

## 🚀 Использование

### Стандартный вход (с автоматическим созданием сессии)

```python
from fastapi import FastAPI, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

app = FastAPI()

@app.post("/auth/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    auth_service: AuthService = Depends(get_auth_service)
):
    token = await auth_service.login_for_access_token(form_data, request)
    return token
```

### Выход с завершением сессий

```python
@app.post("/auth/logout")
async def logout(
    authorization: str = Depends(get_current_user_token),
    request: Request = None,
    auth_service: AuthService = Depends(get_auth_service)
):
    success = await auth_service.logout(authorization, request)
    return {"success": success}
```

### Завершение других сессий

```python
@app.post("/auth/terminate-other-sessions")
async def terminate_other_sessions(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    result = await auth_service.terminate_all_other_sessions(current_user.access_token)
    return result
```

### Получение информации о сессиях

```python
@app.get("/auth/sessions")
async def get_user_sessions(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    sessions_info = await auth_service.get_user_sessions_info(current_user.access_token)
    return sessions_info
```

### Обновление активности сессии

```python
@app.post("/auth/refresh-session")
async def refresh_session(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    success = await auth_service.refresh_session_activity(current_user.access_token)
    return {"success": success}
```

## 🔧 Автоматические функции

### При входе пользователя:
1. ✅ Аутентификация пользователя
2. ✅ Создание JWT токена
3. ✅ **Создание сессии** с информацией об устройстве
4. ✅ Установка сессии как текущей
5. ✅ Логирование активности

### При выходе пользователя:
1. ✅ Завершение всех сессий пользователя
2. ✅ Логирование выхода

### При каждом запросе (можно добавить middleware):
1. ✅ Обновление активности сессии
2. ✅ Продление срока действия сессии

## ⚡ Преимущества интеграции

- **Автоматическое управление сессиями** - нет необходимости вручную создавать сессии
- **Подробная информация об устройствах** - отслеживание всех подключений
- **Безопасность** - возможность завершения всех сессий при необходимости
- **Удобство API** - все методы управления в одном сервисе
- **Совместимость** - обратная совместимость с существующим кодом

## 📝 Заметки

- Создание сессии при входе **не блокирует** процесс аутентификации при ошибках
- Все ошибки логируются для отладки
- Сессии создаются только при наличии Request объекта
- Время жизни сессии соответствует времени жизни JWT токена
