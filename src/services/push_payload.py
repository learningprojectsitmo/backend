"""Сборка сообщения для FCM из типа уведомления и его данных.

Чистые функции без I/O: весь формат push проверяется юнит-тестами без БД,
без сети и без Firebase. Воркер (`src/services/push_worker.py`) получает на
вход уже готовый `payload` из outbox и ничего про типы уведомлений не знает.

О том, какие каналы срабатывают на какой тип, — `notification_policy`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from src.model.notification import NotificationType
from src.services.notification_policy import is_high_priority

#: Куда клиент уходит после тапа. Маршруты совпадают с деревом go_router
#: из плана мобильного приложения.
ROUTE_PROJECT: Final = "/app/projects/{project_id}"
ROUTE_NOTIFICATIONS: Final = "/app/notifications"

#: Лимит FCM на размер сообщения (data + notification). Обрезаем body, а не
#: отбрасываем push целиком: лучше короткий текст, чем никакого.
_MAX_BODY: Final = 180

#: Android-каналы. Клиент обязан завести их через
#: `createNotificationChannel` при старте, иначе Android уронит сообщение на
#: несуществующий channel. Идентификаторы — часть контракта с клиентом.
CHANNEL_RESPONSE: Final = "responses"
CHANNEL_INVITATION: Final = "invitations"
CHANNEL_STAGES: Final = "stages"
CHANNEL_KANBAN: Final = "kanban"

CHANNEL_TITLES: Final = {
    CHANNEL_RESPONSE: "Отклики на проекты",
    CHANNEL_INVITATION: "Приглашения в проекты",
    CHANNEL_STAGES: "Этапы проектов",
    CHANNEL_KANBAN: "Канбан",
}

#: Канал по типу уведомления.
CHANNEL_BY_TYPE: Final = {
    NotificationType.response_received: CHANNEL_RESPONSE,
    NotificationType.response_accepted: CHANNEL_RESPONSE,
    NotificationType.response_rejected: CHANNEL_RESPONSE,
    NotificationType.response_confirmed: CHANNEL_RESPONSE,
    NotificationType.invitation_received: CHANNEL_INVITATION,
    NotificationType.invitation_accepted: CHANNEL_INVITATION,
    NotificationType.invitation_rejected: CHANNEL_INVITATION,
    NotificationType.stage_approval_required: CHANNEL_STAGES,
    NotificationType.task_created: CHANNEL_KANBAN,
    NotificationType.task_updated: CHANNEL_KANBAN,
    NotificationType.task_moved: CHANNEL_KANBAN,
    NotificationType.task_deleted: CHANNEL_KANBAN,
    NotificationType.subtask_created: CHANNEL_KANBAN,
    NotificationType.subtask_updated: CHANNEL_KANBAN,
    NotificationType.subtask_deleted: CHANNEL_KANBAN,
}


@dataclass(frozen=True)
class PushPayload:
    """Подготовленное сообщение, независимое от конкретного устройства.

    Токена здесь нет намеренно: строка outbox одна на уведомление, а
    устройств у пользователя может быть несколько. Воркер подставляет токен
    в момент отправки, поэтому сообщение готовится один раз и переиспользуется
    для всех устройств — и для повторов после сбоя тоже.
    """

    title: str
    body: str
    route: str
    channel_id: str
    high_priority: bool
    collapse_key: str
    data: dict = field(default_factory=dict)

    def to_fcm_message(self, token: str) -> dict:
        """Собрать тело запроса FCM v1 (без обёртки `message`)."""
        data: dict[str, str] = {
            "route": self.route,
            "channel_id": self.channel_id,
            **{k: str(v) for k, v in self.data.items()},
        }
        message: dict = {
            "token": token,
            "notification": {"title": self.title, "body": self.body},
            # Только строковые значения: FCM отвергает message с нестроковым data,
            # а int из project_id в data просто не долетит.
            "data": data,
            "android": {
                "priority": "HIGH" if self.high_priority else "NORMAL",
                "notification": {
                    "channel_id": self.channel_id,
                    "click_action": "FLUTTER_NOTIFICATION_CLICK",
                },
            },
            "apns": {
                "headers": {
                    # APNs сам разрулит по channel_id из notification, но
                    # apns-priority нужен для доставки в фон, когда приложение
                    # свёрнуто.
                    "apns-priority": "10" if self.high_priority else "5",
                },
                "payload": {
                    "aps": {
                        "alert": {"title": self.title, "body": self.body},
                        # iOS 15+ смотрит на interruption_level, а не на
                        # apns-priority: с passive уведомление молча ложится в
                        # «шторку» без звука. Для task_moved это ровно то, что
                        # нужно — иначе перетаскивание задач в канбане гремит
                        # телефон на каждый чих.
                        "interruption_level": "active" if self.high_priority else "passive",
                        "sound": "default" if self.high_priority else None,
                        # На экране блокировки показываем заголовок и текст —
                        # здесь нет ничего, что не должен видеть владелец
                        # телефона, поэтому private вместо secret.
                        "thread-id": self.channel_id,
                    }
                },
            },
        }
        if self.collapse_key:
            message["android"]["collapse_key"] = self.collapse_key
            message["apns"]["headers"]["apns-collapse-id"] = self.collapse_key
        if message["apns"]["payload"]["aps"]["sound"] is None:
            del message["apns"]["payload"]["aps"]["sound"]
        return {"message": message}


def _clip(text: str, limit: int = _MAX_BODY) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _actor(data: dict) -> str:
    """Имя актора. В данных оно под ключом actor_name, но у части вызовов
    (канбан) оно тоже есть, а вот у календарных событий может отсутствовать."""
    return str(data.get("actor_name") or "Кто-то")


def _project(data: dict) -> str:
    return str(data.get("project_name") or "проект")


def build_push(
    *,
    type: NotificationType,
    data: dict,
    user_id: int,
    notification_id: int | None = None,
) -> PushPayload:
    """Собрать push для пользователя, без привязки к устройству.

    `user_id` нужен для collapse_key: серия однотипных событий у одного
    человека схлопывается в одно уведомление, у соседа по проекту — нет.
    """
    project_id = data.get("project_id")
    route = ROUTE_PROJECT.format(project_id=project_id) if project_id else ROUTE_NOTIFICATIONS

    title, body = _describe(type, data)
    high = is_high_priority(type)
    # Серия однотипных событий у одного пользователя схлопывается в одно
    # уведомление: иначе десять task_moved подряд превращаются в десять
    # баннеров. Ключ общий на тип, а не на задачу — иначе схлопывание не
    # работает вовсе.
    collapse_key = f"{user_id}:{type.value}"

    extra: dict = {"type": type.value}
    if notification_id is not None:
        extra["notification_id"] = notification_id
    if project_id is not None:
        extra["project_id"] = project_id
    if data.get("task_title"):
        extra["task_title"] = data["task_title"]
    if data.get("subtask_title"):
        extra["subtask_title"] = data["subtask_title"]
    if data.get("stage_name"):
        extra["stage_name"] = data["stage_name"]
    if data.get("vacancy_title"):
        extra["vacancy_title"] = data["vacancy_title"]

    return PushPayload(
        title=title,
        body=_clip(body),
        route=route,
        channel_id=CHANNEL_BY_TYPE[type],
        high_priority=high,
        collapse_key=collapse_key,
        data=extra,
    )


def _describe(type: NotificationType, data: dict) -> tuple[str, str]:
    """(заголовок, текст) под каждый тип уведомления."""
    actor = _actor(data)
    project = _project(data)

    match type:
        case NotificationType.response_received:
            return "Новый отклик", f"{actor} откликнулся на проект «{project}»"
        case NotificationType.response_accepted:
            return "Отклик принят", f"Вас приняли в проект «{project}»"
        case NotificationType.response_rejected:
            return "Отклик отклонён", f"Отклик в проект «{project}» отклонён"
        case NotificationType.response_confirmed:
            return "Участие подтверждено", f"Вы подтвердили участие в проекте «{project}»"
        case NotificationType.invitation_received:
            vacancy = data.get("vacancy_title")
            role = f" на роль «{vacancy}»" if vacancy else ""
            return "Приглашение в проект", f"{actor} пригласил вас{role} в «{project}»"
        case NotificationType.invitation_accepted:
            return "Приглашение принято", f"{actor} принял приглашение в «{project}»"
        case NotificationType.invitation_rejected:
            return "Приглашение отклонено", f"{actor} отклонил приглашение в «{project}»"
        case NotificationType.stage_approval_required:
            stage = data.get("stage_name")
            what = f" этап «{stage}»" if stage else " этап"
            return "Нужно утверждение", f"{actor} ждёт вашего решения по{what} в «{project}»"
        case (
            NotificationType.task_created
            | NotificationType.task_updated
            | NotificationType.task_moved
            | NotificationType.task_deleted
            | NotificationType.subtask_created
            | NotificationType.subtask_updated
            | NotificationType.subtask_deleted
        ):
            return _describe_kanban(type, data, actor)
    raise ValueError(f"Нет шаблона push для типа уведомления {type!r}")


def _describe_kanban(type: NotificationType, data: dict, actor: str) -> tuple[str, str]:
    """Задачи и подзадачи: их движение — это шум, а не событие."""
    match type:
        case NotificationType.task_created:
            task = data.get("task_title") or "задача"
            column = data.get("column_name")
            where = f" в «{column}»" if column else ""
            return "Новая задача", f"{actor} создал задачу «{task}»{where}"
        case NotificationType.task_updated:
            task = data.get("task_title") or "задача"
            return "Задача изменена", f"{actor} изменил задачу «{task}»"
        case NotificationType.task_moved:
            task = data.get("task_title") or "задача"
            column = data.get("column_name")
            where = f" в «{column}»" if column else ""
            return "Задача перемещена", f"«{task}» →{where}"
        case NotificationType.task_deleted:
            task = data.get("task_title") or "задача"
            return "Задача удалена", f"{actor} удалил задачу «{task}»"
        case NotificationType.subtask_created:
            sub = data.get("subtask_title") or "подзадача"
            task = data.get("task_title")
            where = f" к задаче «{task}»" if task else ""
            return "Новая подзадача", f"{actor} добавил «{sub}»{where}"
        case NotificationType.subtask_updated:
            sub = data.get("subtask_title") or "подзадача"
            return "Подзадача изменена", f"{actor} изменил «{sub}»"
        case NotificationType.subtask_deleted:
            sub = data.get("subtask_title") or "подзадача"
            return "Подзадача удалена", f"{actor} удалил «{sub}»"
    raise ValueError(f"Нет шаблона push для типа уведомления {type!r}")
