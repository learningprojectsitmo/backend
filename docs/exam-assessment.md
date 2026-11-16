# Оценка после защиты: форма, черновик и допуск

После завершения защиты (`finish`) сервер открывает окно оценивания
(`assessment_window`). Допущенные участники workspace получают персональную
форму с вопросами типа проекта, уровнями 1–5 и серверным сроком.

## Кто допущен

Для попытки с проектом `P` в workspace `W`:

- **Исключены:** автор проекта `P` (руководитель команды), участники проекта `P`
  (члены команды), пользователи не из workspace `W`.
- **Допущены:** остальные участники workspace `W`, глобальные admin.

Ответственный teacher не назначается — все преподаватели workspace оценивают
все команды. Усреднение оценок преподавателей — отдельная задача (#113).

Роль, вес и допуск вычисляет сервер. Эффективная роль: глобальный admin или
локальный admin/teacher → `teacher`; локальный `manager` → `manager`;
локальный `member` → `member`. Вес берётся из весов настройки Exam
(`teacher_weight` / `manager_weight` / `member_weight`).

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
- `403` — исключён (`own_project_manager` / `own_project_member` / `not_workspace_member`)
- `404` — окно не существует (попытка не завершена или нет `assessment_window`)
- `401` — не аутентифицирован

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

Ответ — обновлённый объект `draft` (как в GET). Повторный запрос с теми же
значениями идемпотентен — `updated_at` не меняется.

## Гарантии

- Один лист на пользователя на попытку (ограничение `uq_sheet_user_attempt`).
- Лист привязан к попытке, не к очереди — смена текущей команды не подменяет листы.
- Несколько ролей/связей пользователя дают один лист с высшей применимой ролью.
- Черновик персональный — не передаётся в общий WebSocket-снимок экзамена.
- Список вопросов типа заблокирован с первого окна (`ProjectTypeQuestionLock`).

## Вне объёма #111

- Отправка листа, редакции отправленного и проверка `closes_at` — #112.
- Усреднение оценок преподавателей — #113.
- Второе `assessment_window` не создаётся; `closes_at` не пересчитывается.