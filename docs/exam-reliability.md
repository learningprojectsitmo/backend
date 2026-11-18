# Надёжность экзамена: конкуренция, reconnect, ресурсы, CSV-снимки (#118)

Что проверено под нагрузкой и как это воспроизвести, найденные дефекты и что остаётся за командой. Относится к AC-05
(таймер и ETA: reload/reconnect, пауза, пропуск и возврат, чужой workspace) и AC-09 (ведомость и участие из одного
снимка, баллы и версии согласованы). Контракты существующих эндпоинтов не менялись; миграций нет.

## Что и чем проверяется

| Приёмка #118 | Тест | Что доказывает |
|---|---|---|
| Нет частичного успеха и потери отложенных команд | `test_exam_reliability_db.py`: `test_ac05_concurrent_commands_keep_every_team_and_count_one_event_each`, `test_failed_sheet_submit_*`, `test_failed_queue_command_*`, `test_failed_registration_with_a_slot_*`, `test_failed_acceptance_*` | параллельные postpone/no-show/start не теряют команд (все команды в очереди, позиции без дыр, ровно одно live-событие на команду); сбой в середине отправки листа, команды очереди, записи со слотом и принятия итога откатывает всю мутацию (триггер БД бросает исключение после первой вставки), повторная операция работает без «дыр» в версиях |
| AC-05: единое состояние и прогноз | `test_ac05_pause_postpone_return_and_reload_give_one_state_and_forecast`, `test_ac05_foreign_workspace_and_outsiders_*` | после каждой мутации снимок WebSocket (`ExamLiveService`) и `GET .../queue` на один момент идентичны (включая ETA); на паузе `remaining_seconds`/`phase_deadline` заморожены при любом reload; resume сдвигает дедлайн ровно на паузу; `stream_seq` растёт на 1 за мутацию; чужой workspace и посторонний — `NotFoundError` по обоим каналам |
| Нагрузка ~150 подключений | `test_exam_live_load_ws.py::test_consistent_load_with_mutations_and_mass_reconnect` | 150 клиентов одного Exam + 30 второго, два реальных процесса uvicorn с общей PostgreSQL; мутации очереди идут во время подключения; все получили последний `stream_seq`, нет закрытий 4408/4429/1011, чужой Exam не получает чужих данных (id/workspace каждого снимка), массовый одновременный reconnect: снимок каждого клиента = `GET .../queue` (без полей, зависящих от момента чтения) |
| Нагрузка по HTTP + пул | `test_exam_live_load_ws.py::test_burst_of_submits_with_parallel_websocket_keeps_the_pool_bounded_and_the_export_consistent` | 120 оценщиков одновременно (форма → черновик → отправка) при 75 подключённых WS-клиентах: все ответы 200, ровно одна редакция на оценщика, пик соединений с БД не выше расчётного предела пула, ZIP-выгрузка по HTTP согласована с данными |
| Снимок не растёт с числом клиентов | `test_exam_reliability_db.py::test_hub_builds_one_snapshot_per_exam_and_not_per_client` | число SQL-запросов на рассылку одного изменения одинаково для 3 и 150 подписчиков; подключение клиента стоит одно и то же независимо от числа уже подключённых |
| AC-09: CSV-снимок консистентен | `test_ac09_many_assessors_around_the_close_then_accept_and_csv_match_registry_and_participation`, `test_ac09_export_taken_while_assessors_keep_submitting_is_always_one_consistent_snapshot` | 40+ оценщиков отправляют одновременно, 10 пересдают в последнюю секунду окна, 5 опоздавших получают 409 `assessment_window_closed` и не оставляют следов; принятие итога; обе CSV совпадают с реестром (`list_results`, #115) и участием (`list_participation`, #117) по версии итога, баллам, версии настроек, числам допущенных/ответивших/исключённых и по каждому оценщику; балл пересчитывается из строк самого CSV. Второй тест делает 8 выгрузок при непрерывных пересдачах: в каждой паре `calculated_score` = пересчёт из её же листов, один `export_id`/`snapshot_at` |

Запуск (нужен одноразовый PostgreSQL с правом `CREATE DATABASE`, см. `CLAUDE.md`):

```bash
export EXAM_TEST_DATABASE_URL=postgresql+asyncpg://postgres@localhost:55432/postgres
export QUESTION_TEST_DATABASE_URL=$EXAM_TEST_DATABASE_URL REGISTRATION_TEST_DATABASE_URL=$EXAM_TEST_DATABASE_URL
uv run python -m pytest tests/integration/test_exam_reliability_db.py --no-cov
uv run python -m pytest tests/integration/test_exam_live_load_ws.py --no-cov -s   # 150 клиентов, 120 оценщиков
EXAM_LOAD_CLIENTS=40 EXAM_LOAD_ASSESSORS=40 uv run python -m pytest tests/integration/test_exam_live_load_ws.py --no-cov  # как в CI
```

`-s` печатает строки `EXAM_LOAD_REPORT` и `EXAM_BURST_REPORT` с измеренными числами. CI (job `migrations`) гоняет те же
файлы с `EXAM_LOAD_CLIENTS=40`, `EXAM_LOAD_ASSESSORS=40`.

## Цифры (macOS, PostgreSQL 17 с `max_connections=100`, два процесса uvicorn, 2026-11-18)

| Сценарий | Результат |
|---|---|
| 150+30 WS-клиентов подключаются одновременно во время мутаций очереди | все получили финальный `stream_seq`, подключение 0,6–0,8 с, ни одного закрытия с ошибкой |
| массовый reconnect 180 клиентов | 0,5 с, у всех `reason="reconnect"`, `stale=false`, снимок = HTTP |
| 120 оценщиков (360 HTTP-запросов) одновременно + 75 WS | 1,1 с, все 200, одна редакция на оценщика |
| пик соединений с БД | 42 на два процесса = предел пула (`2 × (10 + 10 + 1)`) |

Это синтетическая нагрузка на одном компьютере (клиенты — asyncio-websockets, не браузеры), а не замер production.

## Найденные дефекты и правки

### 1. Запрос к exam-эндпоинту держит два соединения пула (исправлено)

`get_current_user` берёт `get_uow` (область «запрос»: соединение держится до конца запроса), а exam-репозитории
берут `Depends(get_uow, scope="function")` — второй `SqlAlchemyUoW`. Получается два соединения на запрос. Когда число
одновременных запросов на процесс достигает размера пула, каждый держит первое соединение и ждёт второе: взаимная
блокировка пула до `pool_timeout` (30 с) и массовые 500 (`QueuePool limit ... connection timed out`). Воспроизведение:
`DB_POOL_SIZE=1 DB_MAX_OVERFLOW=0` — первый же `GET .../queue` падал 500; при пуле 10+10 из 120 одновременных оценщиков
102 получили 500 за 30 с.

Правка (`src/core/dependencies.py`): после аутентификации `get_current_user` завершает её транзакцию (`uow.commit()` —
в аутентификации только чтения), и соединение возвращается в пул до начала обработчика. Теперь запрос держит не более
одного соединения одновременно; тот же сценарий с пулом из одного соединения возвращает 200, а 120 оценщиков проходят
за 1,1 с. Побочный эффект — для остальных эндпоинтов соединение тоже не держится на время работы обработчика без
запросов. Требует внимания на ревью: правка затрагивает общую зависимость, обёрнута в `getattr` ради тестовых
заглушек UoW.

### 2. Суммарный размер пулов против `max_connections` (исправлено)

Было: `pool_size=20 + max_overflow=30` на процесс; production — `uvicorn --workers 4` (`Dockerfile.prod`), плюс по одному
LISTEN-соединению hub'а на процесс: до `4 × 51 = 204` соединений, а в compose/deploy PostgreSQL работает с
`max_connections` по умолчанию (100). Воспроизведение: два процесса и 180 WS-клиентов — часть клиентов получила close 1011
(`TooManyConnectionsError: sorry, too many clients already`).

Правка: размер пула вынесен в настройки (`src/core/config.py`, `src/core/database.py`, `.env.example`):

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `DB_POOL_SIZE` | 10 | постоянные соединения процесса |
| `DB_MAX_OVERFLOW` | 10 | временные сверх пула |
| `DB_POOL_TIMEOUT_SECONDS` | 30 | ожидание свободного соединения |

Расчёт: `workers × (DB_POOL_SIZE + DB_MAX_OVERFLOW + 1 LISTEN) + резерв ≤ max_connections − 3 (superuser_reserved)`.
По умолчанию `4 × 21 = 84 ≤ 97`; юнит-тест `tests/unit/test_db_pool.py` следит, чтобы значения по умолчанию помещались в
стандартные 100 соединений. Для локальной разработки (один процесс) ничего не меняется функционально.

**Рекомендация команде для deploy-репозитория (мы там ничего не меняли):** поднять `max_connections` минимум до 150
(`-c max_connections=150` у postgres) — запас под миграции, `psql`, pgAdmin и рост числа workers; при увеличении
`--workers` или пула пересчитать формулу выше. `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` можно задавать переменными окружения.

### 3. Тихие 1011 в WebSocket (исправлено)

`/live` закрывал соединение кодом 1011 без записи причины в лог. Добавлены `logger.exception` в двух ветках
(`src/api/v1/endpoints/exam_live.py`); контракт не менялся.

## Участие: CSV и эндпоинт считают одинаково

CSV «участие оценщиков» (`exam_csv_participation.py`) и `GET .../participation` (`ExamParticipationRepository`) строятся
на одном снимке аудитории и дают одни и те же правила: голос — последняя отправленная редакция внутри окна
`[opened_at, closes_at)`; черновик и отправка вне окна не голос; исключённый не показывает отправку; допущенный без
голоса — `not_submitted`; коды причины исключения — хранимые `manager_of_defending_team` / `member_of_defending_team`.
Источник расчёта итога (`SubmittedSheetSource`) использует то же правило окна. Проверено тестом
`test_csv_and_endpoint_participation_rules_agree` по каждому оценщику. Попытка без окна: эндпоинт — `not_offered` и пустой
список, CSV — строки-«предпросмотр» (`audience_source=preview`), это намеренно.

## Ограничения и что остаётся за командой

- Мини-экзамен E08-T03 (ручной сквозной сценарий) и ревью второго backend-разработчика (DoD #118) не проводились.
- Нагрузка снята на одной машине и без реверс-прокси; через production-домен WebSocket заработает только после правки
  nginx в deploy-репозитории: `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection $connection_upgrade;
  proxy_read_timeout 90s;` в `location /v1/` (см. `exam-live.md`).
- `max_connections` в deploy — см. рекомендацию выше.
- Ограничения hub'а по числу соединений (250 на Exam, 1000 на процесс) проверены только до 150 на Exam; два процесса
  делят нагрузку, лимит считается на процесс.
- Скорость снимка при подключении: каждое подключение строит свой снимок (аутентификация + чтение), всплеск из 150
  одновременных подключений обслуживается за <1 с, но стоит ~2 транзакции на клиента; при изменении состояния снимок
  строится один раз на Exam.
- Измерение числа транзакций через `pg_stat_database` оказалось ненадёжным (бэкенды сбрасывают статистику с задержкой
  до 10 с), поэтому «снимок не зависит от числа клиентов» проверено подсчётом SQL-запросов на уровне движка в процессе,
  а число соединений — выборкой `pg_stat_activity` каждые 100 мс.
