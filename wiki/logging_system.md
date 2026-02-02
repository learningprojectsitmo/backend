# Система логирования

## Обзор

В приложении реализована комплексная система логирования с использованием Python `logging`. Система обеспечивает:

- **Структурированное логирование** всех операций
- **Ротацию лог-файлов** для управления размером
- **Разделение по уровням** (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **Специализированные логгеры** для разных типов событий
- **Middleware для HTTP запросов**
- **Логирование базы данных** через репозитории

## Структура логгеров

### Основные логгеры

1. **`app`** - основной логгер приложения
2. **`api`** - логирование API запросов
3. **`security`** - события безопасности и аутентификации
4. **`repository`** - операции с базой данных
5. **`auth_service`** - сервис аутентификации
6. **`<module_name>`** - логгеры конкретных модулей

### Специализированные логгеры

#### SecurityLogger
```python
from src.core.logging_config import security_logger

# Логирование попыток входа
security_logger.log_login_attempt(email, ip_address, user_agent, success=True)

# Логирование ошибок аутентификации
security_logger.log_authentication_failure(email, reason, ip_address)

# Логирование отказов в доступе
security_logger.log_permission_denied(user_id, action, resource, ip_address)

# Логирование подозрительной активности
security_logger.log_suspicious_activity(user_id, activity, details)
```

#### APILogger
```python
from src.core.logging_config import api_logger

# Логирование API запросов
api_logger.log_request(method, path, user_id, ip_address, status_code, response_time)

# Логирование ошибок API
api_logger.log_error(method, path, error, user_id)
```

## Уровни логирования

- **DEBUG** - подробная информация для отладки
- **INFO** - общая информация о работе системы
- **WARNING** - предупреждения о потенциальных проблемах
- **ERROR** - ошибки, которые не прерывают работу
- **CRITICAL** - критические ошибки

## Настройка через .env

```bash
# Уровень логирования
LOG_LEVEL=INFO

# Формат логов
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s

# Основной файл логов
LOG_FILE=app.log

# Включить файловые логи
ENABLE_FILE_LOGGING=true

# Включить консольные логи
ENABLE_CONSOLE_LOGGING=true
```

## Файлы логов

Система создает следующие файлы логов:

- **`logs/app.log`** - основные логи приложения
- **`logs/errors.log`** - только ошибки (ERROR и выше)
- **Ротация** - автоматическая ротация при размере 10MB
- **Бэкапы** - сохраняется 5 последних файлов

## Логируемые события

### Аутентификация
- Попытки входа (успешные и неуспечные)
- Ошибки аутентификации
- Валидация токенов
- Создание токенов доступа

### API запросы
- Все HTTP запросы к API
- Время выполнения запросов
- Статус коды ответов
- IP адреса клиентов
- User-Agent информация

### База данных
- CRUD операции (создание, чтение, обновление, удаление)
- Время выполнения запросов
- Ошибки базы данных
- Количество полученных записей

### Ошибки приложения
- Все исключения приложения
- Специальное логирование для DatabaseError
- Логирование AuthError и PermissionError

## Примеры использования

### Логирование в сервисах
```python
from src.core.logging_config import get_logger

class MyService:
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    async def my_method(self, data):
        self.logger.info(f"Processing data: {data}")
        try:
            result = await self.process_data(data)
            self.logger.info(f"Successfully processed data: {result}")
            return result
        except Exception as e:
            self.logger.error(f"Failed to process data: {e}")
            raise
```

### Логирование в репозиториях
```python
from src.core.logging_config import get_logger

class MyRepository:
    def __init__(self, uow):
        self.uow = uow
        self.logger = get_logger(self.__class__.__name__)

    async def get_user(self, user_id):
        self.logger.debug(f"Getting user by ID: {user_id}")
        # ... логика получения пользователя
```

## Мониторинг и алерты

### Рекомендуемые алерты
1. **Критические ошибки** - немедленные уведомления
2. **Высокая частота ошибок аутентификации** - возможная атака
3. **Длительное время ответа API** - проблемы производительности
4. **Ошибки базы данных** - проблемы с БД

### Инструменты для анализа логов
- **ELK Stack** (Elasticsearch, Logstash, Kibana)
- **Grafana + Loki**
- **CloudWatch** (AWS)
- **Cloud Logging** (Google Cloud)

## Производительность

Система логирования оптимизирована для минимального влияния на производительность:

- Асинхронное логирование
- Буферизация для файловых операций
- Исключение логирования статических путей
- Опциональное включение/отключение

## Безопасность

### Чувствительные данные
- Пароли НЕ логируются
- Токены частично маскируются
- PII данные обрабатываются с осторожностью

### Рекомендации
- Регулярно проверяйте логи на наличие чувствительных данных
- Настройте ограничения доступа к лог-файлам
- Используйте безопасное хранение логов в production
