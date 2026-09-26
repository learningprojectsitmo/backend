# Архив предрелизных миграций (до baseline)

Здесь лежат 15 дельт, которые накапливались в разработке до 26.09.2026. В
схему продакшена они **не входят**.

## Почему они вне `versions/`

Ни одна из этих миграций не создаёт базовые таблицы — все 49 таблиц
создавались `Base.metadata.create_all` на старте приложения. Первая миграция
цепочки (`a1b2c3d4e5f6`) — это `ALTER TABLE workspace_participation`, а этой
таблицы в пустой базе не существует. То есть цепочка не умеет поднять базу с
нуля и была пригодна только как дельты поверх схемы, нарисованной `create_all`.

На момент перехода продакшен ещё не разворачивался, поэтому вместо того
чтобы чинить такую историю, она заменена на один честный **baseline**
(`../versions/*.py`), который создаёт всю схему целиком и применяется
`alembic upgrade head` на пустой базе.

## Что здесь лежит

| Ревизия | Содержание |
|---|---|
| `a1b2c3d4e5f6` | `role_id` в `workspace_participation` |
| `b2c3d4e5f6a7` | `theme` в `project` |
| `c3d4e5f6a7b8` | `default_project_deadline` в `space_settings` |
| `d4e5f6a7b8c9` | `workspace_id` в `project_type` + уникальный ключ |
| `e5f6a7b8c9d0` | `duration_days` в `project_stage` |
| `f0a1b2c3d4e5` | enum `notification_type_enum`: `stage_approval_required` |
| `f1a2b3c4d5e6` | enum `notification_type_enum`: `response_confirmed` |
| `a7b8c9d0e1f2` | `visible_to_participants` в `project_stage` |
| `b1c2d3e4f5a6` | `require_project_type_on_create` в `space_settings` |
| `074a657a4dde` | таблица `project_specification` + `kind` в `project_stage` |
| `c2d3e4f5a6b7` | таблица `project_specification_comment` |
| `c7d8e9f0a1b2` | реструктуризация полей specification, drop `deadline` |
| `d0e1f2a3b4c5` | enum `notification_type_enum`: kanban-события |
| `e1f2a3b4c5d6` | `project_id` + индексы в `audit_logs` |
| `f2a3b4c5d6e7` | `resume.is_default` + backfill + `uq_resume_author_default` |

Всё это уже учтено в baseline. Возвращать файлы в `versions/` не нужно: Alembic
их не видит, и на dev-базу они не повлияют.

## Если всё-таки понадобится откат

Откат цепочки на dev возможен только до удаления архива — с текущим baseline
`alembic downgrade` опустится в пустоту. Dev-база, созданная из baseline,
проще пересоздать заново, чем откатывать.
