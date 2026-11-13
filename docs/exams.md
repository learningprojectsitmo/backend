# Exam: экзамены пространства

Экзамен относится к workspace и содержит название, дату/время, описание, ссылку подключения, выбранные существующие типы проектов и настройки. Можно создать несколько независимых экзаменов. Источник вопросов — ProjectType этого workspace, без rubric_version, assessment_kind или копирования текстов в Exam.

## Создать и опубликовать

Все операции требуют Bearer token. База маршрутов: `/v1/workspaces/{workspace_id}/exams`.

```http
POST /v1/workspaces/7/exams
Content-Type: application/json

{"title":"Защита проектов","starts_at":"2026-11-30T07:00:00Z","project_type_ids":[42]}
```

Ответ201: `id`, `workspace_id`, `status:"draft"`, `current_settings_version:1`, `configuration`, `created_by/created_at`, nullable `published_by/published_at`.

Defaults: teacher/manager/member60/30/10, max_score `"25.00"`, выступление7 / вопросы7 / переход1 / оценивание3 минуты. Дата требует timezone; ответ UTC. В draft можно готовить пустой список типов. Для публикации каждому выбранному типу нужен непустой список вопросов с полной шкалой1–5; N не ограничено пятью.

```http
POST /v1/workspaces/7/exams/12/publish
Content-Type: application/json

{"expected_version":1}
```

Ответ200. Повторная публикация актуальной редакции сохраняет исходные published_at/published_by. Статус клиентом не задаётся. В этой поставке есть только draft/published; старт, пауза, завершение, отмена и удаление здесь отсутствуют.

## Прочитать

- GET базы: список `items,limit,offset,has_more`, defaults limit50/offset0, limit1…100; порядок starts_at,id. Необязательный status=draft/published.
- GET `/{exam_id}`: текущая конфигурация.
- GET `/{exam_id}/settings`: история version ASC, та же пагинация, только организатор.
- GET `/{exam_id}/settings/{version}`: конкретная редакция, только организатор.

Global admin может управлять всеми workspace. Global teacher должен быть автором/участником; local teacher/admin — своего пространства. Manager/member/NULL-role участник читают опубликованные экзамены; draft скрыт по id и в списке. Авторство пространства без teacher/admin не даёт запись. Чужой workspace/Exam/type недоступен. Чужие листы и оценки эти операции не предоставляют.

## Изменить конфигурацию

PUT `/{exam_id}/settings` принимает expected_version, непустую reason и **полную** configuration из GET, включая nullable поля. Например, увеличить окно до5:

```json
{"expected_version":1,"reason":"Больше времени на оценивание","configuration":{"title":"Защита проектов","description":null,"starts_at":"2026-11-30T07:00:00Z","connection_url":null,"project_type_ids":[42],"registration_opens_at":null,"registration_closes_at":null,"weights":{"teacher":60,"manager":30,"member":10},"max_score":"25.00","presentation_minutes":7,"questions_minutes":7,"transition_minutes":1,"assessment_window_minutes":5}}
```

Ответ200 с новой current_settings_version. Старые редакции сохраняются; актуальный no-op не создаёт новую. Stale expected_version →409, включая повтор прежнего PUT после успешного изменения. Веса — целые0…100, сумма100; max_score положительный Decimal ≤2 знаков, JSON number/string; в ответе строка. Boolean/NaN/Infinity не допускаются. Длительности: выступление/окно1…1440, вопросы/переход0…1440 минут. Ноль отключает соответствующую фазу.

После публикации starts_at, project_type_ids, registration_opens_at/closes_at менять нельзя: нужен отдельный будущий сценарий переноса с учётом регистраций. Остальное меняется новой редакцией с причиной. Title1…200, description null либо1…5000, connection_url null либо http/https≤2048, reason1…1000; строки trim. Типы только своего workspace, без повторов; системный тип с NULL workspace не принимается. При наличии registration timestamps: opens<closes≤starts_at, каждое≤starts_at.

## Интеграция записи и окна

`ExamService.require_self_registration_open(workspace_id, exam_id, user, now=server_time)` проверяет доступ, published и период от max(published_at,opens) до min(starts_at,closes), правая граница исключена. #102 должна вызвать его в одной транзакции с созданием регистрации, а также проверить manager/проект/тип/слот/уникальность. Сам guard не выполняет эти проверки.

`prepare_assessment_window(workspace_id, exam_id, project_type_id, expected_version=..., opened_at=server_time)` — внутренний доверенный вызов, без HTTP и самостоятельного commit. Проверяет опубликованный Exam, текущую редакцию, выбранный тип/готовность вопросов; блокирует весь список этого типа навсегда и возвращает frozen exam_id/workspace_id/project_type_id/settings_version/opened_at/closes_at.

#107/#111 должны проверить права ведущего, состояние попытки и связь проекта с типом, затем создать окно **в том же UoW**, сохранив возвращённые времена/редакцию. Ошибка вставки окна откатывает новый lock. Пример: v1, открытие10:00, окно3 →10:03. Изменение v2 до5 не меняет этот срок; новое открытие10:02 по v2 →10:07. Начатая фаза таймера аналогично должна сохранять свои метки в #107.

После первого окна PUT вопросов, очистка, добавление, перестановка, изменение объяснений и apply-template для этого типа отвергаются409. Для другого списка нужен другой тип. Это общая постоянная блокировка типа, включая другие Exam; снятия блокировки API нет. Тип, упомянутый в любой редакции Exam или marker блокировки, удалять нельзя. Операции сериализуются parent row locks; успешный HTTP-ответ даётся после commit.

## Ошибки

401 — нет входа; 403 — запись/история запрещена в видимом Exam; 404 — отсутствующий/чужой/скрытый объект; 422 — неверное тело/path/query; 409 — конфликт состояния. Detail409 содержит code/message:

- settings_version_conflict;
- questions_not_ready;
- published_schedule_locked;
- exam_not_published / registration_closed (внутренний guard);
- questions_locked (изменение списка вопросов);
- project_type_in_use (старый CRUD типа).

Неожиданная ошибка БД возвращает500, без ложного успешного сохранения.

## Хранение, проверки и границы

Миграция d101a10b20c4 от d100a10b20c3 добавляет exam, exam_settings_revision, exam_settings_project_type, project_type_question_lock и UNIQUE(id,workspace_id) типа. FK изолируют workspace и current revision; вопросные данные #134 не меняются. Downgrade теряет новые Exam/историю/lock, сохраняя старые типы/проекты/вопросы; применять обратный цикл только в собственной disposable DB.

```sh
pytest tests/unit/test_exam_schema.py tests/unit/test_exam_api.py --no-cov
EXAM_TEST_DATABASE_URL=... pytest tests/integration/test_exams_db.py --no-cov
ruff check src/ tests/
ruff format --check src/ tests/
pytest --no-cov
```

EXAM_TEST_DATABASE_URL указывает на тестовый PostgreSQL с CREATE DATABASE: fixture создаёт случайную exam_test_<uuid> и удаляет только её. Без переменной DB-тесты skip. CI проверяет PostgreSQL18; локально возможен14.17.

Реальные регистрации/слоты/очередь/окна/аудитория/листы/расчёт/итоги/CSV/UI здесь не реализованы. Счётчики проектов и оценщиков не возвращаются. #113 должна согласовать формулу для произвольного N и явно пересчитывать предварительный результат по новой редакции весов/максимума; #114 — сохранять принятый итог до нового решения. Создание редакции настроек само по себе не пересчитывает результат. Общая сквозная приёмка и человеческое ревью учитываются отдельно.
