"""Юнит-тесты сборки FCM-payload: чистые функции, без БД и сети."""

from __future__ import annotations

import pytest

from src.model.notification import NotificationType
from src.services.notification_policy import EMAIL_TYPES, needs_email
from src.services.push_payload import (
    CHANNEL_BY_TYPE,
    CHANNEL_INVITATION,
    CHANNEL_KANBAN,
    CHANNEL_RESPONSE,
    CHANNEL_STAGES,
    PushPayload,
    build_push,
)

_TOKEN = "tok"


def _push(type: NotificationType, data: dict | None = None, user_id: int = 7) -> PushPayload:
    # data заменяет базовый набор, а не дополняет его: иначе нельзя проверить
    # поведение при отсутствующем project_id — он всегда доезжает из base.
    base = {"project_id": 3, "actor_name": "Анна"}
    return build_push(
        type=type,
        data=base if data is None else data,
        user_id=user_id,
        notification_id=42,
    )


class TestNeedsEmail:
    def test_should_keep_email_for_important_types(self):
        # given / when / then
        assert needs_email(NotificationType.response_received) is True
        assert needs_email(NotificationType.invitation_received) is True
        assert needs_email(NotificationType.stage_approval_required) is True

    def test_should_not_send_email_for_kanban_noise(self):
        # given / when / then
        assert needs_email(NotificationType.task_created) is False
        assert needs_email(NotificationType.task_moved) is False
        assert needs_email(NotificationType.subtask_updated) is False

    def test_should_cover_every_notification_type(self):
        # given
        all_types = set(NotificationType)

        # when
        mapped = set(EMAIL_TYPES) | set(CHANNEL_BY_TYPE)

        # then — новый тип уведомления нельзя забыть покрыть
        assert mapped == all_types


class TestBuildPush:
    def test_should_describe_every_type(self):
        # given
        types = list(NotificationType)

        # when
        messages = [_push(t, {"task_title": "T", "subtask_title": "S"}) for t in types]

        # then — ни один тип не падает и даёт непустой текст
        assert len(messages) == len(types)
        for message in messages:
            assert message.title and message.body

    def test_should_route_project_events_into_project(self):
        # given
        data = {"project_id": 12, "actor_name": "Анна"}

        # when
        message = _push(NotificationType.response_received, data)

        # then
        assert message.route == "/app/projects/12"

    def test_should_route_without_project_to_notifications(self):
        # given
        data = {"actor_name": "Анна"}

        # when
        message = _push(NotificationType.response_received, data)

        # then
        assert message.route == "/app/notifications"

    def test_should_mark_important_types_high_priority(self):
        # given / when / then
        assert _push(NotificationType.stage_approval_required).high_priority is True

    def test_should_mark_kanban_types_low_priority(self):
        # given / when
        message = _push(NotificationType.task_moved, {"task_title": "Дизайн"})

        # then
        assert message.high_priority is False
        assert message.channel_id == CHANNEL_KANBAN

    def test_should_assign_expected_channels(self):
        # given / when / then
        assert _push(NotificationType.response_received).channel_id == CHANNEL_RESPONSE
        assert _push(NotificationType.stage_approval_required).channel_id == CHANNEL_STAGES

    def test_should_clip_long_body(self):
        # given
        data = {"actor_name": "А" * 400, "project_name": "P"}

        # when
        message = _push(NotificationType.response_received, data)

        # then
        assert len(message.body) <= 180
        assert message.body.endswith("…")

    def test_should_collapse_by_type_not_by_task(self):
        # given
        first = _push(NotificationType.task_moved, {"task_title": "A"})
        second = _push(NotificationType.task_moved, {"task_title": "B"})

        # then — серия однотипных событий схлопывается в одно уведомление
        assert first.collapse_key == second.collapse_key

    def test_should_scope_collapse_key_by_user(self):
        # given
        mine = _push(NotificationType.task_moved, {"task_title": "A"}, user_id=1)
        theirs = _push(NotificationType.task_moved, {"task_title": "A"}, user_id=2)

        # then
        assert mine.collapse_key != theirs.collapse_key

    def test_should_survive_missing_optional_fields(self):
        # given
        data = {"project_id": 1}

        # when
        message = _push(NotificationType.subtask_created, data)

        # then — подзадача без task_title не должна ронять сборку
        assert message.title == "Новая подзадача"
        assert message.body


class TestFcmMessage:
    def test_should_stringify_data_values(self):
        # given — FCM отвергает нестроковый data
        message = _push(NotificationType.response_received, {"project_id": 5})

        # when
        sent = message.to_fcm_message(_TOKEN)

        # then
        data = sent["message"]["data"]
        assert all(isinstance(v, str) for v in data.values())
        assert data["project_id"] == "5"
        assert data["type"] == NotificationType.response_received.value

    def test_should_carry_route_for_deep_link(self):
        # given / when
        sent = _push(NotificationType.response_received).to_fcm_message(_TOKEN)

        # then
        assert sent["message"]["data"]["route"] == "/app/projects/3"

    def test_should_set_android_priority_and_channel(self):
        # given / when
        sent = _push(NotificationType.invitation_received).to_fcm_message(_TOKEN)

        # then
        android = sent["message"]["android"]
        assert android["priority"] == "HIGH"
        assert android["notification"]["channel_id"] == CHANNEL_INVITATION
        assert android["notification"]["click_action"] == "FLUTTER_NOTIFICATION_CLICK"
        assert android["collapse_key"] == sent["message"]["apns"]["headers"]["apns-collapse-id"]

    def test_should_use_passive_interruption_for_low_priority(self):
        # given — иначе task_moved гремит телефон на каждое перемещение
        sent = _push(NotificationType.task_moved, {"task_title": "A"}).to_fcm_message(_TOKEN)

        # then
        aps = sent["message"]["apns"]["payload"]["aps"]
        assert aps["interruption_level"] == "passive"
        assert "sound" not in aps

    def test_should_sound_for_high_priority(self):
        # given / when
        sent = _push(NotificationType.response_received).to_fcm_message(_TOKEN)

        # then
        aps = sent["message"]["apns"]["payload"]["aps"]
        assert aps["interruption_level"] == "active"
        assert aps["sound"] == "default"

    def test_should_place_token_and_text(self):
        # given / when
        sent = _push(NotificationType.response_received).to_fcm_message(_TOKEN)

        # then
        assert sent["message"]["token"] == "tok"
        assert sent["message"]["notification"]["title"] == "Новый отклик"


class TestEmptyCollapseKey:
    def test_should_omit_headers_when_no_collapse_key(self):
        # given — пустой ключ не должен отправляться мусором в заголовках
        payload = PushPayload(
            title="x",
            body="y",
            route="/app",
            channel_id=CHANNEL_KANBAN,
            high_priority=False,
            collapse_key="",
        )

        # when
        message = payload.to_fcm_message(_TOKEN)["message"]

        # then
        assert "collapse_key" not in message["android"]
        assert "apns-collapse-id" not in message["apns"]["headers"]

    @pytest.mark.parametrize("missing", ["actor_name", "project_name"])
    def test_should_fallback_on_missing_names(self, missing: str):
        # given
        data = {"project_id": 1, "actor_name": "Анна", "project_name": "P"}
        del data[missing]

        # when
        message = _push(NotificationType.response_received, data)

        # then
        assert message.title and message.body
