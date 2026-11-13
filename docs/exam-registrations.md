# Запись команды на экзамен

Exam относится к workspace. Магистрант-manager — руководитель своей команды: для самостоятельной записи он должен быть текущим автором проекта и участником workspace с эффективной ролью manager. Явная локальная роль имеет приоритет над общей ролью аккаунта; при локальной NULL используется общая. Member не выбирает дату/слот за команду. Произвольная подпись роли участника проекта полномочий не даёт.

Все операции требуют Bearer token. База примеров: `/v1/workspaces/7/exams/12`.

## Режимы и доступные слоты

Если у Exam нет слотов, команда записывается на экзамен целиком с `slot_id:null`; вместимость не ограничивается вымышленным числом. Если слоты есть, нужно выбрать его свободный слот. Один слот вмещает одну активную запись, интервалы `[starts_at,ends_at)` не пересекаются; соседние интервалы допустимы.

```http
GET /v1/workspaces/7/exams/12/slots?limit=50&offset=0
```

Ответ200: `items,limit,offset,has_more`. Каждый слот: `id,workspace_id,exam_id,starts_at,ends_at,is_available`. Данных занявшей его команды здесь нет; доступность — на момент чтения, место занимает только успешная запись.

Teacher/admin с организационными правами Exam добавляет явные интервалы, пакет1–100:

```http
POST /v1/workspaces/7/exams/12/slots
Content-Type: application/json

{"slots":[{"starts_at":"2026-11-30T10:00:00Z","ends_at":"2026-11-30T10:15:00Z"},{"starts_at":"2026-11-30T10:15:00Z","ends_at":"2026-11-30T10:30:00Z"}]}
```

Ответ201 — массив новых слотов. Весь пакет сохраняется либо откатывается. Времена требуют timezone, ответ UTC; начало слота не раньше starts_at Exam. Слоты не вычисляются из7/7/1 и не сдвигаются при изменении длительностей. Изменение starts_at draft Exam, которое оставило бы слот раньше экзамена, отклоняется409 slot_schedule_conflict.

Добавлять можно до планового начала Exam, в draft или published. Первый пакет допустим только до первой в истории регистрации этого Exam: даже отменённая запись без слотов не превращается незаметно в слотовую. В уже слотовый Exam можно добавить места. Изменения/удаления слотов API нет. Draft скрыт от manager/member, включая слоты.

## Самостоятельная запись

```http
POST /v1/workspaces/7/exams/12/registrations/self
Content-Type: application/json

{"project_id":42,"slot_id":5}
```

Для Exam без слотов поле можно опустить или передать null. Ответ201 — регистрация (позиция в очереди назначается при создании; см. [очередь](exam-queue.md)):

```json
{"id":91,"workspace_id":7,"exam_id":12,"project_id":42,"project_type_id_at_registration":8,"slot_id":5,"queue_position":1,"queue_hold":null,"status":"active","version":1,"created_source":"manager","created_by":17,"created_at":"2026-11-20T10:00:00Z","updated_by":17,"updated_at":"2026-11-20T10:00:00Z","started_at":null}
```

Проверяются свой проект/роль, общий workspace, выбранный в Exam тип проекта, published, открытый период и слот. Самостоятельные create/cancel/move разрешены от `max(published_at,registration_opens_at)` включительно до `min(starts_at,registration_closes_at)` исключительно; при null используются published_at/starts_at. Проверка периода и запись выполняются в одной транзакции существующим `ExamService.require_self_registration_open`.

У проекта **одна active запись вообще**, включая другие экзамены и даты. Повторный POST не создаёт дубль и возвращает409 `project_already_registered`. Для другого Exam нужна отмена или перенос. Совпадающие конкурентные запросы имеют одного победителя; слот/проект защищены также partial unique индексами БД.

## Прочитать свои записи и историю

```http
GET /v1/workspaces/7/exams/12/registrations/self?project_id=42&status=active
GET /v1/workspaces/7/exams/12/registrations/91/history
```

Списки: limit50 по умолчанию (1–100), offset0; `items,limit,offset,has_more`. Статус фильтра: active/cancelled/moved. Свои регистрации отсортированы created_at,id; события — version. Без фильтра status остаются видны отменённые/перенесённые строки. Текущий автор проекта сохраняет чтение после cutoff/потери роли manager при сохранённом доступе к workspace. Чужой manager не видит эту историю; scoped teacher/admin может читать её как организатор.

Событие содержит action/source/actor_id/occurred_at/reason, old/new slot ids, `from_position/to_position` для queue-действий, nullable related_registration_id/transfer_id и версию. Действия #108: `postponed`, `returned`, `no_show`, `queue_changed` (источник organizer). `created_source/created_by` регистрации не меняются при последующих действиях; конкретное действие видно в событиях. Сведения в истории не являются чужими листами/баллами оценивания.

## Отмена и перенос

```http
POST /v1/workspaces/7/exams/12/registrations/91/self-cancel
Content-Type: application/json

{"expected_version":1,"reason":"Выбрали другую дату"}
```

Ответ200: status cancelled/version2. Место освобождается, строка/история остаются. Новая запись после отмены получает новый id. Повтор отмены —409 inactive или stale version; она не создаёт второе событие.

```http
POST /v1/workspaces/7/exams/12/registrations/91/self-move
Content-Type: application/json

{"expected_version":1,"target_exam_id":13,"target_slot_id":9,"reason":"Согласован другой экзамен"}
```

Ответ200: `{source:RegistrationRead,target:RegistrationRead}`. При переносе между Exam исходная строка становится moved, новая target —active/version1 с новым id. Парные moved_out/moved_in события связаны общим transfer_id и встречными registration ids. Оба Exam одного workspace, для manager у обоих открыт период и тип проекта допустим. Ошибка назначения сохраняет прежнее место и всю исходную запись.

При смене слота внутри того же Exam id остаётся прежним; source и target в ответе содержат одну итоговую строку. Актуальный запрос на тот же слот — no-op без новой версии/события/updated_at. Устаревший expected_version всё равно409. Reason обязательна, trim1–1000.

Автор/источник/статус/время не принимаются от клиента; лишние поля422. Целочисленные id/version положительны и не больше2147483647; boolean/string вместо body ID отклоняются. Offset ограничен0…2147483647. NUL в причине отклоняется422 до обращения к БД.

## Назначение организатором

Teacher/admin с правами Exam управляет любой командой его workspace. Права совпадают с Exam: globaladmin — все workspace; globalteacher — автор/участник пространства; localteacher/admin — своё пространство. Авторство workspace без teacher/admin и globalteacher без доступа запись не дают. Manager/member не получают организационные операции.

- POST `.../exams/{exam_id}/registrations` — `{project_id,slot_id:null}`, ответ201 RegistrationRead.
- GET той же базы — все регистрации Exam, optional project_id/status и обычная пагинация.
- POST `.../registrations/{id}/cancel` — `{expected_version,reason}`, ответ200 RegistrationRead.
- POST `.../registrations/{id}/move` — `{expected_version,target_exam_id,target_slot_id:null,reason}`, ответ200 `{source,target}`.

Общие правила workspace/type/published/slot/одной active записи/версии/истории те же, что у manager. **Исключение периода:** организатор может назначать, отменять и переносить после закрытия записи и планового starts_at, пока защита команды фактически не началась. При переносе ему не нужно открытие периодов обоих Exam. Это явное серверное правило; клиентский override/source/actor не принимаются. Будущие статусы завершённого/отменённого Exam потребуют дополнительных guards при их появлении; сейчас Exam имеет draft/published.

Каждое организационное событие имеет source=organizer и actor_id текущего пользователя. Исходные created_source/created_by прежней регистрации сохраняются. В частности, manager-запись после организационного переноса остаётся manager-источником в старой moved строке; новая active строка создана организатором. Организационный перенос после начала защиты запрещён тем же permanent marker.

## Начало защиты и изменение проекта

Регистрация не создаёт попытку, таймер или окно оценивания, но при создании получает место в очереди (`queue_position`) и при откладывании/неявке — удержание (`queue_hold`). С #107 постоянный started_at выставляет старт попытки: после фактического начала обычные cancel/move запрещены409, включая завершённую защиту. Техническое откладывание, неявка, возврат и перестановка — отдельные сценарии #108, не перенос начатой записи; HTTP — в [инструкции очереди](exam-queue.md).

При active/started регистрации существующий Project CRUD запрещает менять workspace/type409 `project_registration_locked`. Название/описание и обычная смена автора не переписывают историю; право manager проверяется по текущему автору. После отмены всех не начатых записей смена типа/workspace снова возможна. Проект с любой историей регистраций удалять нельзя409 `project_has_registrations`.

Внутренний `ExamRegistrationService.claim_for_attempt(workspace_id,exam_id,registration_id,expected_version=...,actor=...,started_at=server_time)` проверяет права организатора, published, активность/версию и текущий тип проекта. В общем UoW блокирует Exam→Project→Registration→Slot, устанавливает started_at, увеличивает version, добавляет defense_started и возвращает frozen binding с registration_id/workspace_id/exam_id/project_id/project_type_id/started_at(UTC). Время передаёт доверенный серверный вызывающий код, не HTTP-клиент. Naïve/UTC overflow и неверная версия не принимаются.

#107 (реализовано) создаёт реальную Attempt с FK registration_id и соответствующими exam/project/workspace **в той же транзакции**. Ошибка вставки/commit попытки откатывает marker и событие. Повторный claim конфликтует; идемпотентность старта обеспечивает #107 через чтение уже созданной Attempt. Marker не очищается после завершения. Завершение защиты вызывает `prepare_assessment_window` и сохраняет окно в том же UoW; регистрация/claim окон не открывают. Подробности и маршруты — [инструкция попытки](exam-attempts.md).

Слоты — плановое время. Изменение записи само по себе не переставляет живую очередь и не меняет длительность/версии настроек Exam. Вопросы по-прежнему принадлежат существующему ProjectType workspace, без версий рубрик и снимков вопросов.

## Ошибки и транзакции

401 — требуется вход;403 — недостаточная роль;404 — чужой/скрытый/несуществующий scoped объект;422 — неверное тело/path/query. Конфликт409: `detail:{code,message}`.

- `registration_closed`: период самостоятельных действий закрыт.
- `project_already_registered`: у проекта уже есть active запись.
- `project_type_not_allowed`: текущий тип проекта отсутствует в выбранных типах Exam или не задан.
- `slot_required` / `slot_unavailable`: нужен слот / место занято.
- `slot_schedule_conflict` / `slot_overlap` / `slot_before_exam` / `slot_schedule_closed` / `slot_schedule_locked`: конфликт настройки слотов.
- `registration_version_conflict` / `registration_not_active`: устаревшая команда / запись уже отменена или перенесена.
- `defense_already_started`: начатую/завершённую защиту нельзя менять этим API.
- `project_registration_locked` / `project_has_registrations`: ограничение изменения/удаления проекта.

Успех HTTP возвращается после commit. Неизвестная/отложенная ошибка БД возвращает500 и откатывает регистрацию, события, позиции очереди и освобождение исходного места. Порядок locks: Exam ids ASC → Project → Registration → Slot ids ASC; часы сервера проверяются после ожидания блокировок. Для queue-операций порядок: Exam → регистрации Exam (ORDER BY id) → Attempt; все они сериализуются блокировкой Exam. Не повторять POST вслепую после неопределённого сетевого результата: сначала перечитать свои записи/версию.

## Хранение и проверка

Миграция d102a10b20c5 от d101a10b20c4 добавляет exam_slot/exam_registration/registration_event. Downgrade теряет новые записи/историю, сохраняя вопросы и Exam прежних задач; выполнять обратные циклы только в собственной disposable DB.

```sh
pytest tests/unit/test_exam_registration_schema.py tests/unit/test_exam_registration_api.py --no-cov
REGISTRATION_TEST_DATABASE_URL=... pytest tests/integration/test_exam_registrations_db.py tests/integration/test_exam_organizer_db.py --no-cov
ruff check src/ tests/
ruff format --check src/ tests/
pytest --no-cov
```

REGISTRATION_TEST_DATABASE_URL — PostgreSQL с CREATE DATABASE. Fixture создаёт случайную registration_test_<uuid> и удаляет только её; без URL тесты явно skip. Проверки lifecycle попытки и окна — `tests/integration/test_exam_attempts_db.py` (#107); оценок и общий записанный мини-экзамен — следующие задачи, отдельно от тестов регистрации.


Проверки прав используют текущую глобальную роль из БД после ожидания блокировок;
объект пользователя из аутентификации не служит снимком полномочий для записи.
При редактировании профиля фактическую смену `role_id` разрешает только действующий
глобальный admin. Передача неизменного текущего `role_id` вместе с личными полями
допустима; устаревшее значение не восстанавливает отозванную роль.
