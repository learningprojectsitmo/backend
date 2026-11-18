# Участие в оценивании: кто допущен, отправил, не отправил, исключён

AC-07 (#105, #117). Teacher/admin видят по одной защите (попытке), кто из аудитории окна оценивания допущен, кто
отправил лист, кто не отправил и кто исключён и почему. Читается только снимок аудитории
`assessment_window_audience`, зафиксированный при открытии окна ([exam-assessment.md](exam-assessment.md)); текущие
связи с проектами и роли пользователей не пересчитываются.

## Endpoint

`GET /v1/workspaces/{workspace_id}/exams/{exam_id}/attempts/{attempt_id}/participation` — только чтение, без тела.

Права (как у результата, см. [exam-results.md](exam-results.md)): видимость экзамена (`require_read_access`), затем
`ProjectRelationsService.is_workspace_teacher` — effective teacher/admin именно этого workspace.

| Код | Когда |
|---|---|
| 200 | есть доступ; окно открыто, закрыто или не открывалось (`state`) |
| 401 | нет токена |
| 403 | экзамен виден, но пользователь не teacher/admin workspace (member, manager, global admin вне workspace) |
| 404 | экзамен скрыт/чужой/не найден, попытка не найдена или принадлежит другому экзамену/workspace |
| 409 `audience_snapshot_unavailable` | окно открыто до появления снимка аудитории (старые окна); текущие связи не подставляются |
| 422 | id вне диапазона |

## Ответ

```json
{
  "workspace_id": 7, "exam_id": 12, "attempt_id": 31,
  "state": "open",
  "window": {"opened_at": "2026-11-30T07:00:00Z", "closes_at": "2026-11-30T07:03:00Z", "settings_version": 1},
  "summary": {
    "total":   {"admitted": 5, "submitted": 2, "not_submitted": 3, "excluded": 2},
    "teacher": {"admitted": 2, "submitted": 1, "not_submitted": 1, "excluded": 0},
    "manager": {"admitted": 1, "submitted": 1, "not_submitted": 0, "excluded": 1},
    "member":  {"admitted": 2, "submitted": 0, "not_submitted": 2, "excluded": 1}
  },
  "items": [
    {
      "user_id": 5, "name": "Анна Иванова", "role": "teacher", "status": "submitted", "exclusion_reason": null,
      "submission": {
        "version": 2, "submitted_at": "2026-11-30T07:01:10Z", "total": 22,
        "answers": [{"question_id": 1, "score": 5, "comment": "Сильная защита"}]
      }
    },
    {"user_id": 9, "name": "Пётр Сидоров", "role": "manager", "status": "excluded",
     "exclusion_reason": "manager_of_defending_team", "submission": null}
  ]
}
```

- `state`: `not_offered` — окно оценивания не открывалось (попытка не завершена): `window: null`, `items: []`, нулевая
  сводка; `open` — `now < closes_at`; `closed` — иначе (серверные часы, как при отправке).
- `status` оценщика: `excluded` («не должен оценивать», `admitted = false`); `submitted` — допущен и есть хотя бы одна
  отправка внутри окна `[opened_at, closes_at)` (отправка вне окна не голос, как в CSV); `not_submitted` — допущен, отправки нет. **Черновик не голос**: допущенный только с черновиком — это
  `not_submitted`, текст и сам факт черновика не раскрываются. Отсутствие права тоже не голос: лист исключённого, если он
  каким-то образом есть, не показывается и не считается.
- `role` — из снимка (`teacher|manager|member`, admin входит в teacher), `name` — `first_name last_name` без висящих
  пробелов.
- `exclusion_reason` — `manager_of_defending_team` / `member_of_defending_team` (хранимые значения снимка, те же, что в CSV), иначе `null`.
- `submission` — последняя редакция отправленного листа (`version`, `submitted_at`, `total`, все `answers`); баллы и
  комментарии видны teacher/admin. Предыдущие редакции здесь не выдаются.
- Время: момент исключения — это `window.opened_at` (снимок аудитории создаётся одной транзакцией с открытием окна);
  отдельного времени у исключённого нет. Время отправки — `submission.submitted_at`.
- `summary`: целые `admitted` (= `submitted` + `not_submitted`), `submitted`, `not_submitted`, `excluded` для `total` и по
  каждой роли.
- Порядок строк детерминирован: роль (teacher, manager, member), `name`, `user_id`; пагинации нет (аудитория ограничена
  составом workspace).

## Для переиспользования в CSV «участие оценщиков» (#122)

`src/repository/exam_participation_repository.py`:

```python
ExamParticipationRepository(uow).list_participation(*, workspace_id, exam_id, attempt_id) -> ExamParticipation | None
# ExamParticipation(window: ParticipationWindow, rows: tuple[ParticipationRow, ...]); None — окно не открывалось
# ParticipationRow(user_id, first_name, last_name, role, admitted, exclusion_reason, submission) + .name, .status
```

Не более трёх SQL независимо от числа оценщиков (окно; аудитория LEFT JOIN лист LEFT JOIN последняя редакция; ответы
последних редакций одним запросом по `IN`). Dataclass-строки не зависят от HTTP-схем; `exclusion_reason` в строке —
значение снимка, без перевода. Для CSV по всему экзамену метод вызывается на
каждую попытку (или расширяется списком `attempt_id` отдельной задачей).

## Что не входит

CSV-выгрузка (#122), UI (#81), выдача итога студентам (Q5), WebSocket (`mark_exam_changed` не вызывается), продление окна,
изменение расчёта, принятия и отправки. Миграций нет.

Тесты: `tests/unit/test_exam_participation.py` (сервис, права, статусы, часы, API),
`tests/integration/test_exam_participation_db.py` (Postgres: смешанная аудитория, число SQL, снимок роли, изоляция).
