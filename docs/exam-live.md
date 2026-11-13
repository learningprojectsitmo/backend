# WebSocket экзамена: живой снимок и reconnect

Live-канал отдаёт состояние одного Exam: текущую попытку, фазу, паузу, абсолютный дедлайн, очередь, ETA и метаданные окон оценивания. Сервер не рассылает ежесекундные тики: клиент считает таймер по `server_now`/`phase_deadline`/`paused_at`, а сервер присылает полный снимок при изменении состояния и при подключении/reconnect.

HTTP-контракт `GET /v1/workspaces/{workspace_id}/exams/{exam_id}/queue` не меняется: его `QueueRead` входит в снимок целиком. События/reconnect не заменяют HTTP-чтение и не добавляют аудиторию, листы или допуск.

## Подключение

```
WS /v1/workspaces/{workspace_id}/exams/{exam_id}/live
```

- Один сокет — один Exam одного workspace.
- Браузерный WebSocket не умеет задавать `Authorization`; токен передаётся первым сообщением после `accept`, не в query string:

```json
{"type":"auth","token":"<access JWT>","last_stream_seq":41}
```

- `last_stream_seq` необязателен. Он влияет только на `reason` (`reconnect` вместо `connected`); полный снимок отправляется всегда.
- Таймаут auth — 5 секунд. Токен не пишется в URL, логи и метрики.
- `Origin`, если передан, должен входить в `CORS_ORIGINS`; отсутствие `Origin` допускается для не-браузерных клиентов.
- После auth сервер отправляет `hello`, затем полный `snapshot`.

### Доступ

| Роль | Кто | Доступ |
|---|---|---|
| `organizer` | teacher/admin workspace, global admin, подходящий global teacher | published и draft своего workspace; `can_manage=true` |
| `viewer` | участник workspace или автор, видящий published Exam | только published; `can_manage=false` |
| — | чужой workspace, неизвестный Exam, draft для viewer | close 4404 |

Состав снимка одинаков для обеих ролей: `queue` уже доступен reader'ам через HTTP. Разница — `access.can_manage` и доступ к draft. Аудитория/персональный допуск/листы здесь не реализуются (#104/#106/#111/#112).

## Сообщения

### `hello`

```json
{"type":"hello","contract_version":1,
 "access":{"role":"organizer","can_manage":true},
 "server_now":"2026-11-30T14:00:00Z"}
```

### `snapshot`

```json
{
  "type": "snapshot",
  "contract_version": 1,
  "reason": "connected",
  "stream_seq": 42,
  "server_now": "2026-11-30T14:00:00Z",
  "stale": false,
  "changed": [],
  "exam": {"id":12,"workspace_id":7,"status":"published","settings_version":3},
  "queue": {
    "queue_revision": 17,
    "server_now": "2026-11-30T14:00:00Z",
    "settings_version": 3,
    "eta_stale": false,
    "contract_version": 1,
    "items": [],
    "eta": {"current": null, "items": []}
  },
  "assessment_windows": [
    {"attempt_id":31,"registration_id":92,"project_id":51,"project_type_id":8,
     "opened_at":"2026-11-30T13:55:00Z","closes_at":"2026-11-30T13:58:00Z",
     "settings_version":2,"state":"closed"}
  ]
}
```

- `reason`: `connected`, `reconnect`, `changed`, `resync`.
- `server_now` верхнего уровня равен `queue.server_now`.
- `queue` — ровно `QueueRead` `GET .../queue`; `settings_version`, `eta_stale`, `contract_version`, `certainty`, `reason` сохраняют смысл.
- `assessment_windows` — метаданные окна, собранные из `queue.items[].attempt.assessment_window`: без состава оценщиков, допуска, `can_submit` и листов. `state` вычисляется по `server_now < closes_at`.
- `stale=true` — снимок не удалось согласовать после ретраев (`queue.eta_stale` или `stream_seq` менялся во время чтения). Данные — последний полный снимок; клиент помечает состояние устаревшим и делает `resync`/переподключение. Это не ложный успех.
- `changed` — подсказка: `queue`, `attempt`, `settings`, `window`, `exam`. При коалесценции список может быть неполным; источник истины — поля снимка.
- `contract_version` WS-конверта — 1; вложенный `queue.contract_version` — версия HTTP-снимка (#110). Версии независимы.

### `heartbeat`

Раз в 20 секунд (настраивается), не тик таймера:

```json
{"type":"heartbeat","contract_version":1,"stream_seq":42,
 "server_now":"2026-11-30T14:00:20Z","queue_revision":17,
 "settings_version":3,"stale":false}
```

Если `heartbeat.stream_seq > last_applied_stream_seq`, клиент понял, что пропустил снимок, и отправляет `resync`.

### `resync`, `ping`, `pong`

- `{"type":"resync"}` — запросить полный снимок; ответ `reason="resync"`. Не чаще одного раза в 5 секунд на соединение.
- `{"type":"ping"}` — необязательный liveness; ответ `{"type":"pong","server_now":"..."}`.
- Неизвестный `type` после auth игнорируется; битый JSON/слишком большое сообщение — close 4400/4409.

### `error`

```json
{"type":"error","code":"access_revoked","message":"Access is no longer available"}
```

Отправляется перед close; после `error` данные не идут.

## Порядок и актуальность

`exam.stream_seq` (`BIGINT`, миграция `d109a10b20c8`) — монотонный курсор потока на Exam:

- растёт на 1 за транзакцию, меняющую WS-значимое состояние, независимо от числа изменённых сущностей;
- назначается в той же транзакции, что и изменение, под блокировкой строки Exam;
- commit order = `stream_seq` order;
- один `finish` с attempt + window + queue даёт один seq, а не три.

`stream_seq` нужен потому, что `queue_revision` не меняется при `questions`/`pause`/`resume`, смене слота и `settings_version`:

| Изменение | `queue_revision` | `attempt.version` | `settings_version` | `stream_seq` |
|---|---:|---:|---:|---:|
| start | +1 | +1 | 0 | +1 |
| questions/pause/resume | 0 | +1 | 0 | +1 |
| finish | +1 | +1 | 0 | +1 |
| postpone/restart | +1 | +1 | 0 | +1 |
| place/next/no-show | +1 | 0 | 0 | +1 |
| slot change | 0 | 0 | 0 | +1 |
| settings change | 0 | 0 | +1 | +1 |

Правила:

- сервер не рассылает снимок с `stream_seq <= last_sent`; новому соединению снимок отправляется всегда;
- клиент отбрасывает снимок с `stream_seq <= last_applied`;
- пропуск промежуточного снимка не теряет состояние: следующий снимок полный; `heartbeat`/`resync` закрывают обнаруженный пропуск;
- снимок проверяет `stream_seq` до и после чтения `QueueRead`; при изменении — до 3 ретраев; после них `stale=true`.

## Публикация после commit

Любая мутация, меняющая live-состояние, вызывает `uow.mark_exam_changed`. В `SqlAlchemyUoW` перед commit выполняется:

1. `UPDATE exam SET stream_seq=stream_seq+1 ... RETURNING workspace_id, stream_seq`;
2. `SELECT pg_notify('exam_live', {workspace_id, exam_id, stream_seq, changed})`;
3. commit.

`pg_notify` транзакционен: PostgreSQL доставляет уведомление только после успешного commit. Rollback, ошибка flush/commit или исключение сервиса не двигают `stream_seq` и не публикуют уведомление. No-op повтор (та же позиция, та же пауза, тот же finish) не маркирует изменение.

`NOTIFY` не является durable event log. Потерянное уведомление компенсируется сверкой `stream_seq` раз в 10 секунд и полным снимком; история изменений остаётся в `registration_event`/`attempt_event`, а не в WebSocket.

## Доставка между workers

Production запускает `uvicorn --workers 4`; отдельного брокера (Redis/RabbitMQ/Celery) в backend нет. Поэтому:

- каждый worker имеет свой `ExamLiveHub` с одним `LISTEN exam_live` (asyncpg) и реестром подписок;
- уведомление получают все listener'ы PostgreSQL, включая процесс-публикатор;
- worker строит снимок один раз на Exam и рассылает его своим подписчикам, а не по снимку на клиента;
- уведомления коалесцируются (100 мс), поэтому всплеск `questions`/`pause`/`resume` даёт один снимок с последним `stream_seq`;
- сверка раз в 10 секунд читает `exam.stream_seq` и строит снимок при отставании, даже если `NOTIFY` потерян;
- process-local `asyncio`-рассылка не выдаётся за межпроцессную: реальный тест использует два процесса uvicorn с общей PostgreSQL.

### Production edge

Edge nginx сейчас пробрасывает `Upgrade`/`Connection` только для Grafana. Для `/v1/` нужно добавить:

```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
proxy_read_timeout 90s;
```

`map $http_upgrade $connection_upgrade` уже есть в `nginx.conf`. Без этого WebSocket через production-домен не поднимется; изменение deploy-репозитория выполняется отдельно, не в backend MR.

## Reconnect и таймер

- При подключении и каждом reconnect — `hello` + полный `snapshot`; `reason="reconnect"`, если передан `last_stream_seq`.
- Клиент не сбрасывает таймер в ноль: `phase_deadline` абсолютный, `remaining_seconds` пересчитан сервером, `server_now` — единственный источник «сейчас».
- Пауза: `paused_at` установлен, `remaining_seconds` заморожен; `resume` сдвигает `phase_deadline` на длительность паузы.
- `assessment_windows[].closes_at` абсолютный; закрытие окна не требует отдельного сообщения — клиент переключает состояние по сроку. Push в момент закрытия — #111/#112.
- `stale=true`/`eta_stale=true` — явный признак потери актуальности; `resync` возвращает полный снимок без сброса времени.

## Отзыв доступа

- При подключении доступ проверяется полностью.
- Раз в 30 секунд guard перепроверяет токен (`AuthService.get_current_user`) и чтение Exam; при потере доступа/истечении токена — `error` + close 4403/4401/4404.
- Максимальная задержка обнаружения — 30 секунд; мгновенный отзыв — #104/#106, не этот контракт.

## Буферы, лимиты и отключение

- На соединение — bounded outbound buffer: не более 2 сообщений; новый снимок заменяет ещё не отправленный старый.
- Отправка с таймаутом 5 секунд; таймаут/переполнение — `error` и close 4408.
- Лимиты: 250 соединений на Exam, 1000 на процесс; превышение — 4429.
- Входящее сообщение ≤ 4 КБ; больше — 4409.
- При disconnect подписка удаляется, задача guard отменяется, буфер очищается; listener/сверка остаются процессами-синглтонами.
- Shutdown: close 1001 всем соединениям, отмена задач, закрытие listener.

## Close-коды

| Код | Значение |
|---|---|
| 1000 | нормальное закрытие клиентом |
| 1001 | shutdown сервера |
| 1011 | внутренняя ошибка/снимок недоступен |
| 4400 | нарушение протокола/битый JSON |
| 4401 | нет auth, истёк/неверный токен |
| 4403 | запрещённый Origin/отозванный доступ |
| 4404 | чужой/скрытый/несуществующий Exam |
| 4408 | таймаут отправки/медленный клиент |
| 4409 | слишком большое входящее сообщение |
| 4429 | превышен лимит соединений |

## Проверки

```sh
pytest tests/unit/test_exam_live_snapshot.py tests/unit/test_exam_live_hub.py --no-cov
REGISTRATION_TEST_DATABASE_URL=... pytest tests/integration/test_exam_live_db.py --no-cov
REGISTRATION_TEST_DATABASE_URL=... pytest tests/integration/test_exam_live_ws.py --no-cov
ruff check src/ tests/
ruff format --check src/ tests/
```

`test_exam_live_ws.py` поднимает реальные uvicorn-процессы (два процесса с общей PostgreSQL), подключается по WebSocket и проверяет: два изолированных Exam, cross-process доставку, snapshot/reconnect, `questions`/`pause`/`resume` без роста `queue_revision`, порядок/дубли, rollback, доставку после commit, окно оценивания, отзыв доступа, Origin и лимит. PG-тесты дополнительно проверяют `LISTEN/NOTIFY`, commit/rollback и `stream_seq`.

## Границы

- #109 не добавляет аудиторию, персональный допуск, листы, черновики, отправку или серверный дедлайн листа (#104/#106/#111/#112).
- Окно — только метаданные; «окно открыто допущенным» не заявляется.
- Нет нового lifecycle Exam, автопереключения фаз, новых правил очереди и пересдач.
- Нет durable event-store и гарантии доставки каждого события; есть полный снимок и сверка.
- `GET .../queue` и ответы мутаций не меняются.
- S0 #93 в части WebSocket не согласован; маршрут/payload/лимиты — предложение #109.
