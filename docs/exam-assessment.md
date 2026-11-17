# Оценка после защиты: форма, черновик и допуск

После завершения защиты (`finish`) сервер открывает окно оценивания
(`assessment_window`). Допущенные участники workspace получают персональную
форму с вопросами типа проекта, уровнями 1–5 и серверным сроком.

## Кто допущен

Допуск и роль читаются из неизменяемого `assessment_window_audience` (#104),
зафиксированного в транзакции `finish`. Изменение роли, автора или состава
проекта после открытия окна не переписывает исторический допуск. Новый
участник workspace не получает доступ к уже открывшимся окнам задним числом.

- Все teacher/admin этого workspace оценивают все команды, в том числе при
  собственном авторстве или участии в проекте. Отдельного ответственного
  преподавателя нет; авторство workspace само по себе не даёт роль teacher.
- Для остальных ролей свои member и manager исключены.
- Локальная роль приоритетна; глобальная используется при NULL локальной.
  Admin учитывается в группе teacher. Пользователь без роли не включается.
- Вес читается из `ExamSettingsRevision` по **`window.settings_version`**,
  которая может отличаться от версии на старте Attempt.

Для старых окон без снимка возвращается `409` с кодом
`audience_snapshot_unavailable`. Текущие связи не подставляются вместо истории;
лист при таком запросе не создаётся.

## Endpoints

### GET `/v1/workspaces/{workspace_id}/exams/{exam_id}/attempts/{attempt_id}/assessment`

Получить форму оценивания для текущего пользователя. При первом вызове сервер
создаёт пустой лист черновика (lazy creation); при повторном возвращает
существующий.

Ответ:

```json
{
  "attempt_id": 1,
  "project_id": 10,
  "project_type_id": 5,
  "window": {
    "opened_at": "2026-11-16T10:30:00Z",
    "closes_at": "2026-11-16T10:45:00Z",
    "settings_version": 3
  },
  "assessor": {
    "role": "teacher",
    "weight": 60,
    "excluded": false,
    "exclusion_reason": null
  },
  "questions": [
    {
      "id": 1,
      "text": "Актуальность темы",
      "description": "Насколько тема соответствует...",
      "position": 0,
      "levels": [
        {"score": 1, "description": "..."},
        {"score": 2, "description": "..."},
        {"score": 3, "description": "..."},
        {"score": 4, "description": "..."},
        {"score": 5, "description": "..."}
      ]
    }
  ],
  "draft": {
    "answers": [
      {"question_id": 1, "score": 4, "comment": "..."}
    ],
    "updated_at": "2026-11-16T10:35:00Z"
  }
}
```

Коды:
- `403` — исключён из зафиксированной аудитории либо отсутствует в ней
- `409` — исторический снимок аудитории недоступен (`audience_snapshot_unavailable`)
- `404` — окно не существует (попытка не завершена или нет `assessment_window`)
- `401` — не аутентифицирован

Поле `submission` (#112, добавлено к ответу; остальные поля не менялись): `null`, пока лист не отправлялся, иначе
`{"version": 2, "submitted_at": "...", "has_unsubmitted_changes": true}`. `has_unsubmitted_changes = true`, если
сохранённый черновик (баллы и комментарии) отличается от последней отправленной редакции.

### PUT `/v1/workspaces/{workspace_id}/exams/{exam_id}/attempts/{attempt_id}/assessment/draft`

Сохранить личный черновик.

```json
{
  "answers": [
    {"question_id": 1, "score": 4, "comment": "Хорошая тема"},
    {"question_id": 2, "score": null, "comment": null}
  ]
}
```

Валидация:
- `score`: `1`–`5` или `null` (очистка ответа)
- `comment`: до 5000 символов, `null` допустим
- `question_id`, не принадлежащий типу проекта попытки — молча игнорируется
- при повторе одного `question_id` внутри payload используется последнее значение

После `closes_at` (серверные часы, `now >= closes_at`) черновик не сохраняется: `409` с кодом
`assessment_window_closed`. Правки после отправки остаются черновиком и на учтённый голос не влияют, пока не отправлены.

Ответ — обновлённый объект `draft` (как в GET). `updated_at` листа обновляется
только при изменении допустимых ответов. Повторное сохранение тех же данных
не меняет ответы и их timestamps, включая `updated_at` листа.

### POST `/v1/workspaces/{workspace_id}/exams/{exam_id}/attempts/{attempt_id}/assessment/submit`

Отправить лист (#112). Тело пустое (или `{}`): любое поле (`role`, `weight`, баллы, `total`) → `422`. Сервер сам
снимает **сохранённый** черновик в новую неизменяемую редакцию; клиент ничего не присылает и роль/вес не задаёт.

Проверки по порядку: вход как у формы (попытка завершена и окно есть → иначе `404`; нет снимка аудитории → `409`
`audience_snapshot_unavailable`; не в аудитории или исключён → `403`), срок (`now >= closes_at` → `409`
`assessment_window_closed`), полнота, блокировка строки листа (`FOR UPDATE`) и повторная проверка срока.

Полнота: отвечены все вопросы типа проекта попытки (`score` не NULL). Иначе `422`:

```json
{"detail": {"code": "incomplete_sheet", "message": "...", "missing_question_ids": [2, 3]}}
```

(422, а не 409: данные листа неполны, состояние экзамена в порядке). Если лист ни разу не открывали, пропущены все вопросы.
Комментарии необязательны, в сумму не входят, но хранятся в редакции.

Версии и идемпотентность: версия 1 — первая отправка. Если баллы и комментарии черновика совпадают с последней
редакцией, возвращается она же (`unchanged: true`), новой версии нет; иначе версия = последняя + 1. Повторная отправка
разрешена до `closes_at`; считается **последняя** отправленная редакция, при просрочке отклоняется и ничего не меняет.
Конкурентные отправки одного листа сериализуются блокировкой строки листа, `UNIQUE(sheet_id, version)` — страховка.

Ответ `200`:

```json
{
  "version": 2,
  "submitted_at": "2026-11-16T10:40:00Z",
  "total": 18,
  "unchanged": false,
  "answers": [{"question_id": 1, "score": 4, "comment": "..."}]
}
```

Коды: `403` исключён/не в аудитории, `404` чужой workspace/экзамен/попытка или окно не открыто, `409`
`assessment_window_closed` / `audience_snapshot_unavailable`, `422` `incomplete_sheet` или лишние поля тела.

## Где лежат отправки (для #122 и отчётов)

- `exam_assessment_sheet` — один лист на (`user_id`, `attempt_id`), `status` = `draft` до первой отправки, потом `submitted`
  (статус не откатывается: наличие учтённого голоса определяют редакции, а не статус).
- `exam_assessment_submission` — редакция: `sheet_id`, `version` (≥1, `UNIQUE(sheet_id, version)`), `submitted_at`,
  `total` (сумма баллов), а также `workspace_id/exam_id/attempt_id` (составной FK на лист — изоляция областей).
- `exam_assessment_submission_answer` — пять (N) баллов редакции: `submission_id`, `question_id`, `score` 1…5, `comment`.
- Роль и допуск — `assessment_window_audience` (по `window_id`, `user_id`), не текущие связи.

«Кто отправил, когда, версия, сумма, баллы» (последняя редакция допущенных):

```sql
SELECT a.user_id, a.role, sub.version, sub.submitted_at, sub.total, ans.question_id, ans.score
FROM assessment_window w
JOIN assessment_window_audience a ON a.window_id = w.id AND a.admitted
JOIN exam_assessment_sheet sh ON sh.user_id = a.user_id AND sh.attempt_id = w.attempt_id
JOIN exam_assessment_submission sub ON sub.sheet_id = sh.id
  AND sub.version = (SELECT max(version) FROM exam_assessment_submission WHERE sheet_id = sh.id)
JOIN exam_assessment_submission_answer ans ON ans.submission_id = sub.id
WHERE w.attempt_id = :attempt_id;
```

Допущенный без отправки (нет строки в `exam_assessment_submission`) — «не отправил»; число отправок —
`max(version)`. Для кода: `ExamAssessmentRepository.counted_sheets(attempt_id)` отдаёт (роль, сумма) для расчёта.

Реальный `ExamSheetSource` (`SubmittedSheetSource`) читает эти же таблицы — см. [exam-results.md](exam-results.md).
Контракт live-канала (WebSocket) не менялся: отправка листа `mark_exam_changed` не вызывает (лист личный, подходящего типа
изменения нет).

## Гарантии

- Один лист на пользователя на попытку (ограничение `uq_sheet_user_attempt`).
- Лист привязан к попытке, не к очереди — смена текущей команды не подменяет листы.
- Несколько связей пользователя дают один лист с ролью, зафиксированной в аудитории.
- Конкурентное открытие листа не откатывает внешнюю транзакцию.
- Ответы записываются в стабильном порядке ID: две вкладки с обратным порядком
  вопросов не создают взаимную блокировку.
- Черновик персональный — не передаётся в общий WebSocket-снимок экзамена.
- Список вопросов типа заблокирован с первого окна (`ProjectTypeQuestionLock`).

## Вне объёма

- Усреднение оценок преподавателей — калькулятор #113; принятие итога — #114.
- Продление окна оценивания — открытый вопрос Q4 (не реализовано).
- Второе `assessment_window` не создаётся; `closes_at` не пересчитывается.

Миграция `d111a10b20c9` следует за `d104a10b20c9`: обе таблицы аудитории и
персональных листов доступны в единой последовательной цепочке миграций.

Миграция `d112a10b20c9` (после `d114a10b20c9`) добавляет таблицы редакций отправленных листов.
