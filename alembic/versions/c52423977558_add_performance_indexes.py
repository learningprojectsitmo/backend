"""add performance indexes

Revision ID: c52423977558
Revises: 7c1d4e9a2b30
Create Date: 2026-09-27 14:25:01.219827

Индексы подтверждённые запросами, а не «на каждый FK»: на момент правки в
моделях было 23 индекса на 50 таблиц, и три самых дорогих места шли без них —
поиск пользователя по `lower(email)` на каждом авторизованном запросе,
подтаблицы резюме (ноль индексов на `resume_id` при `selectinload` с
сортировкой) и `resume.author_id`, чей единственный индекс был partial и не
покрывал `WHERE author_id = $1`.

Порядок колонок в составных индексах: сначала равенства, потом сортировка.
Все индексы продублированы в `__table_args__` моделей — иначе autogenerate
считает их посторонними и предлагает удалить (проверяется `alembic check`).

Обычный `CREATE INDEX`, не CONCURRENTLY: миграция остаётся атомарной, а
.downgrade симметричен upgrade.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c52423977558"
down_revision: str | Sequence[str] | None = "7c1d4e9a2b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # ─── Аутентификация ──────────────────────────────────────────────────────
    # `UserRepository.get_by_email` фильтрует `func.lower(email)`, поэтому
    # btree на самой колонке не используется — нужен expression-индекс.
    op.create_index("ix_user_lower_email", "user", [sa.literal_column("lower(email)")], unique=False)
    op.create_index("ix_newuser_lower_email", "newuser", [sa.literal_column("lower(email)")], unique=False)
    op.create_index("ix_session_user_active", "session", ["user_id", "is_active"], unique=False)

    # ─── Канбан-доска ────────────────────────────────────────────────────────
    op.create_index("ix_column_project_position", "column", ["project_id", "position"], unique=False)
    op.create_index("ix_task_column_position", "task", ["column_id", "position"], unique=False)
    op.create_index("ix_task_project_column_position", "task", ["project_id", "column_id", "position"], unique=False)
    op.create_index("ix_subtask_task_position", "subtask", ["task_id", "position"], unique=False)
    op.create_index("ix_task_assignee_user", "task_assignee", ["user_id"], unique=False)
    op.create_index(
        "ix_task_history_task_created", "task_history", ["task_id", sa.literal_column("created_at DESC")], unique=False
    )

    # ─── Проекты, workspace, права ────────────────────────────────────────────
    op.create_index(
        "ix_pp_project_participant", "project_participation", ["project_id", "participant_id"], unique=False
    )
    op.create_index("ix_pp_participant", "project_participation", ["participant_id"], unique=False)
    op.create_index(
        "ix_wp_workspace_participant", "workspace_participation", ["workspace_id", "participant_id"], unique=False
    )
    op.create_index("ix_wp_participant", "workspace_participation", ["participant_id"], unique=False)
    op.create_index("ix_project_workspace_id", "project", ["workspace_id", "id"], unique=False)
    op.create_index("ix_workspace_author_id", "workspace", ["author_id"], unique=False)
    op.create_index("ix_project_vacancy_project", "project_vacancy", ["project_id"], unique=False)
    op.create_index("ix_project_stage_type_order", "project_stage", ["project_type_id", "order"], unique=False)
    op.create_index(
        "ix_spec_comment_spec_created",
        "project_specification_comment",
        ["specification_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_response_respondent_project_status", "response", ["respondent_id", "project_id", "status"], unique=False
    )
    op.create_index("ix_response_respondent_type", "response", ["respondent_id", "type"], unique=False)
    op.create_index(
        "ix_stage_transition_project_created",
        "stage_transition",
        ["project_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index("ix_role_permission_role_permission", "role_permission", ["role_id", "permission_id"], unique=False)
    op.create_index("ix_user_permission_user_permission", "user_permission", ["user_id", "permission_id"], unique=False)
    op.create_index(
        "ix_ws_invitation_workspace_active_created",
        "workspace_invitation",
        ["workspace_id", "is_active", "created_at"],
        unique=False,
    )

    # ─── Резюме ──────────────────────────────────────────────────────────────
    # Частичный `uq_resume_author_default` видит только строки с is_default,
    # поэтому обычные выборки по автору он не обслуживает.
    op.create_index("ix_resume_author_id", "resume", ["author_id", "id"], unique=False)
    for table in (
        "resume_education",
        "resume_experience",
        "resume_interest",
        "resume_language",
        "resume_link",
        "resume_skill",
    ):
        op.create_index(f"ix_{table}_resume_order", table, ["resume_id", "sort_order"], unique=False)

    # ─── Лента активности и уведомления ──────────────────────────────────────
    op.create_index(
        "ix_audit_logs_project_performed",
        "audit_logs",
        ["project_id", sa.literal_column("performed_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_audit_logs_user_performed",
        "audit_logs",
        ["performed_by", sa.literal_column("performed_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_notification_user_created", "notification", ["user_id", sa.literal_column("created_at DESC")], unique=False
    )
    # ix_notification_user_id из baseline оставлен намеренно: он строгий
    # префикс нового ix_notification_user_created и на notification его можно
    # было бы убрать, но baseline в своём downgrade() дропает этот индекс
    # раньше таблицы и не переживает, если его уже нет. Удаление сломало бы
    # шаг `downgrade base` в CI-гейте миграций.
    op.create_index(
        "ix_notification_user_unread", "notification", ["user_id"], unique=False, postgresql_where=sa.text("NOT read")
    )

    # ─── Вики и идеи ─────────────────────────────────────────────────────────
    op.create_index(
        "ix_wiki_page_project_parent_position", "wiki_page", ["project_id", "parent_id", "position"], unique=False
    )
    op.create_index("ix_idea_comment_idea_created", "idea_comment", ["idea_id", "created_at"], unique=False)
    op.create_index("ix_idea_vote_idea_user", "idea_vote", ["idea_id", "user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_idea_vote_idea_user", table_name="idea_vote")
    op.drop_index("ix_idea_comment_idea_created", table_name="idea_comment")
    op.drop_index("ix_wiki_page_project_parent_position", table_name="wiki_page")

    # ix_notification_user_unread — partial, поэтому predicate не указываем:
    # для DROP он и не нужен, а передача postgresql_where здесь лишняя.
    op.drop_index("ix_notification_user_unread", table_name="notification")
    op.drop_index("ix_notification_user_created", table_name="notification")
    op.drop_index("ix_audit_logs_user_performed", table_name="audit_logs")
    op.drop_index("ix_audit_logs_project_performed", table_name="audit_logs")

    for table in (
        "resume_education",
        "resume_experience",
        "resume_interest",
        "resume_language",
        "resume_link",
        "resume_skill",
    ):
        op.drop_index(f"ix_{table}_resume_order", table_name=table)
    op.drop_index("ix_resume_author_id", table_name="resume")

    op.drop_index("ix_ws_invitation_workspace_active_created", table_name="workspace_invitation")
    op.drop_index("ix_user_permission_user_permission", table_name="user_permission")
    op.drop_index("ix_role_permission_role_permission", table_name="role_permission")
    op.drop_index("ix_stage_transition_project_created", table_name="stage_transition")
    op.drop_index("ix_response_respondent_type", table_name="response")
    op.drop_index("ix_response_respondent_project_status", table_name="response")
    op.drop_index("ix_spec_comment_spec_created", table_name="project_specification_comment")
    op.drop_index("ix_project_stage_type_order", table_name="project_stage")
    op.drop_index("ix_project_vacancy_project", table_name="project_vacancy")
    op.drop_index("ix_workspace_author_id", table_name="workspace")
    op.drop_index("ix_project_workspace_id", table_name="project")
    op.drop_index("ix_wp_participant", table_name="workspace_participation")
    op.drop_index("ix_wp_workspace_participant", table_name="workspace_participation")
    op.drop_index("ix_pp_participant", table_name="project_participation")
    op.drop_index("ix_pp_project_participant", table_name="project_participation")

    op.drop_index("ix_task_history_task_created", table_name="task_history")
    op.drop_index("ix_task_assignee_user", table_name="task_assignee")
    op.drop_index("ix_task_project_column_position", table_name="task")
    op.drop_index("ix_task_column_position", table_name="task")
    op.drop_index("ix_subtask_task_position", table_name="subtask")
    op.drop_index("ix_column_project_position", table_name="column")

    op.drop_index("ix_session_user_active", table_name="session")
    op.drop_index("ix_newuser_lower_email", table_name="newuser")
    op.drop_index("ix_user_lower_email", table_name="user")
