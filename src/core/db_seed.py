from __future__ import annotations

import logging

from sqlalchemy import insert, select

from src.model.project import ProjectStatus


def seed_project_statuses(connection) -> None:
    logger = logging.getLogger(__name__)
    logger.info("=== SEED: Starting project_status seeding ===")
    print("=== SEED: Starting project_status seeding ===")  # временно для отладки

    result = connection.execute(select(ProjectStatus.name))
    existing = {row[0] for row in result}
    logger.info(f"Existing statuses: {existing}")
    print(f"Existing: {existing}")

    statuses = [
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
