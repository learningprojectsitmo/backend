#!/usr/bin/env python3
"""
Демонстрационный скрипт для проверки системы логирования
Запуск: python scripts/demo_logging.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Добавляем src в путь для импортов
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.config import settings
from src.core.logging_config import APILogger, SecurityLogger, get_logger, setup_logging


def demo_basic_logging():
    """Демонстрация базового логирования"""
    print("=== Демонстрация базового логирования ===")

    # Получаем логгер
    logger = get_logger("demo")

    # Логируем сообщения разных уровней
    logger.debug("Это отладочное сообщение")
    logger.info("Это информационное сообщение")
    logger.warning("Это предупреждение")
    logger.error("Это сообщение об ошибке")
    logger.critical("Это критическое сообщение")


def demo_security_logging():
    """Демонстрация логирования безопасности"""
    print("\n=== Демонстрация логирования безопасности ===")

    security_logger = SecurityLogger()

    # Логируем успешный вход
    security_logger.log_login_attempt(
        email="user@example.com",
        ip_address="192.168.1.100",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        success=True,
    )

    # Логируем неудачную попытку входа
    security_logger.log_authentication_failure(
        email="hacker@example.com", reason="Invalid credentials", ip_address="10.0.0.1"
    )

    # Логируем отказ в доступе
    security_logger.log_permission_denied(
        user_id=123, action="delete_project", resource="project_id:456", ip_address="10.0.0.2"
    )


def demo_api_logging():
    """Демонстрация логирования API"""
    print("\n=== Демонстрация логирования API ===")

    api_logger = APILogger()

    # Логируем успешный API запрос
    api_logger.log_request(
        method="GET",
        path="/api/users/123",
        user_id=123,
        ip_address="192.168.1.100",
        status_code=200,
        response_time=0.25,
    )

    # Логируем API запрос с ошибкой
    api_logger.log_request(
        method="POST",
        path="/api/projects",
        user_id=456,
        ip_address="192.168.1.101",
        status_code=400,
        response_time=0.05,
    )

    # Логируем ошибку API
    api_logger.log_error(method="DELETE", path="/api/users/789", error=Exception("User not found"), user_id=999)


def demo_repository_logging():
    """Демонстрация логирования репозитория"""
    print("\n=== Демонстрация логирования репозитория ===")

    # Имитируем работу репозитория
    repo_logger = get_logger("UserRepository")

    # Логируем операции с базой данных
    repo_logger.debug("Getting user by ID: 123")
    repo_logger.info("Successfully retrieved user with ID 123")

    repo_logger.debug("Creating new user: john@example.com")
    repo_logger.info("Created user with ID 456")

    repo_logger.info("Updating user with ID 123 - fields: ['email', 'first_name']")

    repo_logger.info("Deleting user with ID 789")
    repo_logger.warning("User with ID 789 not found for deletion")


def demo_different_levels():
    """Демонстрация разных уровней логирования"""
    print("\n=== Демонстрация уровней логирования ===")

    logger = get_logger("levels_demo")

    # Настраиваем уровень логирования
    current_level = settings.LOG_LEVEL
    print(f"Текущий уровень логирования: {current_level}")

    # Логируем на разных уровнях
    logger.debug("DEBUG: Подробная информация для отладки")
    logger.info("INFO: Общая информация о работе системы")
    logger.warning("WARNING: Предупреждение о потенциальной проблеме")
    logger.error("ERROR: Ошибка, которая не прерывает работу")
    logger.critical("CRITICAL: Критическая ошибка")


async def demo_performance_logging():
    """Демонстрация логирования производительности"""
    print("\n=== Демонстрация логирования производительности ===")

    logger = get_logger("performance_demo")

    # Имитируем медленную операцию
    start_time = time.time()
    logger.info("Starting slow operation...")

    await asyncio.sleep(0.1)  # Имитируем работу

    duration = time.time() - start_time
    logger.info(f"Slow operation completed in {duration:.3f}s")

    # Быстрая операция
    start_time = time.time()
    logger.debug("Starting fast operation...")

    await asyncio.sleep(0.01)  # Имитируем быструю работу

    duration = time.time() - start_time
    logger.debug(f"Fast operation completed in {duration:.3f}s")


def main():
    """Главная функция демонстрации"""
    print("Демонстрация системы логирования")
    print("=" * 50)

    # Настраиваем логирование
    print("Настройка системы логирования...")
    setup_logging()
    print(f"Уровень логирования: {settings.LOG_LEVEL}")
    print(f"Файл логов: {settings.LOG_FILE}")
    print(f"Консольные логи: {settings.ENABLE_CONSOLE_LOGGING}")
    print(f"Файловые логи: {settings.ENABLE_FILE_LOGGING}")
    print()

    # Запускаем демонстрации
    demo_basic_logging()
    demo_security_logging()
    demo_api_logging()
    demo_repository_logging()
    demo_different_levels()

    # Асинхронная демонстрация
    print("\nЗапуск асинхронной демонстрации...")
    asyncio.run(demo_performance_logging())

    print("\n" + "=" * 50)
    print("Демонстрация завершена!")
    print(f"Проверьте логи в файле: logs/{settings.LOG_FILE}")
    print("Проверьте ошибки в файле: logs/errors.log")


if __name__ == "__main__":
    main()
