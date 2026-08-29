from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from src.repository.audit_repository import AuditRepository
from src.schema.audit import ActivityDay, ActivityItem, ActivityResponse, AuditLogResponse

ACTIVITY_DAYS_WINDOW = 365
ACTIVITY_ITEMS_LIMIT = 50
VALUE_MAX_LENGTH = 40

# Человекочитаемые имена полей для diff в ленте действий
FIELD_LABELS = {
    "name": "Название",
    "title": "Название",
    "description": "Описание",
    "theme": "Тема",
    "status_id": "Статус",
    "status": "Статус",
    "progress": "Прогресс",
    "deadline": "Дедлайн",
    "max_participants": "Максимум участников",
    "is_visible": "Видимость",
    "header": "Заголовок",
    "type": "Тип",
    "first_name": "Имя",
    "last_name": "Фамилия",
    "email": "Почта",
    "phone": "Телефон",
}

# Служебные поля, которые не показываем в diff
IGNORED_COLUMNS = {"id", "created_at", "updated_at"}


class AuditService:
    """Сервис для работы с audit логами"""

    def __init__(self, audit_repository: AuditRepository):
        self._audit_repository = audit_repository

    async def get_user_audit_logs(self, user_id: int) -> list[AuditLogResponse]:
        """Получить audit логи пользователя"""

        logs = await self._audit_repository.get_logs_by_user_id(user_id)
        result = []
        for log in logs:
            log_dict = {
                "id": log.id,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "action": log.action,
                "old_values": json.loads(log.old_values) if isinstance(log.old_values, str) else log.old_values,
                "new_values": json.loads(log.new_values) if isinstance(log.new_values, str) else log.new_values,
                "performed_by": log.performed_by,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "performed_at": log.performed_at,
            }
            result.append(AuditLogResponse(**log_dict))

        return result

    async def get_activity(self, user_id: int, limit: int = ACTIVITY_ITEMS_LIMIT) -> ActivityResponse:
        """Активность пользователя за последние 365 дней: агрегат по дням + лента действий"""

        logs = await self._audit_repository.get_logs_by_user_id(user_id)
        since = datetime.now(UTC) - timedelta(days=ACTIVITY_DAYS_WINDOW)
        relevant = [log for log in logs if log.performed_at and log.performed_at >= since]

        project_names, resume_names = await self._resolve_names(relevant)

        day_counts: dict[date, int] = {}
        for log in relevant:
            day = log.performed_at.date()  # type: ignore[union-attr]
            day_counts[day] = day_counts.get(day, 0) + 1
        summary = [ActivityDay(date=day, count=count) for day, count in sorted(day_counts.items())]

        items = [
            ActivityItem(
                id=log.id,
                kind=f"{log.entity_type}:{log.action}",
                description=self._describe(log, project_names, resume_names),
                performed_at=log.performed_at,
            )
            for log in relevant[:limit]
        ]
        return ActivityResponse(total=len(relevant), summary=summary, items=items)

    async def _resolve_names(self, logs: list) -> tuple[dict[int, str], dict[int, str]]:
        """Собрать названия проектов и резюме, которые упоминаются в логах"""

        project_ids: set[int] = set()
        resume_ids: set[int] = set()

        for log in logs:
            new_values = self._parse_values(log.new_values) or {}
            old_values = self._parse_values(log.old_values) or {}

            if log.entity_type == "project":
                project_ids.add(log.entity_id)
            elif log.entity_type == "resume":
                resume_ids.add(log.entity_id)
            elif log.entity_type == "response":
                project_id = new_values.get("project_id") or old_values.get("project_id")
                if project_id:
                    project_ids.add(int(project_id))

        project_names = await self._audit_repository.get_project_names(project_ids)
        resume_names = await self._audit_repository.get_resume_names(resume_ids)
        return project_names, resume_names

    @staticmethod
    def _parse_values(values: dict | str | None) -> dict | None:
        """Распарсить old/new values (могут храниться как JSON-строка или dict)"""

        if values is None:
            return None
        if isinstance(values, str):
            return json.loads(values)
        return values

    def _describe(
        self,
        log,
        project_names: dict[int, str],
        resume_names: dict[int, str],
    ) -> str:
        """Сформировать человекочитаемое описание действия"""

        new_values = self._parse_values(log.new_values) or {}
        old_values = self._parse_values(log.old_values) or {}
        action = log.action

        if log.entity_type == "project":
            name = (
                new_values.get("name")
                or old_values.get("name")
                or project_names.get(log.entity_id)
                or f"проект #{log.entity_id}"
            )
            if action == "INSERT":
                return f"Создал проект «{name}»"
            if action == "DELETE":
                return f"Удалил проект «{name}»"
            return self._with_diff(f"Обновил проект «{name}»", self._diff_fields(old_values, new_values))

        if log.entity_type == "resume":
            header = (
                new_values.get("header") or old_values.get("header") or resume_names.get(log.entity_id)
            )
            label = f"«{header}»" if header else f"резюме #{log.entity_id}"
            if action == "INSERT":
                return f"Создал резюме {label}"
            if action == "DELETE":
                return f"Удалил резюме {label}"
            return self._with_diff(f"Обновил резюме {label}", self._diff_fields(old_values, new_values))

        if log.entity_type == "response":
            return self._describe_response(log, project_names)

        if log.entity_type == "user":
            if action == "INSERT":
                return "Зарегистрировался в системе"
            if action == "DELETE":
                return "Удалил аккаунт"
            return self._with_diff("Обновил профиль", self._diff_fields(old_values, new_values))

        return f"Выполнил действие {log.entity_type}:{action}"

    def _describe_response(self, log, project_names: dict[int, str]) -> str:
        """Описание действия с сущностью response (отклик/приглашение)"""

        new_values = self._parse_values(log.new_values) or {}
        old_values = self._parse_values(log.old_values) or {}
        action = log.action

        values = new_values or old_values
        project_id = values.get("project_id")
        project_name = project_names.get(int(project_id)) if project_id else None
        context = f"проект «{project_name}»" if project_name else "проект"
        resp_type = values.get("type") or "response"

        if action == "INSERT":
            if resp_type == "invitation":
                return f"Пригласил в {context}"
            return f"Откликнулся на {context}"
        if action == "DELETE":
            return f"Удалил отклик в {context}"

        status = new_values.get("status")
        noun = "приглашение" if resp_type == "invitation" else "отклик"
        if status == "accepted":
            base = f"Принял {noun} в {context}"
        elif status == "rejected":
            base = f"Отклонил {noun} в {context}"
        elif status == "withdrawn":
            base = f"Отозвал отклик в {context}"
        else:
            base = f"Обновил отклик в {context}"
        return self._with_diff(base, self._diff_fields(old_values, new_values))

    def _diff_fields(self, old_values: dict | None, new_values: dict | None, limit: int = 3) -> list[str]:
        """Разница old → new для изменённых полей (до limit штук)"""

        old = old_values or {}
        new = new_values or {}
        changes: list[tuple[str, object | None, object | None]] = []

        for field, old_val in old.items():
            if field in IGNORED_COLUMNS:
                continue
            new_val = new.get(field)
            if old_val is None and new_val is None:
                continue
            if old_val == new_val:
                continue
            changes.append((field, old_val, new_val))

        if not changes:
            return []

        parts = []
        for field, old_val, new_val in changes[:limit]:
            label = FIELD_LABELS.get(field, field)
            parts.append(f"{label}: {self._format_value(old_val)} → {self._format_value(new_val)}")

        if len(changes) > limit:
            parts.append(f"и ещё {len(changes) - limit}")
        return parts

    @staticmethod
    def _with_diff(base: str, diff: list[str]) -> str:
        """Добавить diff к описанию действия, если он есть"""

        if not diff:
            return base
        return f"{base}: {', '.join(diff)}"

    @staticmethod
    def _format_value(value: object | None) -> str:
        """Отформатировать значение для отображения в ленте"""

        if value is None:
            return "—"
        if isinstance(value, bool):
            return "да" if value else "нет"
        if isinstance(value, (list, dict)):
            return f"[{len(value)}]"
        if isinstance(value, (int, float)):
            return str(value)
        text = str(value)
        if len(text) > VALUE_MAX_LENGTH:
            text = f"{text[:VALUE_MAX_LENGTH - 3]}…"
        return f"«{text}»"
