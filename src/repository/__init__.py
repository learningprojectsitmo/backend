from __future__ import annotations

from src.repository.education_repository import EducationRepository
from src.repository.kanban_repository import KanbanColumnRepository, KanbanSubtaskRepository, KanbanTaskRepository
from src.repository.language_repository import LanguageRepository
from src.repository.portfolio_repository import PortfolioRepository
from src.repository.project_repository import ProjectRepository
from src.repository.resume_repository import ResumeRepository
from src.repository.user_repository import UserRepository

__all__ = [
    "EducationRepository",
    "KanbanColumnRepository",
    "KanbanSubtaskRepository",
    "KanbanTaskRepository",
    "LanguageRepository",
    "PortfolioRepository",
    "ProjectRepository",
    "ResumeRepository",
    "UserRepository",
]
