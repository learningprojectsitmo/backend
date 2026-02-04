import re


def validate_telegram_username(username: str | None) -> str | None:
    """Валидация Telegram username"""
    MIN_USERNAME_LENGTH = 6
    MAX_USERNAME_LENGTH = 33
    if username is None or username.strip() == "":
        return None

    username = username.strip()

    if not username.startswith('@'):
        raise ValueError("Telegram username должен начинаться с @")

    if len(username) < MIN_USERNAME_LENGTH or len(username) > MAX_USERNAME_LENGTH:  # @ + 5-32 символов
        raise ValueError("Telegram username должен содержать от 5 до 32 символов после @")

    # Проверка символов
    username_part = username[1:]  # Без @
    if not re.match(r'^\w{5,32}$', username_part):
        raise ValueError("Telegram username может содержать только буквы, цифры и подчеркивания")

    return username