# Project Relations — проверяемый источник связей проекта

Единый проверяемый источник трёх связей проекта, используемых в оценивании:

- **Manager** — руководитель команды (`project.author_id`)
- **Студенты** — участники команды (`project_participation.participant_id`)
- **Преподаватели workspace** — пользователи с эффективной ролью teacher/admin (`workspace_participation`)

## Решение о «ответственном преподавателе»

Ответственный преподаватель **не привязывается к конкретному проекту**. Все преподаватели workspace оценивают все команды. Принять итог (#114) может любой teacher/admin workspace. Исключение при оценивании (#104) — только manager и студенты защищающейся команды.

Это закрывает открытый вопрос S0 §11.1 «Источник назначения ответственного teacher»: источника нет и не требуется — преподаватель определяется ролью в workspace, а не назначением на проект.

## API

### `GET /v1/workspaces/{workspace_id}/projects/{project_id}/relations`

Возвращает текущие связи проекта.

**Доступ:** teacher/admin workspace, либо manager (author) проекта.

**Ответ 200:**

```json
{
  "project_id": 42,
  "workspace_id": 5,
  "manager_id": 10,
  "member_ids": [11, 12, 13],
  "workspace_teacher_ids": [1, 2],
  "contract_version": 1
}
```

**Ошибки:**

| Код | Условие |
|---|---|
| 401 | Нет токена |
| 403 | Не teacher/admin workspace и не manager проекта |
| 404 | Проект не найден или не в этом workspace |
| 422 | Некорректные `workspace_id`/`project_id` (≤0) |

## Явно отвергается

- `Workspace.author_id` **не** считается преподавателем: в `workspace_teacher_ids` попадают только пользователи с явной записью `workspace_participation` и эффективной ролью teacher/admin.
- `ProjectParticipation.role` (свободная строка) **не** интерпретируется как доверенная роль оценивания. Участие определяется фактом наличия строки `project_participation`, а не её `role`.
- Подмена чужого ID: все методы проверяют, что проект принадлежит указанному `workspace_id`; при несовпадении — 404.

## Разрешение эффективной роли

Локальная роль (`workspace_participation.role_id → role.name`) приоритетнее глобальной (`user.role_id → role.name`). NULL локальной роли означает «не задана» — используется глобальная.

Admin для целей оценивания маппится в teacher (четвёртой весовой группы нет).

## Сервис

`src/services/project_relations.py` — `ProjectRelationsService`:

```python
svc.get_manager_id(project_id, workspace_id=workspace_id) -> int
svc.get_member_ids(project_id, workspace_id=workspace_id) -> list[int]
svc.get_workspace_teacher_ids(workspace_id) -> list[int]
svc.is_workspace_teacher(user_id, workspace_id=workspace_id) -> bool
svc.get_project_relations(project_id, workspace_id=workspace_id) -> ProjectRelations
```

## Контракт с соседними задачами

- **#104 (снимок аудитории)**: использует `get_project_relations` для получения manager/students/teachers при фиксации состава.
- **#114 (принятие итога)**: использует `is_workspace_teacher` для авторизации принятия итога.
- **#105 (guards)**: использует `is_workspace_teacher` и проверку workspace при отправке оценок.

## Граница «текущие связи vs снимок»

`ProjectRelationsService` всегда возвращает **текущее** состояние БД. Историческая фиксация на момент открытия окна — ответственность #104 (`assessment_window_audience`), не этого сервиса.