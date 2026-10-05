"""add unique participation constraints

Revision ID: a4e7b2f91c35
Revises: 9c7d1e2f3a45
Create Date: 2026-10-05 13:05:00.000000

Уникальность на (project_id, participant_id) в `project_participation` и на
(workspace_id, participant_id) в `workspace_participation`.

Причина: пара (проект, участник) могла встречаться в таблице многократно.
На проде так накопились четыре строки участия одного человека в проекте — из-за
того, что «подтвердить участие» можно было нажать несколько раз, а `add_participant`
делал голый INSERT без upsert. Список участников проекта строится напрямую по
строкам участия, поэтому человек показывался дважды, `participants_count`
завышался, а `scalar_one_or_none` в проверках участия падал в 500.

Индексы переименованы, а не добавлены вторым: на тех же парах колонок уже есть
неуникальные `ix_pp_project_participant` / `ix_wp_workspace_participant` из
`c52423977558`. Новый уникальный индекс строится первым, старый удаляется вторым,
чтобы таблица ни на секунду не осталась без индекса.

CONCURRENTLY + autocommit_block: обычный `CREATE UNIQUE INDEX` берёт на таблицу
`ACCESS EXCLUSIVE` и блокирует приложение на всё время построения.

ПОРЯДОК ПРИМЕНЕНИЯ. `CREATE UNIQUE INDEX CONCURRENTLY` падает, если в таблице
есть дубликаты. Перед этой миграцией их надо удалить, оставив по одной строке на
пару (в проде — `DELETE` лишних строк участия; входящих FK на
`project_participation.id` нет). Если миграция упала на этом, она оставит
невалидный индекс — `DROP INDEX CONCURRENTLY` его и повторите после чистки.

.downgrade симметричен upgrade.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4e7b2f91c35"
down_revision: str | Sequence[str] | None = "9c7d1e2f3a45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    Уникальный индекс создаётся первым, старый неуникальный удаляется вторым:
    так таблица ни на секунду не остаётся без индекса. Отдельный
    autocommit_block на каждую операцию — PostgreSQL не разрешает
    ``CREATE INDEX CONCURRENTLY`` и ``DROP INDEX CONCURRENTLY`` внутри
    транзакции, а два CONCURRENTLY в одной транзакции нельзя выполнить в
    принципе.
    """
    with op.get_context().autocommit_block():
        op.create_index(
            "uq_pp_project_participant",
            "project_participation",
            ["project_id", "participant_id"],
            unique=True,
            postgresql_concurrently=True,
        )
    with op.get_context().autocommit_block():
        op.drop_index("ix_pp_project_participant", table_name="project_participation", postgresql_concurrently=True)

    with op.get_context().autocommit_block():
        op.create_index(
            "uq_wp_workspace_participant",
            "workspace_participation",
            ["workspace_id", "participant_id"],
            unique=True,
            postgresql_concurrently=True,
        )
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_wp_workspace_participant",
            table_name="workspace_participation",
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    """Downgrade schema.

    Возвращает неуникальные индексы из `c52423977558`, к которым приведены модели.
    """
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_pp_project_participant",
            "project_participation",
            ["project_id", "participant_id"],
            unique=False,
            postgresql_concurrently=True,
        )
    with op.get_context().autocommit_block():
        op.drop_index("uq_pp_project_participant", table_name="project_participation", postgresql_concurrently=True)

    with op.get_context().autocommit_block():
        op.create_index(
            "ix_wp_workspace_participant",
            "workspace_participation",
            ["workspace_id", "participant_id"],
            unique=False,
            postgresql_concurrently=True,
        )
    with op.get_context().autocommit_block():
        op.drop_index(
            "uq_wp_workspace_participant",
            table_name="workspace_participation",
            postgresql_concurrently=True,
        )