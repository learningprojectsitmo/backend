# Тесты для слоя сервисов

Этот пакет содержит unit тесты для всех сервисов приложения, написанные с использованием паттерна **given-when-then**.

## Структура тестов

```
tests/
├── unit/                          # Unit тесты
│   ├── conftest.py               # Общие фикстуры
│   ├── test_auth_service.py      # Тесты AuthService
│   ├── test_user_service.py      # Тесты UserService
│   ├── test_project_service.py   # Тесты ProjectService
│   ├── test_resume_service.py    # Тесты ResumeService
│   ├── test_base_services.py     # Тесты базовых сервисов
│   └── __init__.py
├── __init__.py
├── README.md
└── pytest.ini                   # Конфигурация pytest
```

## Установка зависимостей

```bash
# Основные тестовые зависимости
pip install pytest pytest-asyncio pytest-cov

# Дополнительные зависимости для качества кода
pip install pytest-mock pytest-xdist
```

## Запуск тестов

### Все тесты
```bash
pytest
```

### Unit тесты
```bash
pytest tests/unit/
```

### Конкретный файл тестов
```bash
pytest tests/unit/test_auth_service.py
```

### С подробным выводом
```bash
pytest -v
```

### С покрытием кода
```bash
pytest --cov=src --cov-report=html
```

### Только определенные маркеры
```bash
pytest -m "unit"          # Только unit тесты
pytest -m "auth"          # Только тесты аутентификации
pytest -m "service"       # Только тесты сервисов
```

### Параллельный запуск
```bash
pytest -n auto            # Автоматическое определение количества процессов
pytest -n 4               # 4 процесса
```

## Паттерн given-when-then

Все тесты следуют структуре **given-when-then**:

```python
def test_should_example_functionality():
    # given - Подготовка данных и моков
    mock_repository = Mock()
    mock_object = Mock(id=1, name="Test Object")
    mock_repository.get_by_id.return_value = mock_object

    service = SomeService(mock_repository)

    # when - Выполнение действия
    result = service.get_object_by_id(1)

    # then - Проверка результата
    assert result == mock_object
    mock_repository.get_by_id.assert_called_once_with(1)
```

### Принципы написания тестов

1. **Given** - Подготовка:
   - Создание моков зависимостей
   - Настройка ожидаемых возвращаемых значений
   - Инициализация тестируемого сервиса

2. **When** - Действие:
   - Вызов метода, который тестируется
   - Передача необходимых параметров

3. **Then** - Проверка:
   - Проверка возвращаемого значения
   - Проверка вызовов зависимостей
   - Проверка побочных эффектов

## Покрытие кода

Для генерации отчета о покрытии кода:

```bash
# Покрытие с HTML отчетом
pytest --cov=src --cov-report=html --cov-report=term

# Открыть HTML отчет
open htmlcov/index.html  # macOS
start htmlcov/index.html # Windows
xdg-open htmlcov/index.html # Linux
```

## Мокирование зависимостей

Все тесты мокают зависимости сервисов:

- **Репозитории** - полностью мокаются
- **Внешние сервисы** - мокаются через `@patch`
- **База данных** - не используется в unit тестах
- **JWT токены** - мокаются для тестов аутентификации

## Тестируемые сервисы

### AuthService
- Аутентификация пользователей
- Создание и проверка JWT токенов
- Проверка паролей
- Получение текущего пользователя

### UserService
- CRUD операции для пользователей
- Пагинация
- Проверка существования пользователя
- Хеширование паролей

### ProjectService
- CRUD операции для проектов
- Поиск в стиле GitLab
- Фильтрация по автору
- Получение популярных поисковых терминов

### ResumeService
- CRUD операции для резюме
- Проверка прав доступа (только автор может изменять)
- Публичные и приватные резюме
- Поиск резюме

### Базовые сервисы
- BaseService - базовые операции
- SearchableBaseService - операции с поиском

## Лучшие практики

1. **Один тест - одна функциональность**
2. **Используйте описательные названия тестов**
3. **Мокайте все внешние зависимости**
4. **Проверяйте не только возвращаемые значения, но и вызовы зависимостей**
5. **Используйте фикстуры для повторяющихся данных**
6. **Изолируйте тесты друг от друга**

## Добавление новых тестов

1. Создайте файл `test_[service_name].py` в `tests/unit/`
2. Импортируйте необходимые модули
3. Создайте класс `Test[ServiceName]`
4. Добавьте тестовые методы с паттерном given-when-then
5. Используйте существующие фикстуры из `conftest.py`

Пример:
```python
import pytest
from unittest.mock import Mock

from src.services.new_service import NewService

class TestNewService:
    def test_should_do_something(self):
        # given
        mock_repository = Mock()
        service = NewService(mock_repository)

        # when
        result = service.do_something()

        # then
        assert result is not None
```

## Устранение проблем

### Ошибки импорта
```bash
# Убедитесь, что PYTHONPATH настроен правильно
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Проблемы с асинхронными тестами
```bash
# Убедитесь, что используется pytest-asyncio
pytest --asyncio-mode=auto
```

### Медленные тесты
```bash
# Запустите только быстрые тесты
pytest -m "not slow"
```
