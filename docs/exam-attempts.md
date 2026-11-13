# Попытка защиты: старт, фазы, пауза и конец

Попытка создаётся по записи команды на экзамен и связывает регистрацию, экзамен, проект и workspace. Ведёт защиту организатор Exam (teacher/admin с доступом). Попытка может проходить через фазы `speaking` → `questions` → `finished`, а также быть временно отложенной (`postponed`) и продолженной в той же попытке. Пауза останавливает таймер текущей фазы, но не освобождает место выступающей команды; откладывание освобождает его. В экзамене одновременно идёт не более одной попытки.

Все операции требуют Bearer token. База маршрутов: `/v1/workspaces/{workspace_id}/exams/{exam_id}/attempts`.

## Старт

```http
POST /v1/workspaces/7/exams/12/attempts
Content-Type: application/json

{"registration_id":91,"expected_version":1}
```

Ответ201 — новая попытка, повтор200 — та же существующая:

```json
{"id":31,"workspace_id":7,"exam_id":12,"registration_id":91,"project_id":42,"project_type_id":8,
 "status":"speaking","version":1,"settings_version":1,
 "started_at":"2026-11-30T07:00:00Z","phase_started_at":"2026-11-30T07:00:00Z",
 "phase_deadline":"2026-11-30T07:07:00Z","paused_at":null,"paused_seconds":0,"finished_at":null,
 "remaining_seconds":420,"server_now":"2026-11-30T07:00:00Z","assessment_window":null,
 "created_by":17,"created_at":"2026-11-30T07:00:00Z","updated_at":"2026-11-30T07:00:00Z"}
```

Старт проверяет, что у типа проекта есть готовый список вопросов с полной шкалой 1–5; иначе возвращается 409 `questions_not_ready` и marker не ставится. Затем в одной транзакции вызывается `ExamRegistrationService.claim_for_attempt`: он ставит постоянный `started_at` регистрации, увеличивает её версию и пишет `defense_started`, после чего создаётся попытка и событие `started`. Ошибка вставки попытки или commit откатывает marker регистрации вместе с событиями `defense_started` и `started`. Длительность выступления и вопросов берётся из редакции настроек на момент старта (`settings_version`); последующие изменения настроек не сдвигают уже идущий таймер.

`expected_version` — версия регистрации. Повтор после успешного старта возвращает существующую попытку независимо от версии: идемпотентность обеспечивается самой попыткой, а не повторным claim. `project_type_id` попытки — тип проекта на момент старта; регистрация хранит тип на момент записи.

## Фазы и пауза

```http
POST .../attempts/31/questions   {"expected_version":1}
POST .../attempts/31/pause       {"expected_version":2,"reason":"Технический перерыв"}
POST .../attempts/31/resume      {"expected_version":3}
POST .../attempts/31/finish      {"expected_version":4}
```

- `questions`: `phase_started_at = now`, `phase_deadline = now + questions_minutes`; версия+1, событие `questions`. При `questions_minutes=0` дедлайн равен моменту перехода — фаза всё равно требует явного действия.
- `pause`: `paused_at = now`; версия+1, событие `paused` с причиной (необязательна). Повтор на паузе — no-op без события. `paused_seconds` хранит целые секунды и не включает текущую незавершённую паузу; во время паузы остаток берите из `remaining_seconds`.
- `resume`: дедлайн сдвигается ровно на длительность паузы, `paused_seconds` накапливается; версия+1, событие `resumed`.
- `finish`: допустим из любой незавершённой фазы, в том числе на паузе; если попытка была на паузе, её длительность добавляется в `paused_seconds`; затем `paused_at` очищается, ставится `finished_at` и пишется событие `finished`.
- Истечение дедлайна само не меняет фазу и не завершает защиту: фазу переключает и защиту заканчивает ведущий. `remaining_seconds` при этом становится отрицательным (превышение), дедлайн остаётся в ответе.
- `transition_minutes` к таймеру попытки не применяется, но входит в полный слот ETA: это интервал между командами, который учитывается в прогнозе старта следующих команд — [`exam-eta.md`](exam-eta.md).

Повтор уже применённой команды — no-op: тот же статус, версия, дедлайн и число событий; исключение — `questions` на паузе, где возвращается409 `attempt_paused`. Команды после `finished` (кроме повторного `finish`) отклоняются `409 attempt_finished`. Устаревшая `expected_version` при реальной смене — `409 attempt_version_conflict`.

## Откладывание и повторный запуск

```http
POST .../attempts/31/postpone {"expected_version":3,"reason":"Сбой проектора"}
POST .../attempts/31/restart  {"expected_version":4,"reason":"Продолжаем"}
```

- `postpone` допустим из `speaking`/`questions`, в том числе на паузе. Пауза закрывается и учитывается в `paused_seconds`; попытка получает `status="postponed"`, `postponed_at`, `postponed_phase`, версия+1 и событие `postponed`. Дедлайн не меняется, `remaining_seconds` замораживается. Место выступающей команды освобождается: другая команда может стартовать. Окно оценивания не открывается, вопросы типа не блокируются.
- `restart` допустим только из `postponed`. Попытка та же, фаза продолжается та, что была при откладывании, а таймер сбрасывается на полную длительность этой фазы из редакции настроек старта; пишется событие `restarted`. Время откладывания в `paused_seconds` не входит. Если в Exam уже идёт другая защита — `409 another_defense_active`; повторный `restart` при идущей защите — `409 attempt_not_postponed`.
- `finish` из `postponed` разрешён и открывает окно по общим правилам; откладывание само окно не открывает. `questions`/`pause`/`resume` на `postponed` — `409 attempt_postponed`.
- Очередь, неявка и возврат команд — [`exam-queue.md`](exam-queue.md).

## Конец защиты и окно оценивания

`finish` в одном UoW:

1. блокирует Exam и попытку;
2. вызывает `ExamService.prepare_assessment_window` с текущей редакцией настроек — при первом окне этого типа навсегда блокирует его вопросы;
3. сохраняет `assessment_window` с `opened_at`, `closes_at`, `settings_version`, типом проекта;
4. завершает попытку и пишет событие.

`closes_at = opened_at + assessment_window_minutes`. Длительности фаз берутся из редакции старта, срок окна — из текущей редакции на момент конца. Ошибка любого шага откатывает попытку, окно и новый question lock. Повторный `finish` возвращает сохранённое окно и не пересчитывает срок даже после изменения настроек.

Если список вопросов очистили уже после старта, `finish` вернёт 409 `questions_not_ready`; попытка остаётся идущей, окно и lock не создаются — нужно восстановить вопросы и повторить `finish`.

Окно связано с попыткой и содержит срок, но **не содержит аудиторию**: допущенные/исключённые и доступ к форме — задачи #104/#106/#111. Поэтому «окно открыто допущенным» этим API не подтверждается.

## Чтение и восстановление

```http
GET .../attempts/current
GET .../attempts/31
GET .../attempts/31/events?limit=50&offset=0
```

`current` отдаёт выступающую попытку (`speaking`/`questions`); если её нет — последнюю отложенную (`postponed`), затем последнюю завершённую этого Exam, иначе `{"attempt":null}`. Так после откладывания карточка не подменяется чужой завершённой защитой. Ответ содержит абсолютный `phase_deadline`, серверные `server_now` и `remaining_seconds`; клиент не использует собственные часы как источник истины. При паузе остаток заморожен. `events` — append-only история, доступна организатору; пагинация `limit` 1–100, `offset`, `has_more`.

Чтение доступно участнику, который видит опубликованный Exam; draft скрыт. Мутации — только организатор Exam. Проект, руководитель и состав команды в ответ не входят: их отдают существующие проектные API.

## Ошибки

401 — нет входа;403 — известный Exam без права;404 — чужой/скрытый/несуществующий объект;422 — неверное тело/path/query (включая NUL в причине и bool вместо id);409 `detail:{code,message}`:

- `another_defense_active` — в Exam уже идёт другая попытка;
- `attempt_finished` / `attempt_paused` — действие недопустимо в текущем состоянии;
- `attempt_version_conflict` — устаревшая версия команды;
- `defense_already_started` — регистрация уже начиналась, а попытки нет (повреждённая связь);
- `registration_not_active` / `registration_version_conflict` / `project_type_not_allowed` / `exam_not_published` / `settings_version_conflict` — из claim; `questions_not_ready` — из проверки готовности на старте или в `finish`; коды не подменяются.

## Хранение и границы

Миграция `d107a10b20c6` от `d102a10b20c5` добавляет `exam_attempt`, `attempt_event`, `assessment_window`; #108 расширяет статус `postponed`, поля `postponed_at/postponed_phase` и действия `postponed/restarted`. Ограничения: `UNIQUE(registration_id)`, partial `UNIQUE(exam_id) WHERE status IN ('speaking','questions')` (отложенная микрофон не держит), scoped FK к регистрации/типу, CHECK статуса/времени/паузы, `UNIQUE(attempt_id,version)` событий. Downgrade теряет попытки/события/окна, сохраняя регистрации, Exam и вопросы; созданный `finish` question lock в `project_type_question_lock` при этом остаётся, поэтому цикл выполнять только в disposable БД.

Очередь, перестановка, откладывание из очереди, неявка и возврат реализованы в #108 и описаны в [`exam-queue.md`](exam-queue.md). ETA реализована в #110 и описана в [`exam-eta.md`](exam-eta.md). Не реализовано здесь: WebSocket (#109), аудитория и допуск (#104/#106), автооткрытие формы/срок/черновик (#111), отправка, редакции и серверный дедлайн (#112), пересдачи и вторая попытка — у регистрации ровно одна попытка.

```sh
pytest tests/unit/test_exam_attempt_schema.py tests/unit/test_exam_attempt_api.py --no-cov
REGISTRATION_TEST_DATABASE_URL=... pytest tests/integration/test_exam_attempts_db.py tests/integration/test_exam_queue_db.py --no-cov
ruff check src/ tests/
ruff format --check src/ tests/
pytest --no-cov
```

`REGISTRATION_TEST_DATABASE_URL` — PostgreSQL с CREATE DATABASE; fixture создаёт случайную `registration_test_<uuid>` и удаляет только её. Без переменной PG-тесты skip. CI проверяет PostgreSQL 18, локально возможен 14.17.
