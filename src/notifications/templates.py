from __future__ import annotations

from typing import Any

NOTIFICATION_TEMPLATES: dict[str, dict[str, Any]] = {
    "project_invitation": {
        "title": "Приглашение в проект",
        "body": "Вас пригласили в проект «{project_name}».",
        "required": ["project_name"],
    },
    "project_removal": {
        "title": "Удаление из проекта",
        "body": "Вы были удалены из проекта «{project_name}».",
        "required": ["project_name"],
    },
    "join_request": {
        "title": "Запрос на вступление",
        "body": "Пользователь {requester_name} хочет вступить в проект «{project_name}».",
        "required": ["requester_name", "project_name"],
    },
    "join_request_approved": {
        "title": "Запрос одобрен",
        "body": "Ваш запрос на вступление в проект «{project_name}» одобрен.",
        "required": ["project_name"],
    },
    "join_request_rejected": {
        "title": "Запрос отклонен",
        "body": "Ваш запрос на вступление в проект «{project_name}» отклонен.",
        "required": ["project_name"],
    },
    "project_announcement": {
        "title": "Объявление проекта",
        "body": "Новое объявление в проекте «{project_name}»: {message}",
        "required": ["project_name", "message"],
    },
    "system_alert": {
        "title": "Системное уведомление",
        "body": "{message}",
        "required": ["message"],
    },
}


def list_notification_templates() -> dict[str, dict[str, Any]]:
    return NOTIFICATION_TEMPLATES


def list_notification_required_fields() -> dict[str, dict[str, Any]]:
    return {key: {"required": value["required"]} for key, value in NOTIFICATION_TEMPLATES.items()}


def build_notification_examples(
    include_project_id: bool,
    include_author: bool,
) -> dict[str, dict[str, Any]]:
    examples: dict[str, dict[str, Any]] = {}

    for key, template in NOTIFICATION_TEMPLATES.items():
        payload = _build_payload_example(template.get("required", []))
        example_value: dict[str, Any] = {
            "template_key": key,
            "payload": payload,
        }

        if include_project_id and "project_name" in template.get("required", []):
            example_value["project_id"] = 42

        if include_author:
            example_value["include_author"] = True

        examples[key] = {
            "summary": template.get("title", key),
            "value": example_value,
        }

    return examples


def _build_payload_example(required_fields: list[str]) -> dict[str, Any]:
    sample_values = {
        "project_name": "Alpha",
        "requester_name": "Alex",
        "message": "Standup at 10:00",
    }
    return {field: sample_values.get(field, "value") for field in required_fields}
