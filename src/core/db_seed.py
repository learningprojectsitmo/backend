from __future__ import annotations

import logging

from sqlalchemy import insert, select

from src.model.project import ProjectStage, ProjectStatus, ProjectType
from src.model.settings import SettingsType


def seed_project_statuses(connection) -> None:
    logger = logging.getLogger(__name__)
    logger.info("=== SEED: Starting project_status seeding ===")
    print("=== SEED: Starting project_status seeding ===")  # временно для отладки

    result = connection.execute(select(ProjectStatus.name))
    existing = {row[0] for row in result}
    logger.info(f"Existing statuses: {existing}")
    print(f"Existing: {existing}")

    statuses = [
        {"name": "draft", "color": "#999999"},
        {"name": "planned", "color": "#6A7282"},
        {"name": "in_progress", "color": "#2B7FFF"},
        {"name": "completed", "color": "#00C950"},
        {"name": "review", "color": "#F0B100"},
    ]

    new_statuses = [s for s in statuses if s["name"] not in existing]
    logger.info(f"Adding {len(new_statuses)} statuses: {new_statuses}")
    print(f"Adding: {new_statuses}")

    for status in new_statuses:
        connection.execute(insert(ProjectStatus).values(**status))

    logger.info("=== SEED: Finished seeding ===")
    print("=== SEED: Finished ===")


def seed_project_types(connection) -> None:
    """Заполняем справочник типов проектов с наборами этапов (идемпотентно)."""
    logger = logging.getLogger(__name__)

    result = connection.execute(select(ProjectType.name))
    existing = {row[0] for row in result}

    default_types = [
        {
            "name": "Курсовой проект",
            "description": "Диплом с этапами утверждения темы и защиты",
            "stages": [
                {"name": "Выбор темы", "requires_approval": False, "visible_to_participants": False, "kind": "general"},
                {
                    "name": "Утверждение темы",
                    "requires_approval": True,
                    "visible_to_participants": True,
                    "kind": "general",
                },
                {
                    "name": "Создание тз",
                    "requires_approval": False,
                    "visible_to_participants": True,
                    "kind": "spec_creation",
                },
                {
                    "name": "Утверждение тз",
                    "requires_approval": True,
                    "visible_to_participants": True,
                    "kind": "spec_approval",
                },
                {"name": "Реализация", "requires_approval": False, "visible_to_participants": True, "kind": "general"},
                {"name": "Предзащита", "requires_approval": True, "visible_to_participants": True, "kind": "general"},
                {"name": "Защита", "requires_approval": True, "visible_to_participants": True, "kind": "general"},
                {"name": "Завершено", "requires_approval": False, "visible_to_participants": True, "kind": "general"},
            ],
        },
    ]

    for t in default_types:
        if t["name"] in existing:
            logger.info("Project type %r already exists, skipping", t["name"])
            continue

        connection.execute(insert(ProjectType).values(name=t["name"], description=t.get("description")))

        type_row = connection.execute(select(ProjectType.id).where(ProjectType.name == t["name"])).first()
        type_id = type_row[0]

        for idx, stage in enumerate(t["stages"]):
            connection.execute(
                insert(ProjectStage).values(
                    name=stage["name"],
                    order=idx,
                    requires_approval=stage["requires_approval"],
                    visible_to_participants=stage["visible_to_participants"],
                    kind=stage.get("kind", "general"),
                    project_type_id=type_id,
                )
            )
        logger.info("Seeded project type %r with %d stages", t["name"], len(t["stages"]))

    logger.info("=== SEED: Finished project_types seeding ===")


def seed_settings_types(connection) -> None:
    logger = logging.getLogger(__name__)
    logger.info("=== SEED: Starting settings_types seeding ===")

    result = connection.execute(select(SettingsType.name))
    existing = {row[0] for row in result}

    types = [
        {"name": "space", "description": "Настройки пространства"},
    ]

    new_types = [t for t in types if t["name"] not in existing]
    for st in new_types:
        connection.execute(insert(SettingsType).values(**st))

    logger.info("=== SEED: Finished settings_types seeding ===")
