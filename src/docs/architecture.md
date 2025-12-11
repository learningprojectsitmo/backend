# Архитектура AuthService, UserRepository и Container

## Обзор изменений

Была создана полная архитектура для работы с аутентификацией, пользователями, проектами и резюме, используя dependency injection pattern с dependency_injector.

## Созданные компоненты

### 1. Базовые классы

#### `backend/src/repository/base_repository.py`
- Базовый класс для всех репозиториев
- Предоставляет общие методы работы с базой данных
- Управление сессиями и транзакциями

#### `backend/src/services/base_service.py`
- Базовый класс для всех сервисов
- CRUD операции
- Управление жизненным циклом репозиториев

### 2. Специализированные компоненты

#### `backend/src/repository/user_repository.py`
- Наследуется от BaseRepository
- Специализированные методы для работы с пользователями
- Аутентификация пользователей

#### `backend/src/repository/project_repository.py`
- Наследуется от BaseRepository
- Специализированные методы для работы с проектами
- Поиск по автору, пагинация

#### `backend/src/repository/resume_repository.py`
- Наследуется от BaseRepository
- Специализированные методы для работы с резюме
- Поиск по автору, пагинация

#### `backend/src/services/auth_service.py`
- Наследуется от BaseService
- JWT токены, аутентификация
- Получение текущего пользователя
- Полностью интегрирован с dependency injection

#### `backend/src/services/user_service.py`
- CRUD операции для пользователей
- Пагинация, создание, обновление, удаление
- Хеширование паролей

#### `backend/src/services/project_service.py`
- CRUD операции для проектов
- Пагинация, создание, обновление, удаление
- Проверка прав доступа (только автор может изменять)

#### `backend/src/services/resume_service.py`
- CRUD операции для резюме
- Пагинация, создание, обновление, удаление
- Проверка прав доступа (только автор может изменять)

### 3. Конфигурация зависимостей

#### `backend/src/core/container.py`
- Центральная конфигурация всех зависимостей
- Wiring configuration для автоматического инжектирования
- Provider'ы для репозиториев и сервисов

## Архитектурные слои

### 1. Endpoint слой для API
- `backend/src/api/v1/endpoints/auth_new.py` - аутентификация
- `backend/src/api/v1/endpoints/user.py` - пользователи
- `backend/src/api/v1/endpoints/project.py` - проекты
- `backend/src/api/v1/endpoints/resume.py` - резюме

### 2. Middleware интеграция
- Автоматическое закрытие сессий
- @inject декоратор для сервисов
- Управление жизненным циклом

### 3. Безопасность
- JWT аутентификация
- Хеширование паролей
- Проверка прав доступа

### 4. Производительность
- Эффективное управление сессиями БД
- Пагинация для больших списков
- Оптимизированные запросы

### 5. Масштабируемость
- Легко добавлять новые репозитории
- Легко добавлять новые сервисы
- Модульная архитектура

## Примеры использования

#### `backend/src/api/v1/endpoints/auth_new.py`
```python
@auth_router.post("/token")
@inject
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: AuthService = Depends(Provide[Container.auth_service])
) -> Token:
    return await auth_service.login_for_access_token(form_data)
```

#### `backend/src/api/v1/endpoints/user.py`
```python
@user_router.get("/{user_id}", response_model=UserFull)
@inject
async def get_user(
    user_id: int,
    user_service: UserService = Depends(Provide[Container.user_service]),
    current_user: User = Depends(get_current_user)
):
    user = user_service.get_user_by_id(user_id)
    return UserFull.model_validate(user)
```

#### `backend/src/api/v1/endpoints/project.py`
```python
@project_router.get("/{project_id}", response_model=ProjectFull)
@inject
async def fetch_project(
    project_id: int,
    project_service: ProjectService = Depends(Provide[Container.project_service]),
    current_user: User = Depends(get_current_user)
):
    project = project_service.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="There is no project with that id!")
    
    return ProjectFull.model_validate(project)
```

#### `backend/src/api/v1/endpoints/resume.py`
```python
@resume_router.get("/{resume_id}", response_model=ResumeFull)
@inject
async def fetch_resume(
    resume_id: int,
    resume_service: ResumeService = Depends(Provide[Container.resume_service]),
    current_user: User = Depends(get_current_user)
):
    resume = resume_service.get_resume_by_id(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="There is no resume with that id!")
    
    return ResumeFull.model_validate(resume)
```

## Ключевые особенности архитектуры

### 1. Dependency Injection
- Все зависимости настраиваются через Container
- Автоматическое инжектирование в endpoints
- Никаких ручных передач db_session

### 2. Слой абстракции
- Repository слой для работы с БД
- Service слой для бизнес-логики
- Endpoint слой для API

### 3. Middleware интеграция
- Автоматическое закрытие сессий
- @inject декоратор для сервисов
- Управление жизненным циклом

### 4. Безопасность
- JWT аутентификация
- Хеширование паролей
- Проверка прав доступа

## Использование

### Для аутентификации:
```python
# Получение токена
POST /auth/token
# Форма: username=email, password=password

# Получение информации о текущем пользователе
GET /auth/me
# Headers: Authorization: Bearer <token>
```

### Для работы с пользователями:
```python
# Создание пользователя
POST /users/
# Body: UserCreate schema

# Получение пользователя
GET /users/{user_id}

# Обновление пользователя
PUT /users/{user_id}
# Body: UserUpdate schema

# Удаление пользователя
DELETE /users/{user_id}

# Получение списка пользователей
GET /users/?page=1&limit=10
```

### Для работы с проектами:
```python
# Создание проекта
POST /projects/
# Body: ProjectCreate schema

# Получение проекта
GET /projects/{project_id}

# Обновление проекта
PATCH /projects/{project_id}
# Body: ProjectUpdate schema
# Только автор проекта

# Удаление проекта
DELETE /projects/{project_id}
# Только автор проекта

# Получение списка проектов
GET /projects/?page=1&limit=10
```

### Для работы с резюме:
```python
# Создание резюме
POST /resumes/
# Body: ResumeCreate schema

# Получение резюме
GET /resumes/{resume_id}

# Обновление резюме
PATCH /resumes/{resume_id}
# Body: ResumeUpdate schema
# Только автор резюме

# Удаление резюме
DELETE /resumes/{resume_id}
# Только автор резюме

# Получение списка резюме
GET /resumes/?page=1&limit=10
```

## Преимущества

1. **Тестируемость**: Легко мокировать зависимости
2. **Поддержка**: Четкое разделение ответственности
3. **Масштабируемость**: Легко добавлять новые функции
4. **Безопасность**: Централизованная проверка прав доступа
5. **Производительность**: Эффективное управление ресурсами