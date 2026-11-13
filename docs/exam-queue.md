# Очередь экзамена: порядок, откладывание, неявка и возврат

Очередь — это упорядоченный список активных записей одного Exam. Позицию занимают только ожидающие команды; выступающая, отложенная без нового места, неявившаяся и завершённая позиции не занимают. Перестановка очереди не меняет слот (плановое время), а смена слота не переставляет живую очередь.

Все операции требуют аутентификации. База маршрутов: `/v1/workspaces/{workspace_id}/exams/{exam_id}/queue`. Чтение доступно участнику, который видит опубликованный Exam; изменения — только организатору (teacher/admin с доступом), включая global admin и подходящего global teacher.

## Начальный порядок

- Exam со слотами: по `slot.starts_at`, затем `created_at, id`. Новая запись вставляется не в конец, а на место по своему слоту, чтобы план и очередь совпадали на старте.
- Exam без слотов: по `created_at, id`, новая запись — в конец.
- После первой ручной перестановки порядок задаётся позициями; новые записи по-прежнему вставляются по слоту (если слоты есть), иначе в конец.
- Позиции плотные: 1…N. Любая перестановка пересчитывает весь диапазон под блокировкой Exam.

## Прочитать очередь

```http
GET /v1/workspaces/7/exams/12/queue
```

Ответ200:

```json
{"queue_revision":17,"server_now":"2026-11-30T10:05:00Z","settings_version":3,
 "eta_stale":false,"contract_version":1,
 "items":[
  {"registration_id":92,"project_id":51,"project_type_id":8,"slot_id":null,
   "planned_start_at":null,"planned_end_at":null,"position":null,"state":"running",
   "registration_version":3,"started_at":"2026-11-30T10:05:00Z","attempt":{"id":31,"status":"speaking","version":1,"phase_deadline":"2026-11-30T10:12:00Z","remaining_seconds":420,"server_now":"2026-11-30T10:05:00Z"}},
  {"registration_id":91,"project_id":42,"project_type_id":8,"slot_id":5,
   "planned_start_at":"2026-11-30T10:15:00Z","planned_end_at":"2026-11-30T10:30:00Z","position":1,
   "state":"waiting","registration_version":2,"started_at":null,"attempt":null},
  {"registration_id":90,"project_id":40,"project_type_id":8,"slot_id":null,
   "planned_start_at":null,"planned_end_at":null,"position":null,"state":"postponed",
   "registration_version":4,"started_at":"2026-11-30T09:30:00Z","attempt":{"id":29,"status":"postponed","version":3,"remaining_seconds":120,"server_now":"2026-11-30T10:05:00Z"}}
 ],
 "eta":{"current":{"registration_id":92,"attempt_id":31,"status":"speaking","paused":false,
                   "phase_remaining_seconds":420,"slot_remaining_seconds":900,
                   "overdue_seconds":0,"settings_version":2},
        "items":[{"registration_id":91,"position":1,"state":"waiting","eta_seconds":900,
                  "eta_at":"2026-11-30T10:20:00Z","certainty":"certain","reason":null}]}}
```

- `state`: `waiting`, `running`, `postponed`, `no_show`, `finished`.
- `items` — все active записи Exam. Порядок: running (не более одной), затем позиции 1…N (включая возвращённую отложенную), затем отложенные без места, неявившиеся и завершённые.
- `attempt` — полный снимок попытки или null. Все вложенные `server_now` совпадают с верхним: сервер читает время один раз.
- `queue_revision` растёт при изменении состава/порядка/состояния очереди: создание, отмена, перенос записи, старт, `finish`, перестановка, откладывание, неявка, повторный запуск. Смена только слота ревизию не меняет. Ревизия — ориентир для клиента и будущего WebSocket (#109): по ней видно, что снимок устарел.
- `settings_version` — текущая редакция настроек Exam; из неё берутся полные слоты ожидающих, которые ещё не начинали защиту. Смена настроек не меняет `queue_revision`.
- `eta_stale` — `true`, если снимок не удалось согласовать за три попытки; значения последние, очередь нужно перечитать.
- `contract_version` — версия контракта чтения; сейчас `1`.
- `eta` — текущая защита и прогноз старта ожидающих; отложенные без позиции в него не входят.

## ETA

Блок `eta` — аддитивное расширение снимка очереди; отдельного маршрута нет. ETA считает только сервер по остатку полного слота текущей защиты, слотам команд впереди, переходам и `exam.starts_at`; клиент не пересчитывает формулу и использует `server_now`/`eta_at`. `settings_version`, `eta_stale` и `contract_version` описывают актуальность снимка, `certainty`/`reason` — паузу, просрочку или время до старта. Формула, пример 4 + 10 = 14, поля и контракт для #109 — в [инструкции ETA](exam-eta.md).

## Перестановка и возврат

```http
POST .../queue/91/place {"expected_version":2,"position":1}
POST .../queue/91/place {"expected_version":2}             # в конец
POST .../queue/91/next  {"expected_version":2}             # «поставить следующей»
```

`position` — 1…N+1, где N — число ожидающих без самой команды; null/отсутствие — в конец. Позиция вне диапазона — 409 `queue_position_out_of_range`. `place` работает и как возврат: из `postponed` или `no_show` команда снова становится `waiting`. `next` — сокращение для позиции 1.

Ответ200 `{item, queue_revision, server_now}`. Повтор с той же итоговой позицией — 200 без новой версии/события/`updated_at`. Реальная перестановка: версия регистрации +1, событие `queue_changed` (если команда уже была в очереди) или `returned` (если возвращается), с `from_position`/`to_position`, автором и серверным временем.

Завершённая — 409 `attempt_finished`; выступающая — 409 `attempt_running`; отменённая/перенесённая — 409 `registration_not_active`.

## Откладывание

### Из очереди (защита не начиналась)

```http
POST .../queue/91/postpone {"expected_version":2,"reason":"Не запускается презентация"}
```

Позиция освобождается и диапазон сжимается, `queue_hold='postponed'`, версия+1, событие `postponed`. Попытка не создаётся, окно оценивания не открывается, ноль не появляется. Повтор — 200 no-op. Из `no_show` — 409 `registration_not_queued` (сначала вернуть). Начатая защита — 409 `defense_already_started` (откладывайте через попытку).

### Из незаконченного выступления

```http
POST .../attempts/31/postpone {"expected_version":3,"reason":"Сбой проектора"}
```

Допустимо из `speaking`/`questions`, в том числе на паузе: пауза закрывается и учитывается в `paused_seconds`, попытка получает `status="postponed"`, `postponed_at`, `postponed_phase`, версия+1 и событие `postponed`. `phase_deadline` не меняется, `remaining_seconds` замораживается. Микрофон освобождается: другая команда может стартовать. Окно не открывается, вопросы типа не блокируются, попытка остаётся той же.

## Неявка

```http
POST .../queue/91/no-show {"expected_version":2,"reason":"Команда не явилась"}
```

Только для защиты, которая не начиналась. Позиция освобождается, `queue_hold='no_show'`, версия+1, событие `no_show`. Окно не открывается, попытка не создаётся, балл не появляется. Неявка — отдельный статус, не ноль и не отложенность. Повтор — 200 no-op; начатая/завершённая — 409 `defense_already_started`. Возврат — `place`/`next`, после чего команду можно стартовать обычным `POST .../attempts`.

## Повторный запуск в той же попытке

```http
POST .../attempts/31/restart {"expected_version":4,"reason":"Продолжаем"}
```

Только из `postponed`. Попытка та же (`attempt_id` не меняется), но фаза продолжается та, что была при откладывании (`speaking`/`questions`), а таймер сбрасывается на полную длительность этой фазы из редакции настроек, по которой защита начиналась: `phase_started_at=now`, `phase_deadline=now+длительность`. Пишется событие `restarted` с автором, серверным временем и причиной (необязательна). Время откладывания в `paused_seconds` не входит. Если в Exam уже идёт другая защита — 409 `another_defense_active`; повторный restart при идущей защите — 409 `attempt_not_postponed`, тихого повторного сброса таймера нет.

`finish` из `postponed` разрешён: организатор может закрыть защиту, не продолжая; окно открывается по общим правилам. Откладывание само окно не открывает.

## История

- Действия до старта (`postponed` из очереди, `no_show`, `returned`, `queue_changed`) — в `registration_event`; читаются `GET .../registrations/{id}/history`.
- Действия начатой защиты (`postponed`, `restarted`) — в `attempt_event`; читаются `GET .../attempts/{id}/events` (только организатор).
- В обоих: автор, серверное `occurred_at`, причина и версия/позиции. История append-only.

## Ошибки

401 — нет входа;403 — известный Exam без права;404 — чужой/скрытый/несуществующий объект;422 — неверное тело/path/query (включая NUL/пустую причину, bool вместо id, position 0/отрицательный/overflow);409 `detail:{code,message}`:

- `registration_not_queued` — команда не в очереди (отложена/неявка без возврата или старт не из очереди);
- `attempt_postponed` — у попытки уже есть отложенное состояние, нужен `restart`;
- `attempt_not_postponed` — restart не из `postponed`;
- `attempt_running` — перестановка выступающей; неявка/возврат начатой — `defense_already_started`;
- `attempt_finished` — перестановка завершённой; `attempt_paused` / `attempt_version_conflict` / `registration_version_conflict` / `registration_not_active` / `defense_already_started` / `another_defense_active` / `queue_position_out_of_range` / `queue_position_conflict` — конфликты состояния и версий.

`place`/`next`/`postpone`/`no-show` сверяют `expected_version` регистрации: реальная смена с устаревшей версией — 409 `registration_version_conflict`; no-op по целевому состоянию важнее версии (повтор возвращает 200).

Успех HTTP возвращается после commit. Ошибка любого шага откатывает позиции, удержание, события, окно и смену статуса.

## Хранение и проверки

Миграция `d108a10b20c7` от `d107a10b20c6` добавляет `exam.queue_revision`, `exam_registration.queue_position/queue_hold`, `exam_attempt.postponed_at/postponed_phase`, новые действия событий и `from_position/to_position`. Backfill выставляет начальный порядок активным неначавшимся записям. Downgrade деструктивен: отложенные попытки становятся `finished` без окна, queue-события удаляются; выполнять обратный цикл только на disposable PostgreSQL.

```sh
pytest tests/unit/test_exam_queue_schema.py tests/unit/test_exam_queue_api.py --no-cov
REGISTRATION_TEST_DATABASE_URL=... pytest tests/integration/test_exam_queue_db.py --no-cov
ruff check src/ tests/
ruff format --check src/ tests/
pytest --no-cov
```

`REGISTRATION_TEST_DATABASE_URL` — PostgreSQL с CREATE DATABASE; fixture создаёт случайную БД и удаляет только её. Без переменной PG-тесты skip.

## Границы

Расчёт ETA реализован в #110 и описан в [инструкции ETA](exam-eta.md); ETA — блок ответа `GET .../queue`, отдельного маршрута нет. Не реализовано здесь: WebSocket-доставка и полный снимок по подписке (#109), форма/листы/черновик и допуск (#111), редакции отправок и серверное закрытие приёма (#112), аудитория и исключения (#104/#106), пересдачи и вторая попытка. Слот при откладывании/неявке сохраняется и не освобождается; окно оценивания по-прежнему не содержит аудиторию.
