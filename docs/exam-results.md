# Принятие, ручной итог и публикация версии итога (#114, #116)

Итог привязан к **попытке защиты** (`exam_attempt.id`). Преподаватель (teacher) или администратор принимает расчётный итог либо задаёт ручной (#116); принятое решение хранится как **редакция** (версия 1, 2, 3…) и не меняется ни от новых голосов, ни от смены весов или максимума. Любое новое решение — новая редакция, старая остаётся.

Все операции (`GET`, `GET /editions`, `POST /accept`, `POST /manual`, `POST /publish`) требуют аутентификации и **эффективной роли teacher/admin именно этого пространства** — проверка `ProjectRelationsService.is_workspace_teacher(user_id, workspace_id=...)` ([project-relations.md](project-relations.md)); решение согласовано с Фёдором 17.11. Привязки «ответственного teacher» к команде нет (решение 16.11): принять итог может любой teacher/admin пространства. Эндпоинтов для студентов нет — видимость итога студентам остаётся открытым вопросом Q5.

Правила роли (реализованы в `is_workspace_teacher`, здесь не дублируются):

- участие в пространстве обязательно: global admin, не состоящий в пространстве, **не проходит** (как и автор пространства без записи участия);
- локальная роль участия приоритетнее глобальной: локальный member с глобальной ролью teacher/admin **не проходит**;
- если локальная роль не задана (NULL), берётся глобальная (teacher/admin — проходит);
- локальный teacher/admin проходит независимо от глобальной роли.

Порядок проверок: (1) пространство и Exam видны пользователю (`ExamService.require_read_access`) — иначе 404; (2) роль `is_workspace_teacher` — иначе 403; (3) попытка принадлежит этому Exam — иначе 404; (4) состояние — 409. В `accept`, `manual` и `publish` роль проверяется ещё раз после взятия блокировки Exam: если за время ожидания роль отозвали, запись не создаётся (403).

Коды ответов:

- 404 — чужое/несуществующее пространство, Exam или попытка; пользователь, который вообще не видит пространство (не участник и не автор, не global admin), и скрытый черновик Exam для не-организатора;
- 403 — Exam виден, но нет эффективной роли teacher/admin пространства; сюда относятся global admin вне пространства, автор без участия, local member с глобальной ролью teacher, обычный участник, manager;
- 409 с `detail: {code, message}` — конфликт состояния; 422 — неверное тело или путь.

## Маршруты

Основа: `/v1/workspaces/{workspace_id}/exams/{exam_id}/attempts/{attempt_id}/result`.

| Метод | Путь | Что делает |
|---|---|---|
| `GET` | `` | Текущая принятая редакция + `preliminary` + `outdated` |
| `GET` | `/editions` | Все редакции попытки по возрастанию версии |
| `POST` | `/accept` | Принять новую редакцию (первую или следующую) |
| `POST` | `/manual` | Ручной итог: новая редакция `kind='manual'` |
| `POST` | `/publish` | Опубликовать текущую редакцию (любого вида) |

### `POST /accept`

```json
{"expected_version": 0}
```

`expected_version` — номер последней редакции, которую видел клиент (`0`, если принятых нет). Для `expected_version >= 1` обязателен `reason` (1…1000 символов после trim, без NUL). Другие поля (в том числе балл или роль) не принимаются: расчёт всегда на сервере.

Правила:

1. Попытка завершена (`status='finished'`), иначе 409 `attempt_not_finished`; окно оценивания существует (`assessment_window_missing`) и `closes_at <= now` по серверным часам, иначе 409 `assessment_window_open`.
2. `expected_version` совпадает с номером последней редакции, иначе 409 `result_version_conflict` (так же при гонке двух одновременных принятий — запись получится ровно одна).
3. Расчёт: листы берутся из `ExamSheetSource`; веса и `max_score` — из **текущей** редакции настроек Exam; `sheet_max = 5 × N`, где `N` — число вопросов типа проекта попытки (после первого окна список заблокирован); дальше `calculate_exam_score` ([exam-score.md](exam-score.md)).
4. Нет учитываемых оценок («нет расчёта») — 409 `no_calculation`; для такого случая есть ручной итог (`POST /manual`). Малое число ответов и пустая группа принятие не блокируют.
5. Сохраняется редакция `kind='calculated'`: `calculated_score = final_score`, снимок параметров, `decided_by`, `decided_at` (серверное время).

Другие 409: `questions_missing` (у типа проекта нет вопросов), `invalid_sheet_data` (источник отдал лист, который не проходит проверку расчёта, например сумма больше `sheet_max`), `assessment_window_missing` / `audience_snapshot_unavailable` (источник листов не нашёл окно или снимок аудитории, см. ниже).

### `POST /manual` (#116)

Ручной (официальный) итог ответственного teacher/admin пространства. Это такая же редакция, как у `accept`, только `kind='manual'`, а `final_score` задаёт преподаватель.

```json
{"expected_version": 0, "final_score": "17.50", "reason": "Учтена устная защита"}
```

- `final_score` — число или строка, `>= 0`, не более 2 знаков после запятой, не более 12 значащих цифр, без NaN/Infinity и `true/false`; значение сохраняется как передано (`17.5` → `17.50`), **автоматического округления до целого нет** — округление на совести ответственного;
- `reason` — обязательна **всегда**, в том числе для версии 1 (1…1000 символов после trim, без NUL);
- `expected_version` — как у `accept` (`0`, если редакций ещё нет); другие поля (`kind`, `calculated_score`, веса, `max_score`) не принимаются (422).

Правила:

1. Условия как у `accept`: попытка завершена, окно оценивания существует и закрыто по серверным часам — иначе 409 `attempt_not_finished` / `assessment_window_missing` / `assessment_window_open`.
2. `expected_version` равен номеру последней редакции, иначе 409 `result_version_conflict` (так же при гонке по `UNIQUE(attempt_id, version)`: запись одна). Новая версия — текущая + 1; предыдущие редакции не меняются.
3. Диапазон: `0 <= final_score <= max_score` из **текущей** редакции настроек Exam (границы включительно); нарушение — **422** `detail: {"code": "final_score_out_of_range", "message": ..., "max_score": "25.00"}`, запись не создаётся.
4. Сохраняется: `kind='manual'`, `final_score` — введённое; `calculated_score` — свежий расчёт на этот момент или `NULL`, если «нет расчёта» (основной сценарий ручного итога: в этом случае он проходит, в отличие от `accept`); полный снимок параметров как у `accept` (веса, `max_score`, `sheet_max`, `settings_version`, число листов по ролям, `used_weight`); `reason`, `decided_by`, `decided_at`. Исходные листы не читаются на запись и не меняются.
5. Источник листов и расчёт работают как у `accept`: если источник бросил 409 (`assessment_window_missing`, `audience_snapshot_unavailable`, `sheet_source_not_configured`) или лист не проходит проверку (`invalid_sheet_data`), ручной итог тоже получает 409 — ошибки не глотаются. Также 409 `questions_missing`.
6. Права: member/manager и любой без эффективной роли teacher/admin этого пространства — 403, чужое/скрытое — 404 (те же правила, что выше).

`accept` после ручной редакции допустим и создаёт следующую версию `calculated` (с обязательной `reason`); ручной итог после принятого — следующая версия `manual`. `POST /publish` публикует последнюю редакцию любого вида.

Пример ответа (`ResultRead`, как у `accept`), нет расчёта:

```json
{
  "workspace_id": 7, "exam_id": 12, "attempt_id": 31,
  "edition": {
    "id": 1, "workspace_id": 7, "exam_id": 12, "attempt_id": 31,
    "version": 1, "kind": "manual",
    "calculated_score": null, "final_score": "13.50",
    "snapshot": {"settings_version": 1, "weights": {"teacher": 60, "manager": 30, "member": 10},
                 "max_score": "25.00", "sheet_max": 25,
                 "sheets": {"teacher": 0, "manager": 0, "member": 0}, "used_weight": 0},
    "reason": "Никто не оценивал", "decided_by": 5, "decided_at": "2026-11-30T07:13:00Z",
    "published_at": null, "published_by": null
  },
  "preliminary": {"score": null, "no_calculation": true, "snapshot": {"...": "..."}, "roles": ["..."]},
  "outdated": false
}
```

`outdated` для ручной редакции: сравнивается снимок параметров (веса, `max_score`, `settings_version`, `sheet_max`, число листов, `used_weight`) и `calculated_score` со свежим расчётом; **ручной `final_score` с расчётом не сравнивается** — это решение преподавателя, а не расчёт. Поэтому ручной итог при «нет расчёта» остаётся `outdated = false`, пока голосов по-прежнему нет, и становится `true`, когда появились учитываемые листы или изменились настройки. Логика `outdated` не менялась.

### `POST /publish`

```json
{"expected_version": 1}
```

Публикует **последнюю** редакцию (`calculated` или `manual`): ставит `published_at`/`published_by`. Если `expected_version` не равен номеру последней — 409 `result_version_conflict`; если принятых нет — 409 `result_not_accepted`. Повторная публикация идемпотентна и сохраняет исходные `published_at`/`published_by`. Публиковать устаревшую (`outdated`) редакцию можно: флаг виден в ответе. Новая принятая редакция публикуется отдельным вызовом; предыдущая публикация не отзывается и не копируется.

### Ответ `GET` / `accept` / `publish`

```json
{
  "workspace_id": 7, "exam_id": 12, "attempt_id": 31,
  "edition": {
    "id": 1, "workspace_id": 7, "exam_id": 12, "attempt_id": 31,
    "version": 1, "kind": "calculated",
    "calculated_score": "19.00", "final_score": "19.00",
    "snapshot": {
      "settings_version": 1,
      "weights": {"teacher": 60, "manager": 30, "member": 10},
      "max_score": "25.00", "sheet_max": 25,
      "sheets": {"teacher": 1, "manager": 1, "member": 1},
      "used_weight": 100
    },
    "reason": null, "decided_by": 5, "decided_at": "2026-11-30T07:13:00Z",
    "published_at": null, "published_by": null
  },
  "preliminary": {
    "score": "19.00", "no_calculation": false,
    "snapshot": {"...": "тот же вид, по текущим листам и настройкам"},
    "roles": [{"role": "teacher", "weight": 60, "sheets_count": 1, "average": "20.00", "counted": true}]
  },
  "outdated": false
}
```

- `edition` — сохранённая редакция (`null`, если принятых нет). Баллы — строки с двумя знаками.
- `preliminary` — свежий расчёт по текущим листам и текущим настройкам; считается на лету и **не сохраняется**; `null`, пока попытка не завершена. При отсутствии учитываемых оценок `score = null`, `no_calculation = true`.
- `outdated = true`, если снимок принятой редакции (веса, `max_score`, `settings_version`, `sheet_max`, число листов по ролям, `used_weight`) или балл отличается от `preliminary`. Для нового решения клиент вызывает `accept` с `expected_version` = текущая версия и `reason`.

### `GET /editions`

`{"items": [<edition>, ...]}`, по возрастанию `version`. Реестр по всему экзамену — раздел «Реестр результатов по экзамену» ниже.

## Реестр результатов по экзамену (#115)

`GET /v1/workspaces/{workspace_id}/exams/{exam_id}/results` — список итогов **по всему экзамену** с поиском по команде и фильтром по состоянию решения. История одной попытки по-прежнему отдаётся `GET .../attempts/{attempt_id}/result/editions` (этот эндпоинт не менялся); реестр её не дублирует, а показывает текущую редакцию, число редакций и предыдущий итог.

Права — те же, что у остальных операций результата (`require_read_access` → 404, затем `is_workspace_teacher` → 403). Member, manager и global admin вне пространства реестр не видят.

### Query

| Параметр | По умолчанию | Смысл |
|---|---|---|
| `q` | — | Подстрока в названии проекта (`project.name`), без учёта регистра, до 200 символов; пробелы по краям обрезаются, пустая строка = без фильтра. `%`, `_` и `\` ищутся как обычные символы (экранируются) |
| `state` | — | `undecided` — решения ещё нет; `accepted` — есть редакция, текущая не опубликована; `published` — текущая редакция опубликована |
| `limit` | 50 | 1…100 |
| `offset` | 0 | ≥ 0 |

Неверные значения (`limit` вне 1…100, `offset < 0`, неизвестный `state`, `q` длиннее 200, id пути < 1) → 422.

### Что входит в строку

Одна строка на **завершённую** попытку экзамена (`status='finished'` и есть окно оценивания): только по таким попыткам возможно решение. Попытки без редакций присутствуют со `state='undecided'`. Незавершённые и отложенные попытки и регистрации без попытки в реестр **не входят** — их полные состояния относятся к ведомости (#121). Порядок строгий: `attempt.started_at`, затем `attempt.id`. Ответ без `total`: `{items, limit, offset, has_more}`.

Поля строки: `attempt_id`, `registration_id`, `project_id`, `project_name`, `project_type_id`, `finished_at`, `state`, `editions_count`, `previous_final_score` (итог предыдущей версии; `null` для версии 1 и без решения), `settings_outdated`, `current` (`null` при `undecided`, иначе: `version`, `kind`, `calculated_score` (может быть `null`), `final_score`, `max_score`, `reason` (может быть `null`), `decided_by_id`, `decided_by_name` (`имя фамилия`, без висящих пробелов, если фамилии нет), `decided_at`, `published_at`, `published_by_id`). Баллы — строки с двумя знаками (`"19.00"`).

### `settings_outdated`, а не `outdated`

`settings_outdated = true`, если текущая редакция **настроек экзамена** отличается от снимка принятой редакции: другой `settings_version`, веса или `max_score`. Считается одним SQL по настройкам, без чтения листов; для `undecided` всегда `false`. Это дешёвый признак «настройки менялись после решения». Точный `outdated` (с учётом новых голосов: пересчёт по листам и сравнение с баллом) остаётся только в детальном `GET .../result`: в реестр его не включили, потому что он требует пересчёта по листам для каждой строки страницы.

### Пример

```
GET /v1/workspaces/7/exams/12/results?q=алго&state=accepted&limit=2
```

```json
{
  "items": [
    {
      "attempt_id": 31, "registration_id": 18, "project_id": 9, "project_name": "Алгоритмы маршрутизации",
      "project_type_id": 3, "finished_at": "2026-11-30T07:00:00Z", "state": "accepted", "editions_count": 2,
      "previous_final_score": "19.00", "settings_outdated": false,
      "current": {
        "version": 2, "kind": "manual", "calculated_score": "19.00", "final_score": "20.50", "max_score": "25.00",
        "reason": "Устная защита", "decided_by_id": 5, "decided_by_name": "Анна Петрова",
        "decided_at": "2026-11-30T07:20:00Z", "published_at": null, "published_by_id": null
      }
    }
  ],
  "limit": 2, "offset": 0, "has_more": false
}
```

### Репозиторный метод (для переиспользования в #121)

`ExamResultRepository.list_results(workspace_id, exam_id, *, q=None, state=None, limit, offset) -> list[ExamResultRegistryRow]` (`src/repository/exam_result_repository.py`). Возвращает frozen-dataclass `ExamResultRegistryRow` (поля как у строки реестра; `state` — свойство) с вложенным `ExamResultRegistryCurrent`; HTTP-схем не касается. Метод отдаёт до `limit + 1` строк, чтобы вызывающий вычислил `has_more`; для выгрузки целиком можно вызывать страницами.

Один SQL без N+1: редакции ранжируются один раз подзапросом с оконными функциями (`row_number() ... ORDER BY version DESC` — текущая редакция, `lag(final_score)` — предыдущий итог, `count(*)` — число редакций по попытке), попытки соединяются с окном оценивания, проектом, текущей редакцией настроек экзамена и автором решения. Изоляция по `workspace_id` и `exam_id` — в подзапросе и в основном запросе. Новых индексов и миграций не потребовалось: выборка идёт по `exam_id` (индекс `ix_attempt_exam_finished`, уникальный индекс `(attempt_id, version)`).

Примечание: регистронезависимость `ILIKE` для кириллицы зависит от локали БД (в UTF-8-кластерах с `en_US.UTF-8`, как в CI и docker-compose, работает).

## Хранение

Таблица `exam_result_edition` (миграция `d114a10b20c9`, модель `src/model/exam_result.py`):

- `UNIQUE(attempt_id, version)`; составной FK `(attempt_id, exam_id, workspace_id)` на `exam_attempt` (изоляция workspace/Exam) и `(exam_id, settings_version)` на редакцию настроек;
- `kind IN ('calculated','manual')`; для `calculated` — `calculated_score IS NOT NULL AND final_score = calculated_score`; для `manual` `calculated_score` может быть `NULL`, `final_score` задаёт преподаватель, а `reason` обязательна и непуста (`ck_result_edition_manual_reason`, миграция `d116a10b20c9`);
- `0 <= final_score <= max_score`, веса целые и в сумме 100, `sheet_max > 0`, `reason` не пустой, обязателен при `version >= 2`;
- снимок параметров расчёта лежит в колонках самой редакции: веса ролей, `max_score`, `sheet_max`, `settings_version`, число листов по ролям, `used_weight`.

Append-only: строка не перезаписывается и не удаляется (FK `RESTRICT`). Единственная допустимая «мутация» — разовая отметка публикации `published_at/published_by` у самой редакции (колонки, а не отдельная таблица: публикация одного состояния редакции, ровно один раз, парный CHECK `(published_at IS NULL) = (published_by IS NULL)`). Отдельная таблица публикаций понадобилась бы только при отзыве публикации — он не нужен.

Блокировки: Exam → Attempt (`FOR UPDATE`) → строки редакций; чтение последней редакции происходит под блокировкой попытки, поэтому двойное принятие и двойная публикация сериализуются. Регистрации не затрагиваются и не блокируются. Сервис сам не делает commit: ответ уходит после commit UoW.

WebSocket (#109): `mark_exam_changed` для принятия, ручного итога и публикации **не вызывается** — в `ExamLiveChange` нет подходящего типа (`queue|attempt|settings|window|exam`), контракт live-канала не расширялся.

## Источник листов `ExamSheetSource`

`src/services/exam_sheet_source.py`. Граница между расчётом и хранением листов (#111/#112):

```python
class ExamSheetSource(Protocol):
    async def load_submitted_sheets(self, *, attempt_id: int) -> Sequence[SheetScore]: ...
```

Контракт реализации:

- только **отправленные** листы; без черновиков и без листов исключённых оценщиков;
- по одной записи на оценщика — последняя допустимая редакция его листа;
- `SheetScore.role` берётся из снимка аудитории, зафиксированного при открытии окна, а не от клиента; `SheetScore.total` — сумма баллов критериев листа (каждый 1…5);
- работает в UoW вызывающего (та же сессия, без собственного commit);
- пустой список означает «никто не оценил» — если данные недоступны, нужно падать, а не возвращать пустой список.

Реальная реализация — `SubmittedSheetSource` (#112), подключена в `get_exam_sheet_source` (`src/core/container.py`):
берёт окно попытки и строки `assessment_window_audience` с `admitted = TRUE`, для каждого оценщика — последнюю
отправленную редакцию листа (`exam_assessment_submission`, см. [exam-assessment.md](exam-assessment.md)); роль — только
из снимка аудитории, сумма — сумма баллов редакции. Нет окна или снимка аудитории → 409 `assessment_window_missing` /
`audience_snapshot_unavailable` (не пустой список). `UnconfiguredExamSheetSource` остаётся тестовой заглушкой
(409 `sheet_source_not_configured`), по умолчанию не подключается. `GET .../editions` от источника не зависит.

## Что не входит

- хранение листов, черновики, отправка и серверный дедлайн — #111/#112 (сделано, см. [exam-assessment.md](exam-assessment.md));
- аудитория и допуск оценщиков — #104/#106;
- полные состояния всех команд (незавершённые попытки, регистрации без попытки) — ведомость #121;
- видимость итога студентам и вес admin-оценщика — Q5;
- CSV-выгрузки — #121/#122.
