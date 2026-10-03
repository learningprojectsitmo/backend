from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from src.core.app_settings_registry import (
    APP_SETTINGS,
    APP_SETTINGS_BY_KEY,
    InvalidSettingValueError,
    UnknownSettingError,
    default_values,
    validate_patch,
)
from src.model.app_setting import AppSetting
from src.repository.app_setting_repository import AppSettingRepository
from src.services.app_setting_service import AppSettingService

DECORATIONS_KEY = "new_year_decorations_enabled"


def make_repository(rows: list[AppSetting] | None = None) -> Mock:
    """Репозиторий, отдающий заранее заданные строки по любому набору ключей."""
    repository = Mock(spec=AppSettingRepository)
    repository.create = AsyncMock(side_effect=lambda data: AppSetting(id=1, **data))

    async def get_by_keys(keys):
        wanted = set(keys)
        return [row for row in (rows or []) if row.key in wanted]

    repository.get_by_keys = AsyncMock(side_effect=get_by_keys)
    return repository


class TestAppSettingRegistry:
    def test_should_default_decorations_to_disabled(self):
        """Ключевая гарантия: без единой строки в таблице декор выключен"""
        # given / when
        defaults = default_values()

        # then
        assert defaults[DECORATIONS_KEY] is False

    def test_should_register_every_key_as_public_and_bool(self):
        """Все настройки реестра — булевы и публичные (иначе фронт их не увидит)"""
        # given / when / then
        assert {item.key for item in APP_SETTINGS} == set(APP_SETTINGS_BY_KEY)
        for item in APP_SETTINGS:
            assert item.kind == "bool"
            assert item.public is True

    def test_should_reject_unknown_key(self):
        """Неизвестный ключ не проходит валидацию"""
        # given / when / then
        with pytest.raises(UnknownSettingError):
            validate_patch({"no_such_setting": True})

    @pytest.mark.parametrize("value", [1, 0, "true", "yes", [], {}])
    def test_should_reject_non_boolean_value(self, value):
        """Нестрогая проверка bool пропустила бы 1 как True — проверяем строгую"""
        # given / when / then
        with pytest.raises(InvalidSettingValueError):
            validate_patch({DECORATIONS_KEY: value})

    def test_should_accept_real_boolean(self):
        """Настоящий bool любого значения принимается"""
        # given / when / then
        assert validate_patch({DECORATIONS_KEY: False}) == {DECORATIONS_KEY: False}
        assert validate_patch({DECORATIONS_KEY: True}) == {DECORATIONS_KEY: True}


class TestAppSettingServiceReads:
    @pytest.mark.asyncio
    async def test_should_return_registry_defaults_when_table_is_empty(self):
        """Пустая таблица = дефолты реестра, а не 404 и не пустой dict"""
        # given
        service = AppSettingService(make_repository([]))

        # when
        values = await service.get_values()

        # then
        assert values == default_values()
        assert values[DECORATIONS_KEY] is False

    @pytest.mark.asyncio
    async def test_should_override_default_with_stored_row(self):
        """Строка из БД перекрывает дефолт реестра"""
        # given
        rows = [AppSetting(id=1, key=DECORATIONS_KEY, value=True, updated_by_id=7)]
        service = AppSettingService(make_repository(rows))

        # when
        values = await service.get_values()

        # then
        assert values[DECORATIONS_KEY] is True

    @pytest.mark.asyncio
    async def test_should_ignore_row_left_behind_by_removed_setting(self):
        """Строка от настройки, удалённой из реестра, наружу не отдаётся"""
        # given
        rows = [AppSetting(id=1, key="legacy_flag", value=True)]
        service = AppSettingService(make_repository(rows))

        # when
        values = await service.get_values()

        # then
        assert "legacy_flag" not in values
        assert values == default_values()

    @pytest.mark.asyncio
    async def test_should_return_only_public_values(self):
        """Анонимный эндпоинт получает лишь публичные ключи"""
        # given
        service = AppSettingService(make_repository([AppSetting(id=1, key="legacy_flag", value=True)]))

        # when
        values = await service.get_public_values()

        # then
        assert values == {DECORATIONS_KEY: False}

    @pytest.mark.asyncio
    async def test_should_report_settings_not_touched_yet(self):
        """Для настройки без строки updated_by_id пуст — «ещё не менялась»"""
        # given
        service = AppSettingService(make_repository([]))

        # when
        items = await service.list_items()

        # then
        assert len(items) == len(APP_SETTINGS)
        item = next(current for current in items if current.key == DECORATIONS_KEY)
        assert item.value is False
        assert item.kind == "bool"
        assert item.updated_at is None
        assert item.updated_by_id is None


class TestAppSettingServiceUpdates:
    @pytest.mark.asyncio
    async def test_should_create_row_on_first_toggle(self):
        """Первый переключатель создаёт строку: до этого жил только дефолт"""
        # given
        repository = make_repository([])
        service = AppSettingService(repository)

        # when
        await service.apply_patch({DECORATIONS_KEY: True}, user_id=42)

        # then
        repository.create.assert_awaited_once_with({"key": DECORATIONS_KEY, "value": True, "updated_by_id": 42})

    @pytest.mark.asyncio
    async def test_should_update_existing_row_in_place(self):
        """Повторный переключатель обновляет строку, а не плодит новые"""
        # given
        row = AppSetting(id=1, key=DECORATIONS_KEY, value=False, updated_by_id=1)
        repository = make_repository([row])
        service = AppSettingService(repository)

        # when
        await service.apply_patch({DECORATIONS_KEY: True}, user_id=42)

        # then
        repository.create.assert_not_awaited()
        assert row.value is True
        assert row.updated_by_id == 42

    @pytest.mark.asyncio
    async def test_should_reject_invalid_patch_without_touching_table(self):
        """Невалидный patch отклоняется до записи в БД"""
        # given
        repository = make_repository([])
        service = AppSettingService(repository)

        # when / then
        with pytest.raises(InvalidSettingValueError):
            await service.apply_patch({DECORATIONS_KEY: "true"}, user_id=42)

        repository.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_touch_nothing_on_empty_patch(self):
        """Пустой patch — не ошибка, но и не запись"""
        # given
        repository = make_repository([])
        service = AppSettingService(repository)

        # when
        await service.apply_patch({}, user_id=42)

        # then
        repository.create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_return_updated_item_after_toggle(self):
        """Ответ содержит новое значение — админ-панель сразу перерисует тумблер"""
        # given
        row = AppSetting(id=1, key=DECORATIONS_KEY, value=False)
        service = AppSettingService(make_repository([row]))

        # when
        items = await service.apply_patch({DECORATIONS_KEY: True}, user_id=42)

        # then
        item = next(current for current in items if current.key == DECORATIONS_KEY)
        assert item.value is True

    @pytest.mark.asyncio
    async def test_should_keep_created_row_timestamped(self):
        """У созданной строки заполнены audit-поля модели (updated_at — на уровне БД)"""
        # given
        repository = make_repository([])
        service = AppSettingService(repository)

        # when
        await service.apply_patch({DECORATIONS_KEY: True}, user_id=42)

        # then
        created = repository.create.await_args.args[0]
        assert set(created) == {"key", "value", "updated_by_id"}
