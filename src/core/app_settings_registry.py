from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

SettingKind = Literal["bool", "int", "str"]


class UnknownSettingError(ValueError):
    """В patch попал ключ, которого нет в реестре."""


class InvalidSettingValueError(ValueError):
    """Значение не соответствует типу, объявленному в реестре."""


@dataclass(frozen=True, slots=True)
class SettingDefinition:
    """Описание одной глобальной настройки инстанса."""

    key: str
    kind: SettingKind
    default: bool | int | str | None
    title: str
    description: str
    # Публичные ключи попадают в /v1/settings/public, который читает в том числе
    # анонимный посетитель. Серверные параметры сюда выносить нельзя.
    public: bool = False


APP_SETTINGS: tuple[SettingDefinition, ...] = (
    SettingDefinition(
        key="new_year_decorations_enabled",
        kind="bool",
        # Выключено по умолчанию: отсутствие строки в таблице = выключено.
        default=False,
        title="Новогодние украшения",
        description="Снег, гирлянда и ёлочные шары на всех страницах сайта",
        public=True,
    ),
)

APP_SETTINGS_BY_KEY: dict[str, SettingDefinition] = {item.key: item for item in APP_SETTINGS}

PUBLIC_SETTING_KEYS: tuple[str, ...] = tuple(item.key for item in APP_SETTINGS if item.public)


def default_values() -> dict[str, Any]:
    """Значения всех настроек по умолчанию (основа для чтения без строк в БД)."""
    return {item.key: item.default for item in APP_SETTINGS}


def public_defaults() -> dict[str, Any]:
    """Дефолты только публичных ключей — форма ответа анонимного эндпоинта."""
    return {key: APP_SETTINGS_BY_KEY[key].default for key in PUBLIC_SETTING_KEYS}


def _coerce(definition: SettingDefinition, value: Any) -> bool | int | str | None:
    """Проверить тип значения по реестру.

    Проверка строгая и на isinstance, а не на приведение: `True` — это bool,
    а `1` и `"true"` — нет. Иначе `{"new_year_decorations_enabled": 1}` молча
    превратился бы во включённый декор у того, кто хотел передать что-то другое.
    """
    if value is None:
        if definition.default is None:
            return None
        raise InvalidSettingValueError(f"Setting '{definition.key}' does not accept null")

    match definition.kind:
        case "bool":
            # type(), а не isinstance: isinstance(True, int) — True, и такой
            # int молча прошёл бы проверку bool-настройки.
            if type(value) is not bool:
                raise InvalidSettingValueError(f"Setting '{definition.key}' expects a boolean")
            return value
        case "int":
            if type(value) is not int:
                raise InvalidSettingValueError(f"Setting '{definition.key}' expects an integer")
            return value
        case "str":
            if type(value) is not str:
                raise InvalidSettingValueError(f"Setting '{definition.key}' expects a string")
            return value

    raise InvalidSettingValueError(f"Setting '{definition.key}' has unsupported kind {definition.kind!r}")


def validate_patch(data: dict[str, Any]) -> dict[str, Any]:
    """Проверить частичное обновление по реестру и вернуть нормализованный patch.

    Raises:
        UnknownSettingError: ключ не зарегистрирован.
        InvalidSettingValueError: значение не соответствует типу ключа.
    """
    validated: dict[str, Any] = {}

    for key, value in data.items():
        definition = APP_SETTINGS_BY_KEY.get(key)
        if definition is None:
            raise UnknownSettingError(f"Unknown setting '{key}'")
        validated[key] = _coerce(definition, value)

    return validated
