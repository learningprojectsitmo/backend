from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from src.core.audit_context import get_audit_context
from src.repository.audit_repository import AuditRepository
from src.schema.audit import ActivityActor, ActivityDay, ActivityItem, ActivityResponse, AuditLogResponse

if TYPE_CHECKING:
    from src.model.kanban_models import Task

ACTIVITY_DAYS_WINDOW = 365
ACTIVITY_ITEMS_LIMIT = 50
VALUE_MAX_LENGTH = 40
TEXT_PREVIEW_LENGTH = 60
DIFF_FIELDS_LIMIT = 3

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
    "middle_name": "Отчество",
    "email": "Почта",
    "phone": "Телефон",
    "priority": "Приоритет",
    "due_date": "Срок",
    "tags": "Метки",
    "wip_limit": "Лимит WIP",
    "is_completed": "Выполнено",
    "goal": "Цель",
    "column_id": "Колонка",
    "kind": "Вид",
    "action": "Действие",
    "comment": "Комментарий",
    "rejection_comment": "Комментарий",
    "text": "Текст",
    "functional_requirements": "Функциональные требования",
    "non_functional_requirements": "Нефункциональные требования",
}

# Служебные поля, которые не показываем в diff
IGNORED_COLUMNS = {"id", "created_at", "updated_at"}

# Поля, меняющиеся при перетаскивании задач и сортировке: они не несут смысла
# для читателя ленты, поэтому в описании действия не упоминаются.
POSITION_FIELDS = {"position"}

# Одиночные смены статуса ТЗ, для которых есть готовые формулировки
SPEC_STATUS_DESCRIPTIONS = {
    "submitted": "Отправил техническое задание на согласование",
    "approved": "Согласовал техническое задание",
    "draft": "Вернул техническое задание в черновики",
}

STAGE_ACTION_DESCRIPTIONS = {
    "advance": "Перешёл на этап",
    "approve": "Согласовал этап",
    "reject": "Отклонил этап",
}

# Куда относится entity_id самой записи журнала
DIRECT_ID_BUCKETS = {
    "project": "projects",
    "resume": "resumes",
    "task": "tasks",
    "column": "columns",
}

# Имя метода, формирующего описание действия, для каждой сущности
DESCRIBERS = {
    "project": "_describe_project",
    "resume": "_describe_resume",
    "user": "_describe_user",
    "response": "_describe_response",
    "project_participation": "_describe_participation",
    "stage_transition": "_describe_stage_transition",
    "specification": "_describe_specification",
    "specification_comment": "_describe_specification_comment",
    "column": "_describe_column",
    "task": "_describe_task",
    "subtask": "_describe_subtask",
    "task_assignee": "_describe_task_assignees",
}


@dataclass
class ActivityNames:
    """Названия сущностей, упомянутых в пачке логов."""

    projects: dict[int, str] = field(default_factory=dict)
    resumes: dict[int, str] = field(default_factory=dict)
    tasks: dict[int, str] = field(default_factory=dict)
    columns: dict[int, str] = field(default_factory=dict)
    stages: dict[int, str] = field(default_factory=dict)
    users: dict[int, str] = field(default_factory=dict)


@dataclass
class _EntityIds:
    """ID сущностей, которые нужно разрешить в названия для пачки логов."""

    projects: set[int] = field(default_factory=set)
    resumes: set[int] = field(default_factory=set)
    tasks: set[int] = field(default_factory=set)
    columns: set[int] = field(default_factory=set)
    stages: set[int] = field(default_factory=set)
    users: set[int] = field(default_factory=set)


@dataclass
class _Entry:
    """Запись журнала, подготовленная к описанию."""

    log: Any
    old: dict
    new: dict
    names: ActivityNames

    @property
    def values(self) -> dict:
        """Значения, ради которых запись вообще появилась."""
        return self.new or self.old

    @property
    def changed(self) -> dict[str, tuple[Any, Any]]:
        return _changed_fields(self.old, self.new)

    def diff(self) -> list[str]:
        return _diff_fields(self.old, self.new)


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

    async def get_activity(
        self,
        user_id: int,
        page: int = 1,
        limit: int = ACTIVITY_ITEMS_LIMIT,
        day: date | None = None,
    ) -> ActivityResponse:
        """Активность пользователя от даты регистрации: агрегат по дням + лента действий

        `day` ограничивает ленту одним днём (клик по ячейке графика), но не
        `summary` — график остаётся годным.
        """

        since = await self._user_activity_start(user_id)
        # Полная выборка нужна для summary: при выборе дня график не должен
        # «схлопываться» в одну колонку, поэтому его считаем без фильтра.
        all_logs = await self._audit_repository.get_logs_by_user_id(user_id, _start_of_day(since))
        logs = (
            await self._audit_repository.get_logs_by_user_id(user_id, _start_of_day(since), day=day)
            if day is not None
            else all_logs
        )
        names = await self._resolve_names(logs)

        offset = (page - 1) * limit
        total = len(logs)
        return ActivityResponse(
            total=total,
            page=page,
            limit=limit,
            total_pages=_total_pages(total, limit),
            since=since,
            summary=_daily_summary(log.performed_at for log in all_logs),
            items=[self._to_item(log, names) for log in logs[offset : offset + limit]],
        )

    async def get_project_activity(
        self,
        project_id: int,
        page: int = 1,
        limit: int = ACTIVITY_ITEMS_LIMIT,
        day: date | None = None,
    ) -> ActivityResponse:
        """Активность проекта от первого действия в нём: лента действий всех участников

        `day` ограничивает ленту одним днём (клик по ячейке графика), но не
        `summary` — график остаётся годным.
        """

        since = await self._project_activity_start(project_id)
        offset = (page - 1) * limit
        # summary считаем по всем дням проекта, ленту — по выбранному дню.
        logs, total = await self._audit_repository.get_logs_by_project_id(project_id, offset, limit, day=day)
        stamps = await self._audit_repository.get_performed_at_by_project_id(project_id, _start_of_day(since))
        names = await self._resolve_names(logs)

        return ActivityResponse(
            total=total,
            page=page,
            limit=limit,
            total_pages=_total_pages(total, limit),
            since=since,
            summary=_daily_summary(stamps),
            items=[self._to_item(log, names) for log in logs],
        )

    async def log_task_assignees(self, task: Task, added: list[int], removed: list[int]) -> None:
        """Записать смену исполнителей задачи.

        Связь many-to-many обновляется в обход ORM-событий, поэтому изменение
        состава исполнителей не видно слушателям и логируется явно.
        """
        if not added and not removed:
            return

        context_data = get_audit_context()
        await self._audit_repository.create_log(
            entity_type="task_assignee",
            entity_id=task.id,
            action="UPDATE",
            project_id=task.project_id,
            new_values={"task_id": task.id, "added": added, "removed": removed},
            performed_by=context_data.user_id if context_data else None,
            ip_address=context_data.ip_address if context_data else None,
            user_agent=context_data.user_agent if context_data else None,
        )

    async def _user_activity_start(self, user_id: int) -> date:
        """Начало окна активности пользователя — дата его регистрации"""

        registered_at = await self._audit_repository.get_user_registered_at(user_id)
        if registered_at is not None:
            return registered_at
        return datetime.now(UTC).date() - timedelta(days=ACTIVITY_DAYS_WINDOW)

    async def _project_activity_start(self, project_id: int) -> date:
        """Начало окна активности проекта — дата первого действия в нём

        Проект часто создают раньше, чем начинают работать, поэтому начало
        берётся из первого лога активности, а не из ``Project.created_at``.
        """

        first_at = await self._audit_repository.get_first_activity_at_by_project_id(project_id)
        if first_at is not None:
            return first_at
        # Активности ещё не было: отступаем к дате создания, а если проекта
        # не нашлось — к сегодняшнему дню, чтобы окно не было пустым.
        created_at = await self._audit_repository.get_project_created_at(project_id)
        if created_at is not None:
            return created_at
        return datetime.now(UTC).date()

    def _resolve_names(self, logs: list) -> ActivityNames:
        """Собрать названия сущностей, которые упоминаются в логах"""

        ids = _EntityIds()
        for log in logs:
            _collect_ids(log, ids)
        return self._load_names(ids)

    async def _load_names(self, ids: _EntityIds) -> ActivityNames:
        repository = self._audit_repository
        return ActivityNames(
            projects=await repository.get_project_names(ids.projects),
            resumes=await repository.get_resume_names(ids.resumes),
            tasks=await repository.get_task_titles(ids.tasks),
            columns=await repository.get_column_names(ids.columns),
            stages=await repository.get_stage_names(ids.stages),
            users=await repository.get_actor_names(ids.users),
        )

    def _to_item(self, log, names: ActivityNames) -> ActivityItem:
        return ActivityItem(
            id=log.id,
            kind=f"{log.entity_type}:{log.action}",
            description=self._describe(log, names),
            performed_at=log.performed_at,
            actor=_actor(log, names),
        )

    def _describe(self, log, names: ActivityNames) -> str:
        """Сформировать человекочитаемое описание действия"""

        method_name = DESCRIBERS.get(log.entity_type)
        if method_name is None:
            return f"Выполнил действие {log.entity_type}:{log.action}"

        entry = _Entry(
            log=log,
            old=_parse_values(log.old_values) or {},
            new=_parse_values(log.new_values) or {},
            names=names,
        )
        return getattr(self, method_name)(entry)

    def _describe_project(self, entry: _Entry) -> str:
        name = (
            entry.new.get("name")
            or entry.old.get("name")
            or entry.names.projects.get(entry.log.entity_id)
            or f"проект #{entry.log.entity_id}"
        )
        if entry.log.action == "INSERT":
            return f"Создал проект «{name}»"
        if entry.log.action == "DELETE":
            return f"Удалил проект «{name}»"
        return _with_diff(f"Обновил проект «{name}»", entry.diff())

    def _describe_resume(self, entry: _Entry) -> str:
        header = entry.new.get("header") or entry.old.get("header") or entry.names.resumes.get(entry.log.entity_id)
        label = f"«{header}»" if header else f"резюме #{entry.log.entity_id}"
        if entry.log.action == "INSERT":
            return f"Создал резюме {label}"
        if entry.log.action == "DELETE":
            return f"Удалил резюме {label}"
        return _with_diff(f"Обновил резюме {label}", entry.diff())

    def _describe_user(self, entry: _Entry) -> str:
        if entry.log.action == "INSERT":
            return "Зарегистрировался в системе"
        if entry.log.action == "DELETE":
            return "Удалил аккаунт"
        return _with_diff("Обновил профиль", entry.diff())

    def _describe_response(self, entry: _Entry) -> str:
        context = _project_context(entry.values, entry.names)
        resp_type = entry.values.get("type") or "response"
        noun = "приглашение" if resp_type == "invitation" else "отклик"

        if entry.log.action == "INSERT":
            return f"Пригласил в {context}" if resp_type == "invitation" else f"Откликнулся на {context}"
        if entry.log.action == "DELETE":
            return f"Удалил {noun} в {context}"

        status = entry.new.get("status")
        if status == "accepted":
            base = f"Принял {noun} в {context}"
        elif status == "rejected":
            base = f"Отклонил {noun} в {context}"
        elif status == "withdrawn":
            base = f"Отозвал {noun} в {context}"
        else:
            base = f"Обновил {noun} в {context}"
        return _with_diff(base, entry.diff())

    def _describe_participation(self, entry: _Entry) -> str:
        participant_id = _as_int(entry.values.get("participant_id"))
        name = entry.names.users.get(participant_id) or f"участник #{participant_id}"
        if entry.log.action == "DELETE":
            return f"Исключил из проекта {name}"
        return f"Добавил в проект {name}"

    def _describe_stage_transition(self, entry: _Entry) -> str:
        stage_name = entry.names.stages.get(_as_int(entry.new.get("stage_id"))) or "следующий этап"
        action = entry.new.get("action") or ""
        description = f"{STAGE_ACTION_DESCRIPTIONS.get(action, 'Сменил этап')} «{stage_name}»"
        comment = entry.new.get("comment")
        if action == "reject" and comment:
            description = f"{description}: {_preview(comment)}"
        return description

    def _describe_specification(self, entry: _Entry) -> str:
        if entry.log.action == "INSERT":
            return "Создал техническое задание"

        new_status = entry.new.get("status")
        base = SPEC_STATUS_DESCRIPTIONS.get(new_status or "")
        if base is None or new_status == entry.old.get("status"):
            return _with_diff("Обновил техническое задание", entry.diff())

        rejection_comment = entry.new.get("rejection_comment")
        if new_status == "draft" and rejection_comment:
            return f"{base}: {_preview(rejection_comment)}"
        return base

    def _describe_specification_comment(self, entry: _Entry) -> str:
        if entry.log.action == "DELETE":
            return "Удалил комментарий к техническому заданию"
        text = entry.values.get("text")
        base = "Оставил комментарий к техническому заданию"
        return f"{base}: {_preview(text)}" if text else base

    def _describe_column(self, entry: _Entry) -> str:
        name = entry.new.get("name") or entry.old.get("name") or entry.names.columns.get(entry.log.entity_id) or "?"
        if entry.log.action == "INSERT":
            return f"Создал колонку «{name}»"
        if entry.log.action == "DELETE":
            return f"Удалил колонку «{name}»"
        return _with_diff(f"Обновил колонку «{name}»", entry.diff())

    def _describe_task(self, entry: _Entry) -> str:
        title = entry.new.get("title") or entry.old.get("title") or entry.names.tasks.get(entry.log.entity_id) or "?"
        if entry.log.action == "INSERT":
            return f"Создал задачу «{title}»"
        if entry.log.action == "DELETE":
            return f"Удалил задачу «{title}»"

        if "column_id" in entry.changed and not (set(entry.changed) - {"column_id", "position"}):
            column_name = entry.names.columns.get(_as_int(entry.new.get("column_id"))) or "другую колонку"
            return f"Переместил задачу «{title}» в «{column_name}»"
        return _with_diff(f"Обновил задачу «{title}»", entry.diff())

    def _describe_subtask(self, entry: _Entry) -> str:
        title = entry.values.get("title") or "?"
        task_title = entry.names.tasks.get(_as_int(entry.values.get("task_id")))
        task_context = f" к задаче «{task_title}»" if task_title else ""
        if entry.log.action == "INSERT":
            return f"Добавил подзадачу «{title}»{task_context}"
        if entry.log.action == "DELETE":
            return f"Удалил подзадачу «{title}»{task_context}"

        if set(entry.changed) == {"is_completed"}:
            if entry.new.get("is_completed"):
                return f"Отметил подзадачу «{title}»{task_context} выполненной"
            return f"Снял отметку о выполнении с подзадачи «{title}»{task_context}"
        return _with_diff(f"Обновил подзадачу «{title}»", entry.diff())

    def _describe_task_assignees(self, entry: _Entry) -> str:
        values = entry.values
        task_title = entry.names.tasks.get(_as_int(values.get("task_id")))
        task_label = f" задачи «{task_title}»" if task_title else " задачи"

        parts = []
        for key, verb in (("added", "добавил"), ("removed", "снял")):
            user_ids = values.get(key) or []
            if not user_ids:
                continue
            rendered = ", ".join(entry.names.users.get(_as_int(uid)) or f"#{uid}" for uid in user_ids)
            noun = "исполнителя" if len(user_ids) == 1 else "исполнителей"
            parts.append(f"{verb} {noun}{task_label}: {rendered}")
        return "; ".join(parts) or f"Обновил исполнителей{task_label}"


def _actor(log, names: ActivityNames) -> ActivityActor | None:
    if log.performed_by is None:
        return None
    return ActivityActor(
        id=log.performed_by,
        name=names.users.get(log.performed_by) or f"Пользователь #{log.performed_by}",
    )


def _collect_ids(log, ids: _EntityIds) -> None:
    """Добавить в наборы ID всех сущностей, упомянутых в записи журнала."""

    if log.performed_by:
        ids.users.add(log.performed_by)

    bucket = DIRECT_ID_BUCKETS.get(log.entity_type)
    if bucket is not None:
        getattr(ids, bucket).add(log.entity_id)

    old = _parse_values(log.old_values) or {}
    new = _parse_values(log.new_values) or {}
    values = new or old

    match log.entity_type:
        case "response":
            # Отклик и приглашение знают проект только внутри значений
            _add(ids.projects, values.get("project_id"))
        case "project_participation":
            _add(ids.users, values.get("participant_id"))
        case "subtask":
            _add(ids.tasks, values.get("task_id"))
        case "task_assignee":
            _add(ids.tasks, values.get("task_id"))
            for key in ("added", "removed"):
                for user_id in values.get(key) or ():
                    _add(ids.users, user_id)
        case "task":
            _add(ids.columns, old.get("column_id"))
            _add(ids.columns, new.get("column_id"))
        case "stage_transition":
            _add(ids.stages, values.get("stage_id"))
            _add(ids.stages, values.get("from_stage_id"))


def _add(bucket: set[int], value: object | None) -> None:
    """Добавить ID в набор, пропуская пустые и нечисловые значения."""

    if value is None or value == "":
        return
    try:
        bucket.add(int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return


def _project_context(values: dict, names: ActivityNames) -> str:
    project_name = names.projects.get(_as_int(values.get("project_id")))
    return f"проект «{project_name}»" if project_name else "проект"


def _parse_values(values: dict | str | None) -> dict | None:
    """Распарсить old/new values (могут храниться как JSON-строка или dict)"""

    if values is None:
        return None
    if isinstance(values, str):
        return json.loads(values)
    return values


def _changed_fields(old_values: dict, new_values: dict) -> dict[str, tuple[Any, Any]]:
    """Поля, значения которых действительно отличаются"""

    old = old_values or {}
    new = new_values or {}
    changed: dict[str, tuple[Any, Any]] = {}

    for name, old_val in old.items():
        if name in IGNORED_COLUMNS or name in POSITION_FIELDS:
            continue
        new_val = new.get(name)
        if old_val is None and new_val is None:
            continue
        if old_val == new_val:
            continue
        changed[name] = (old_val, new_val)

    return changed


def _diff_fields(old_values: dict, new_values: dict, limit: int = DIFF_FIELDS_LIMIT) -> list[str]:
    """Разница old → new для изменённых полей (до limit штук)"""

    changed = _changed_fields(old_values, new_values)
    if not changed:
        return []

    parts = []
    for name, (old_val, new_val) in list(changed.items())[:limit]:
        label = FIELD_LABELS.get(name, name)
        parts.append(f"{label}: {_format_value(old_val)} → {_format_value(new_val)}")

    if len(changed) > limit:
        parts.append(f"и ещё {len(changed) - limit}")
    return parts


def _with_diff(base: str, diff: list[str]) -> str:
    """Добавить diff к описанию действия, если он есть"""

    if not diff:
        return base
    return f"{base}: {', '.join(diff)}"


def _preview(text: object | None) -> str:
    """Короткая выдержка из текста для ленты"""

    value = _strip_html(str(text or ""))
    if len(value) > TEXT_PREVIEW_LENGTH:
        return f"{value[: TEXT_PREVIEW_LENGTH - 1]}…"
    return value


_TAG_RE = re.compile(r"<[^>]+>")
_ENTITIES = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"}


def _strip_html(value: str) -> str:
    """Убрать разметку rich-text редактора: в ленте нужен текст, а не теги.

    Описания проекта и ТЗ приходят из WYSIWYG, поэтому без этого diff выглядит
    как «Описание: «<p>ввыфвыф</p>…»».
    """
    text = _TAG_RE.sub(" ", value)
    for entity, char in _ENTITIES.items():
        text = text.replace(entity, char)
    return " ".join(text.split())


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
    text = _strip_html(str(value))
    if len(text) > VALUE_MAX_LENGTH:
        text = f"{text[: VALUE_MAX_LENGTH - 3]}…"
    return f"«{text}»"


def _start_of_day(value: date) -> datetime:
    """Полночь UTC указанного дня — нижняя граница окна активности."""

    return datetime.combine(value, time.min, tzinfo=UTC)


def _as_int(value: object | None) -> int:
    """Привести значение из JSON к int, не падая на мусоре."""

    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _total_pages(total: int, limit: int) -> int:
    if total <= 0:
        return 0
    return (total + limit - 1) // limit


def _daily_summary(timestamps) -> list[ActivityDay]:
    """Сгруппировать временные метки по дням (UTC)"""

    day_counts: dict[date, int] = {}
    for performed_at in timestamps:
        if performed_at is None:
            continue
        day = performed_at.date()
        day_counts[day] = day_counts.get(day, 0) + 1
    return [ActivityDay(date=day, count=count) for day, count in sorted(day_counts.items())]
