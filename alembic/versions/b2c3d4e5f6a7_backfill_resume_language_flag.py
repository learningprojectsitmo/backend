"""backfill resume_language.flag

Revision ID: b2c3d4e5f6a7
Revises: d1c2b3a4f5e6
Create Date: 2026-10-21 21:00:00.000000

Данные, а не схема: заполняем ``resume_language.flag`` у резюме, созданных
ДО миграции ``f7a8b9c0d1e2`` (она добавила колонку с ``server_default '🌐'``).
Без этого бэкфилла в существующих резюме вместо флага языка везде стоял бы
глобус, а блок «Языки» в резюме расходился с блоком на странице профиля.

Флаг берётся из профильного языка (``language.flag``) — при создании резюме
именно так и копируется (``resume_service`` → ``ResumeLanguage(flag=item.flag)``).
История этих копий не сохранилась, поэтому восстанавливаем флаг приближённо,
в два шага:

1. Точное совпадение по имени языка В ПРОФИЛЕ ТОГО ЖЕ АВТОРА
   (``lower(name)``, при нескольких строках — самая свежая, глобус
   проигрывает). Это достоверные данные: флаг стоял в профиле автора.
2. Если у автора такого языка в профиле нет или там стоял глобус — берём
   самый частый НЕ-глобусный флаг для этого имени среди всех профилей
   (``language`` по всей базе). Это эвристика: «Английский» у разных
   авторов помечен и 🇬🇧, и 🇺🇸, и выбирается самый массовый вариант.
   Строки, для которых неглобусного флага нет вовсе, остаются с '🌐'.

UPDATE трогает только строки с флагом '🌐', поэтому вручную проставленные
флаги (и те, что проставлены при создании резюме после ``f7a8b9c0d1e2``)
не перезаписываются — миграция идемпотентна.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "d1c2b3a4f5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Шаг 1: флаг из профиля того же автора.
    op.execute(
        sa.text(
            """
            UPDATE resume_language rl
            SET flag = src.flag
            FROM (
                SELECT DISTINCT ON (l.user_id, lower(l.name))
                       l.user_id AS user_id,
                       lower(l.name) AS name_key,
                       l.flag AS flag
                FROM language l
                ORDER BY l.user_id, lower(l.name), (l.flag = '🌐') ASC, l.updated_at DESC NULLS LAST, l.id DESC
            ) src
            WHERE lower(rl.name) = src.name_key
              AND rl.flag = '🌐'
              AND src.flag <> '🌐'
              AND EXISTS (
                  SELECT 1
                  FROM resume r
                  WHERE r.id = rl.resume_id
                    AND r.author_id = src.user_id
              )
            """
        )
    )

    # Шаг 2: самый частый неглобусный флаг для имени языка по всем профилям.
    op.execute(
        sa.text(
            """
            WITH per_name AS (
                SELECT lower(l.name) AS name_key,
                       (array_agg(l.flag ORDER BY (l.flag = '🌐') ASC, l.cnt DESC, l.flag))[1] AS flag
                FROM (
                    SELECT lower(name) AS name, flag, count(*) AS cnt
                    FROM language
                    GROUP BY 1, 2
                ) l
                GROUP BY 1
            )
            UPDATE resume_language rl
            SET flag = per_name.flag
            FROM per_name
            WHERE lower(rl.name) = per_name.name_key
              AND rl.flag = '🌐'
              AND per_name.flag <> '🌐'
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Возврат к состоянию сразу после f7a8b9c0d1e2: у всех строк флаг '🌐'.
    op.execute(
        sa.text(
            """
            UPDATE resume_language
            SET flag = '🌐'
            WHERE flag <> '🌐'
            """
        )
    )
