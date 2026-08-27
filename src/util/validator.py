from __future__ import annotations

import re
from typing import Any, ClassVar


class NameValidator:
    """Валидатор ФИО.

    Разрешает и кириллицу, и латиницу (а также дефис, апостроф, точку и пробел),
    чтобы поддерживать иностранные имена (напр. "Jean-Luc", "O'Brien", "Анна-Мария").
    Запрещает цифры и прочие символы.
    """

    # Первый символ — буква любого алфавита; далее буквы, дефис, апостроф, точка.
    TOKEN_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"^[^\W\d_](?:[^\W\d_]|['\-\.])*$", re.UNICODE
    )

    @classmethod
    def _clean(cls, value: Any | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("Имя должно быть строкой")
        cleaned = value.strip()
        return cleaned if cleaned else None

    @classmethod
    def _validate(cls, value: str, field: str) -> str:
        if any(ch.isdigit() for ch in value):
            raise ValueError(f"{field} не может содержать цифры")

        if re.search(r"\s{2,}", value):
            raise ValueError(f"{field} не должно содержать двойных пробелов")

        for token in value.split():
            if not cls.TOKEN_PATTERN.match(token):
                raise ValueError(
                    f"{field} может содержать только буквы, дефис, апостроф и точку. "
                    f"Ошибка в части «{token}»"
                )
        return value

    @classmethod
    def validate_name(cls, value: Any | None, field: str = "Имя") -> str:
        """Валидатор обязательного поля ФИО."""
        cleaned = cls._clean(value)
        if cleaned is None:
            raise ValueError(f"{field} обязательно для заполнения")
        return cls._validate(cleaned, field)

    @classmethod
    def validate_name_optional(cls, value: Any | None, field: str = "Отчество") -> str | None:
        """Валидатор необязательного поля ФИО (отчество)."""
        cleaned = cls._clean(value)
        if cleaned is None:
            return None
        return cls._validate(cleaned, field)


class TelegramValidator:
    """Валидатор для Telegram nickname"""

    # Регулярное выражение для проверки корректности Telegram ника
    # Ник должен начинаться с @
    # Длина ника без @: от 5 до 32 символов
    TG_NICKNAME_PATTERN: ClassVar[re.Pattern] = re.compile(r"^@[a-zA-Z0-9_]{5,32}$")

    # Минимальная длина ника без @
    TG_NICKNAME_MIN_LENGTH: ClassVar[int] = 5

    # Максимальная длина ника без @
    TG_NICKNAME_MAX_LENGTH: ClassVar[int] = 32

    @classmethod
    def validate_tg_nickname(cls, value: Any | None) -> str | None:
        """
        Валидатор для поля tg_nickname

        Args:
            value: Значение поля tg_nickname

        Returns:
            Валидное значение или None

        Raises:
            ValueError: Если значение не соответствует требованиям
        """
        if value is None:
            return None

        if not isinstance(value, str):
            raise TypeError("Telegram ник должен быть строкой")

        # Убираем лишние пробелы
        value = value.strip()

        if not value:
            return None

        # Проверка на наличие символа @
        if not value.startswith("@"):
            raise ValueError("Telegram ник должен начинаться с символа @")

        # Проверка на допустимые символы и длину
        if not cls.TG_NICKNAME_PATTERN.match(value):
            raise ValueError(
                f"Telegram ник может содержать только буквы, цифры и "
                f"подчеркивания. Длина ника без @ должна быть от "
                f"{cls.TG_NICKNAME_MIN_LENGTH} до {cls.TG_NICKNAME_MAX_LENGTH} "
                f"символов"
            )

        return value

    @classmethod
    def validate_tg_nickname_optional(cls, value: Any | None) -> str | None:
        """
        Валидатор для опционального поля tg_nickname

        Args:
            value: Значение поля tg_nickname

        Returns:
            Валидное значение или None
        """
        if value is None:
            return None

        return cls.validate_tg_nickname(value)

    @classmethod
    def normalize_tg_nickname(cls, value: str | None) -> str | None:
        """
        Нормализация Telegram ника (приведение к единому формату)

        Args:
            value: Значение поля tg_nickname

        Returns:
            Нормализованное значение или None
        """
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        # Приводим к нижнему регистру (Telegram ники регистронезависимые)
        return value.lower()
