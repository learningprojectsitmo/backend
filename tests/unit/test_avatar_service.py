from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.repository.avatar_repository import AvatarRepository
from src.services.avatar_service import (
    MAX_AVATAR_BYTES,
    AvatarError,
    AvatarService,
    AvatarTooLargeError,
    AvatarUnsupportedTypeError,
    build_avatar_url,
)

_DT = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
_EXPECTED_TS = int(_DT.timestamp() * 1_000_000)

WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBP" + b"payload"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"payload"
JPEG_BYTES = b"\xff\xd8\xff" + b"payload"


def _make_service(updated_at: datetime = _DT) -> tuple[AvatarService, Mock]:
    repository = Mock(spec=AvatarRepository)
    repository.upsert = AsyncMock(return_value=updated_at)
    repository.delete = AsyncMock(return_value=True)
    repository.get_image = AsyncMock(return_value=None)
    repository.get_meta = AsyncMock(return_value=None)
    repository.get_updated_at_map = AsyncMock(return_value={})
    return AvatarService(repository), repository


class TestBuildAvatarUrl:
    def test_should_include_cache_busting_version(self):
        # given / when
        url = build_avatar_url(5, _DT)

        # then
        assert url == f"/media/5/avatar?v={_EXPECTED_TS}"

    def test_should_treat_naive_datetime_as_utc(self):
        # given
        naive = datetime(2026, 10, 31, 12, 0)  # намеренно без tzinfo

        # when
        url = build_avatar_url(7, naive)

        # then
        assert url.endswith(f"?v={_EXPECTED_TS}")

    def test_should_change_version_on_reupload_within_same_second(self):
        # given: две загрузки в одну секунду (now() в Postgres — микросекунды)
        first = _DT
        second = _DT.replace(microsecond=1)

        # when
        first_url = build_avatar_url(3, first)
        second_url = build_avatar_url(3, second)

        # then: URL с max-age=86400 обязан отличаться, иначе браузер покажет
        # закэшированную старую картинку
        assert first_url != second_url


class TestAvatarUpload:
    @pytest.mark.asyncio
    async def test_should_store_webp_and_return_url(self):
        # given
        service, repository = _make_service()

        # when
        url = await service.upload(5, "image/webp", WEBP_BYTES)

        # then
        repository.upsert.assert_awaited_once_with(5, "image/webp", WEBP_BYTES)
        assert url == f"/media/5/avatar?v={_EXPECTED_TS}"

    @pytest.mark.asyncio
    async def test_should_strip_content_type_parameters(self):
        # given
        service, repository = _make_service()

        # when
        await service.upload(5, "image/png; charset=binary", PNG_BYTES)

        # then
        repository.upsert.assert_awaited_once_with(5, "image/png", PNG_BYTES)

    @pytest.mark.asyncio
    async def test_should_accept_jpeg(self):
        # given
        service, repository = _make_service()

        # when
        await service.upload(5, "image/jpeg", JPEG_BYTES)

        # then
        repository.upsert.assert_awaited_once_with(5, "image/jpeg", JPEG_BYTES)

    @pytest.mark.asyncio
    async def test_should_reject_empty_file(self):
        # given
        service, repository = _make_service()

        # when / then
        with pytest.raises(AvatarError):
            await service.upload(5, "image/webp", b"")
        repository.upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_reject_svg(self):
        # given
        service, repository = _make_service()

        # when / then
        with pytest.raises(AvatarUnsupportedTypeError):
            await service.upload(5, "image/svg+xml", b"<svg></svg>")
        repository.upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_reject_content_type_mismatching_signature(self):
        # given: заявлен PNG, внутри JPEG
        service, repository = _make_service()

        # when / then
        with pytest.raises(AvatarUnsupportedTypeError):
            await service.upload(5, "image/png", JPEG_BYTES)
        repository.upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_reject_file_over_limit(self):
        # given
        service, repository = _make_service()
        oversized = WEBP_BYTES + b"\x00" * MAX_AVATAR_BYTES

        # when / then
        with pytest.raises(AvatarTooLargeError):
            await service.upload(5, "image/webp", oversized)
        repository.upsert.assert_not_awaited()


class TestAvatarReadAndDelete:
    @pytest.mark.asyncio
    async def test_should_delete_avatar(self):
        # given
        service, repository = _make_service()

        # when
        deleted = await service.delete(5)

        # then
        assert deleted is True
        repository.delete.assert_awaited_once_with(5)

    @pytest.mark.asyncio
    async def test_should_return_image_tuple(self):
        # given
        service, repository = _make_service()
        repository.get_image = AsyncMock(return_value=Mock(data=WEBP_BYTES, content_type="image/webp", updated_at=_DT))

        # when
        image = await service.get_image(5)

        # then
        assert image == (WEBP_BYTES, "image/webp", _DT)

    @pytest.mark.asyncio
    async def test_should_return_none_when_avatar_missing(self):
        # given
        service, _ = _make_service()

        # when
        image = await service.get_image(5)

        # then
        assert image is None

    @pytest.mark.asyncio
    async def test_should_build_urls_for_many_users(self):
        # given
        service, repository = _make_service()
        repository.get_updated_at_map = AsyncMock(return_value={3: _DT})

        # when
        urls = await service.get_avatar_urls([3, 4])

        # then
        assert urls == {3: f"/media/3/avatar?v={_EXPECTED_TS}"}
