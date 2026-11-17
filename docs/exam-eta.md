# ETA: остаток слота, очередь и переходы

ETA — серверный детерминированный прогноз: через сколько ожидающая команда сможет начать защиту и во сколько это будет по серверному времени. Прогноз строится из остатка полного слота текущей защиты, полных слотов команд впереди (включая переходы между командами) и планового начала Exam. Статистика, средние по истории и клиентский пересчёт не используются.

Все операции требуют аутентификации. ETA не имеет отдельного маршрута: это блок `eta` в ответе `GET /v1/workspaces/{workspace_id}/exams/{exam_id}/queue`. Чтение доступно участнику, который видит опубликованный Exam; draft скрыт от не-писателей; чужой workspace или Exam — 404. Новых ролей и аудитории нет: права те же, что у очереди.

## Формула

Полный слот команды — это временной блок из настроек, а не строка `exam_slot`:

```
полный_слот = presentation_minutes + questions_minutes + transition_minutes
```

Для целевой команды на позиции `p` среди ожидающих (1 — первая после текущей; текущая защита в позицию не входит):

```
cursor = now
если текущей защиты нет и now < exam.starts_at:
    cursor = exam.starts_at
    reason = before_start
если текущая защита есть:
    cursor += остаток_полного_слота(текущей)
    если пауза или просрочка:
        certainty = lower_bound
        reason = paused или overdue

для i = 1..p-1:
    cursor += полный_слот(команда_i)

eta_at(p)      = cursor
eta_seconds(p) = max(0, floor((eta_at(p) - now).total_seconds()))
```

`eta_seconds` — целые секунды, не меньше нуля. `eta_at` — абсолютный прогноз старта в UTC с `Z`. Время до `exam.starts_at` — единственное плановое время, которое участвует в формуле; индивидуальные слоты в неё не входят.

## Полный слот и остаток текущей защиты

Пусть `reference = paused_at`, если попытка на паузе, иначе `now`:

```
phase_remaining = max(0, floor((phase_deadline - reference).total_seconds()))
overdue_seconds = max(0, floor((reference - phase_deadline).total_seconds()))
```

- `speaking`: остаток полного слота = `phase_remaining + questions_minutes + transition_minutes`.
- `questions`: остаток полного слота = `phase_remaining + transition_minutes`.
- `finished`: текущей защиты нет, остаток равен нулю.
- `postponed`: текущей защиты нет. Если команда возвращена в очередь, она учитывается как ожидающая.
- При паузе остаток считается по `paused_at`; это прогноз «если продолжить сейчас», поэтому `certainty=lower_bound`, `reason=paused`.
- При превышении дедлайна (`overdue_seconds > 0`) остаток текущей фазы для прогноза равен нулю, `slot_remaining_seconds=0`, `certainty=lower_bound`, `reason=overdue`. Следующие фазы не обещаются: ведущий может завершить защиту сейчас.

Длительности текущей попытки берутся из `attempt.settings_version` — редакции, по которой защита начиналась. Последующее изменение настроек не сдвигает уже идущий таймер.

Для ожидающих команд:

- никогда не начинавшаяся команда — полный слот из текущей редакции Exam (`settings_version`);
- отложенная, возвращённая в очередь (`state=postponed`, позиция задана), — полный слот фазы, с которой она будет продолжена после `restart`; таймер сбрасывается на полную длительность из `attempt.settings_version`:
  - `postponed_phase=speaking` — `presentation + questions + transition`;
  - `postponed_phase=questions` — `questions + transition`;
  - `postponed_phase` отсутствует (повреждённое состояние) — полный слот текущей редакции;
- если организатор завершит такую попытку через `finish`, не делая `restart`, прогноз для команд позади был консервативным (полный слот); снимок после `finish` пересчитывается и уменьшает ETA;
- `finished`, `no_show` и `postponed` без позиции в сумму не входят.

В таймлайн попадают только текущая защита в статусе `speaking`/`questions` и ожидающие с `queue_position IS NOT NULL` в порядке позиции. `GET .../attempts/current` для этого не используется: он может вернуть `postponed` или `finished`. `waiting` без позиции — повреждённое состояние, такая запись не входит и не блокирует остальных.

## Контрольный пример 4 + 10 = 14

Фиксированное серверное время `2026-11-30T14:00:00Z`.

- Защищается A: `status=questions`, `phase_deadline=14:03`, `questions_minutes=3`, `transition_minutes=1` → остаток полного слота A = 3 + 1 = **4 минуты**.
- Перед C стоит B: `presentation=5`, `questions=4`, `transition=1` → полный слот B = **10 минут**.
- C — позиция 2.

```
cursor = 14:00 + 4 = 14:04       # B
eta(B) = 4 минуты, eta_at = 14:04

cursor = 14:04 + 10 = 14:14      # C
eta(C) = 14 минут, eta_at = 14:14
```

`eta_seconds(B)=240`, `eta_at(B)=2026-11-30T14:04:00Z`; `eta_seconds(C)=840`, `eta_at(C)=2026-11-30T14:14:00Z`. Это и есть приёмка «4 + 10 = 14 минут». Переход в одну минуту уже входит в 4 и 10; отдельного перерыва нет.

## Плановое начало и слоты

Если текущей защиты нет и `now < exam.starts_at`, прогноз отсчитывается от `starts_at`, `reason=before_start`, `certainty=certain`. Если экзамен уже начинался (есть любая Attempt, включая finished/postponed, или `exam_registration.started_at`), правило не применяется: даже после раннего завершения до `starts_at` очередь идёт от `now`.

Индивидуальные `exam_slot.starts_at/ends_at` — плановое время и на ETA не влияют:

- ETA следует порядку очереди, а не плановым временам, и может быть раньше или позже `planned_start_at`;
- длительность команды берётся из настроек, а не из длительности слота;
- смена слота не меняет ETA и не меняет `queue_revision`; `planned_start_at`/`planned_end_at` и `registration_version` в `items` обновляются;
- жёсткое ограничение старта раньше слота не вводится.

## Ответ

```http
GET /v1/workspaces/7/exams/12/queue
```

Ответ200:

```json
{
  "queue_revision": 17,
  "server_now": "2026-11-30T14:00:00Z",
  "settings_version": 3,
  "eta_stale": false,
  "contract_version": 1,
  "items": [
    {
      "registration_id": 92,
      "project_id": 51,
      "project_type_id": 8,
      "slot_id": null,
      "planned_start_at": null,
      "planned_end_at": null,
      "position": null,
      "state": "running",
      "registration_version": 3,
      "started_at": "2026-11-30T13:55:00Z",
      "attempt": {
        "id": 31,
        "status": "questions",
        "version": 3,
        "settings_version": 2,
        "phase_deadline": "2026-11-30T14:03:00Z",
        "remaining_seconds": 180,
        "server_now": "2026-11-30T14:00:00Z"
      }
    },
    {
      "registration_id": 91,
      "project_id": 42,
      "project_type_id": 8,
      "slot_id": 5,
      "planned_start_at": "2026-11-30T14:10:00Z",
      "planned_end_at": "2026-11-30T14:20:00Z",
      "position": 1,
      "state": "waiting",
      "registration_version": 2,
      "started_at": null,
      "attempt": null
    },
    {
      "registration_id": 90,
      "project_id": 40,
      "project_type_id": 8,
      "slot_id": null,
      "planned_start_at": null,
      "planned_end_at": null,
      "position": 2,
      "state": "waiting",
      "registration_version": 2,
      "started_at": null,
      "attempt": null
    }
  ],
  "eta": {
    "current": {
      "registration_id": 92,
      "attempt_id": 31,
      "status": "questions",
      "paused": false,
      "phase_remaining_seconds": 180,
      "slot_remaining_seconds": 240,
      "overdue_seconds": 0,
      "settings_version": 2
    },
    "items": [
      {
        "registration_id": 91,
        "position": 1,
        "state": "waiting",
        "eta_seconds": 240,
        "eta_at": "2026-11-30T14:04:00Z",
        "certainty": "certain",
        "reason": null
      },
      {
        "registration_id": 90,
        "position": 2,
        "state": "waiting",
        "eta_seconds": 840,
        "eta_at": "2026-11-30T14:14:00Z",
        "certainty": "certain",
        "reason": null
      }
    ]
  }
}
```

`items` — существующий снимок очереди #108 без изменения формы: в нём есть все активные записи, включая отложенные без позиции. `eta.items` — только ожидающие и возвращённые отложенные с позицией, в порядке позиций. Поэтому отложенная без позиции остаётся в `items`, но отсутствует в `eta.items` и не задерживает остальных. `eta` и поля актуальности есть только в ответе чтения; ответы мутаций очереди сохраняют прежнюю форму `{item, queue_revision, server_now}`.

Плановые времена в `items` — справочные: в примере B стоит в плане на 14:10, а ETA показывает 14:04, потому что очередь живая и может начаться раньше плана.

## Поля ответа

- `queue_revision` — ревизия снимка очереди; растёт при изменении состава, порядка или состояния очереди. Смена только слота её не меняет.
- `server_now` — серверное время снимка; единственный источник «сейчас». Вложенные `server_now` в попытках совпадают с верхним.
- `settings_version` — текущая редакция настроек Exam. Из неё берутся полные слоты ожидающих, которые ещё не начинали защиту; отложенная попытка с позицией считается по редакции своей попытки. Смена настроек увеличивает `settings_version`, но не `queue_revision`.
- `eta_stale` — `true`, если после трёх попыток не удалось получить согласованный снимок: изменились `queue_revision`, текущая редакция настроек или версии попыток. Значения — последний снимок; клиенту нужно перечитать очередь.
- `contract_version` — версия контракта чтения; сейчас `1`.
- `items` — существующие элементы очереди #108 без изменения формы.
- `eta.current` — текущая защита (`speaking`/`questions`) или `null`. Содержит `registration_id`, `attempt_id`, `status`, `paused`, `phase_remaining_seconds`, `slot_remaining_seconds`, `overdue_seconds`, `settings_version`.
- `eta.current.phase_remaining_seconds` — остаток текущей фазы, ≥0.
- `eta.current.slot_remaining_seconds` — остаток полного слота, ≥0; при паузе — по `paused_at`; при превышении — 0.
- `eta.current.overdue_seconds` — превышение дедлайна, ≥0.
- `eta.current.settings_version` — редакция старта попытки.
- `eta.items` — только ожидающие и возвращённые отложенные с позицией, в порядке позиций. Каждый элемент содержит `registration_id`, `position`, `state`, `eta_seconds`, `eta_at`, `certainty`, `reason`.
- `eta.items[].state` — `waiting` или `postponed` (возвращённая).
- `eta.items[].eta_seconds` — относительное ожидание, целые секунды, ≥0.
- `eta.items[].eta_at` — абсолютный прогноз старта, UTC.
- `eta.items[].certainty` — `certain` для детерминированного прогноза или `lower_bound` для «не раньше», когда текущая защита на паузе или просрочена.
- `eta.items[].reason` — `null`, `paused`, `overdue` или `before_start`.

Для `finished`, `no_show` и `postponed` без позиции ETA не существует: их нет в `eta.items`. Состояние таких команд клиент берёт из `items`.

## Серверное время и актуальность

- Сервер читает `server_now` один раз за попытку снимка. `eta_at` согласован с `server_now` и `eta_seconds` в пределах секунды (для `before_start` `eta_at` может быть `starts_at` с микросекундами, а `eta_seconds` — floor); клиент не пересчитывает формулу и не использует собственные часы как источник истины.
- `queue_revision` и `settings_version` — два независимых признака актуальности. Смена настроек не меняет `queue_revision`, но меняет ETA, поэтому клиент сравнивает оба значения.
- Снимок делается не более трёх раз; при расхождении во время чтения `queue_revision`, текущей редакции настроек или карты версий попыток снимок повторяется. Версии попыток проверяются всегда: `questions`, `pause` и `resume` меняют состояние попытки, но не `queue_revision`; без этой проверки возможен torn read.
- Если на последней попытке состояние всё ещё менялось, возвращается последний снимок с `eta_stale=true`. Это деградация, а не ошибка: `queue_revision` и `settings_version` относятся к снимку, а клиент должен перечитать очередь.
- `certainty=lower_bound` — сигнал «не раньше»; UI показывает паузу или задержку и уточнение прогноза, а не «0 минут» как обещание.
- `contract_version` фиксирует контракт чтения для #109 и будущих изменений. Новые поля не удаляются и не меняют смысл без `contract_version+1`.
- Если обязательную редакцию настроек прочитать невозможно, ответ — 500, без выдуманного успешного снимка.

## Пауза и просрочка

- Пауза замораживает остаток текущей фазы по `paused_at`, ETA считается как «если продолжить сейчас». Момент продолжения неизвестен, поэтому все ожидающие получают `certainty=lower_bound`, `reason=paused`; `eta_seconds` не отрицателен.
- При превышении дедлайна `overdue_seconds > 0`: `phase_remaining_seconds=0`, `slot_remaining_seconds=0`, ожидающие получают `certainty=lower_bound`, `reason=overdue`. Значения не уходят в минус.
- Если пауза и превышение одновременно, приоритет у `paused`; остаток равен нулю, `certainty=lower_bound`.
- Если текущей защиты нет, пауза и превышение не применяются.

## Нет текущей защиты и пустая очередь

- Нет текущей, очередь не пуста: первая ожидающая получает `eta_seconds=0` (или время до `starts_at`), следующие — сумму полных слотов команд впереди.
- Нет текущей, очередь пуста: `eta.items=[]`, `eta.current=null`, ответ200.
- Есть текущая, очередь пуста: `eta.items=[]`, `eta.current` заполнен; виден остаток текущего слота.
- Нет текущей, есть только отложенные без позиции: `eta.items=[]`; они не задерживают очередь.

## Отложенная без позиции, возврат, restart, finish, no_show и перестановка

Отложенная без нового места не входит в `eta.items` и не задерживает остальных. Возврат через `place`/`next` снова даёт ей позицию (состояние может остаться `postponed` до `restart`), пересчитывает позиции и ETA, увеличивает `queue_revision`. Если отложенная была возвращена в очередь и затем продолжена через `restart`, её позиция снимается, команда становится текущей, а ETA остальных считается от её полного слота.

| Действие | Что меняется в ETA |
|---|---|
| `finish` текущей | Текущей защиты нет; первая ожидающая получает ETA от `now` (или `starts_at`); `queue_revision` +1 |
| `no_show` ожидающей | Команда исчезает из позиций; следующие сдвигаются; `queue_revision` +1 |
| `place`/`next`/возврат | Позиции пересчитываются; ETA целевой и следующих меняется; `queue_revision` +1 |
| Перестановка | Меняется порядок и ETA; `queue_revision` +1 |
| `postpone` из очереди | Позиция освобождается; ETA следующих уменьшается; `queue_revision` +1 |
| `postpone` из выступления | Текущей защиты нет; следующая получает ETA от `now`; `queue_revision` +1 |
| `restart` | Попытка снова идёт (`speaking`/`questions`), позиция снимается; ETA остальных считается от её полного слота; `queue_revision` +1 |
| `restart` отложенной с позицией | Позиция снимается, команда становится текущей; ETA следующих пересчитывается; `queue_revision` +1 |
| `finish` отложенной | Текущей защиты нет; команда finished; ETA следующих от `now`; `queue_revision` +1 |
| Отмена/перенос | Команда исчезает из Exam или позиции; ETA пересчитывается; `queue_revision` растёт |

`no_show` допустим только для неначавшейся защиты; окно оценивания при пропуске не открывается. `finish` из отложенной попытки разрешён: команда завершается без `restart`, а ETA следующих пересчитывается от `now`.

## Настройки, редакции и слоты

- Смена настроек создаёт новую редакцию и увеличивает `settings_version`. Ожидающие, которые ещё не начинали защиту, получают полные слоты из новой редакции; текущая защита и отложенная попытка с позицией сохраняют редакцию своей попытки. `queue_revision` при этом не меняется.
- Смена `transition_minutes` — это тоже новая редакция настроек: она меняет полные слоты ожидающих, которые ещё не начинали защиту, но не текущую защиту и не `queue_revision`.
- Индивидуальный слот (`exam_slot`) — план. Его смена не меняет ETA и `queue_revision`; меняются только `planned_start_at`/`planned_end_at` в `items`.
- Отдельных разовых перерывов (например, обед) в контракте нет. «Перерыв» в ETA — это `transition_minutes` после команды, уже входящий в полный слот; таблицы, API, статуса или lifecycle-сущности перерыва нет.

## Контракт для #109: WebSocket реализован

`GET .../queue` остаётся полным HTTP-снимком и входит в live-снимок #109 целиком (см. [инструкцию WebSocket](exam-live.md)):

- при подключении и reconnect #109 отправляет полный `QueueRead` плюс метаданные окон; окна добавляет #109, а не #110;
- live-снимок несёт `stream_seq` #109, `queue_revision`, `settings_version` и версии Attempt; `questions`/`pause`/`resume`, смена слота и настроек двигают `stream_seq`, даже когда `queue_revision` не растёт;
- `QueueMutationRead` #108 не является event-payload; #109 использует свой конверт `snapshot` и не меняет ответы мутаций;
- ETA считает только сервер; клиент использует `server_now`/`eta_at`, а не собственные часы, и не пересчитывает формулу;
- `eta_stale`/`certainty` входят в live-снимок; `stale=true` — явный признак потери актуальности, после которого клиент делает `resync`;
- #110 не меняет `queue_revision`; #109 добавляет `exam.stream_seq` и `pg_notify`, но не меняет расчёт ETA.

## Ошибки

401 — нет входа; 403 — известный Exam без права; 404 — чужой, скрытый или несуществующий объект; 422 — неверный path или query. 409 у чтения нет. Существующие коды ошибок #108 не подменяются.

## Хранение и проверки

Миграция не добавляется: ETA считается при чтении и не хранится. Новых таблиц, колонок, статусов и полей очереди нет; используются существующие Exam, записи, попытки и редакции настроек. Голова миграций остаётся `d108a10b20c7`.

```sh
pytest tests/unit/test_exam_eta.py tests/unit/test_exam_queue_api.py tests/unit/test_exam_queue_schema.py --no-cov
REGISTRATION_TEST_DATABASE_URL=... pytest tests/integration/test_exam_eta_db.py tests/integration/test_exam_queue_db.py tests/integration/test_exam_attempts_db.py --no-cov
ruff check src/ tests/
ruff format --check src/ tests/
pytest --no-cov
```

`REGISTRATION_TEST_DATABASE_URL` — PostgreSQL с CREATE DATABASE; fixture создаёт случайную БД и удаляет только её. Без переменной PG-тесты skip. CI проверяет PostgreSQL18; локально возможен14.17.

## Границы

#110 добавляет только расчёт ETA и аддитивные поля чтения очереди. WebSocket, подписки, reconnect и доставка событий реализованы в #109 (`exam-live.md`). Форма, листы, черновик и допуск — #111; аудитория и исключения — #104/#106. Пересдачи и вторая попытка, отмена или перенос начатой защиты, статистическая или ML-модель и клиентский UI сюда не входят.

`transition_minutes` — единственный «перерыв» между командами; отдельных разовых перерывов, отдельной таблицы, API или статуса перерыва и изменения lifecycle Exam нет. Слот остаётся планом: ETA может быть раньше или позже `planned_start_at`, жёсткое ограничение старта по слоту не вводится.
