from __future__ import annotations

from src.model.app_setting import AppSetting
from src.model.audit import AuditLog
from src.model.auth import NewUser, PasswordReset, Session
from src.model.education import Education
from src.model.exam import Exam, ExamSettingsProjectType, ExamSettingsRevision
from src.model.exam_attempt import AssessmentWindow, AttemptEvent, ExamAttempt
from src.model.exam_registration import ExamRegistration, ExamSlot, RegistrationEvent
from src.model.ideas import Idea, IdeaComment, IdeaTag, IdeaVote
from src.model.kanban_models import Column, Subtask, Task, TaskAssignee, TaskHistory
from src.model.language import Language
from src.model.notification import Notification, NotificationType
from src.model.portfolio import Portfolio
from src.model.project import Project, ProjectParticipation, ProjectStatus, ProjectVacancy, Response, Tag
from src.model.project_type_question import ProjectTypeQuestion, ProjectTypeQuestionLevel, ProjectTypeQuestionLock
from src.model.resume import (
    Resume,
    ResumeEducation,
    ResumeExperience,
    ResumeInterest,
    ResumeLanguage,
    ResumeLink,
    ResumeSkill,
    ResumeWorkspace,
)
from src.model.settings import SettingsType, SpaceSettings
from src.model.user import Permission, Role, RolePermission, User, UserPermission
from src.model.wiki import WikiPage
from src.model.workspace import WorkSpace, WorkSpaceCategories, WorkSpaceParticipation, WorkSpaceStatus
from src.model.workspace_invitation import WorkspaceInvitation

__all__ = [
    "AppSetting",
    "AssessmentWindow",
    "AttemptEvent",
    "AuditLog",
    "Column",
    "Education",
    "Exam",
    "ExamAttempt",
    "ExamRegistration",
    "ExamSettingsProjectType",
    "ExamSettingsRevision",
    "ExamSlot",
    "Idea",
    "IdeaComment",
    "IdeaTag",
    "IdeaVote",
    "Language",
    "NewUser",
    "Notification",
    "NotificationType",
    "PasswordReset",
    "Permission",
    "Portfolio",
    "Project",
    "ProjectParticipation",
    "ProjectStatus",
    "ProjectTypeQuestion",
    "ProjectTypeQuestionLevel",
    "ProjectTypeQuestionLock",
    "ProjectVacancy",
    "RegistrationEvent",
    "Response",
    "Resume",
    "ResumeEducation",
    "ResumeExperience",
    "ResumeInterest",
    "ResumeLanguage",
    "ResumeLink",
    "ResumeSkill",
    "ResumeWorkspace",
    "Role",
    "RolePermission",
    "Session",
    "SettingsType",
    "SpaceSettings",
    "Subtask",
    "Tag",
    "Task",
    "TaskAssignee",
    "TaskHistory",
    "User",
    "UserPermission",
    "WikiPage",
    "WorkSpace",
    "WorkSpaceCategories",
    "WorkSpaceParticipation",
    "WorkSpaceStatus",
    "WorkspaceInvitation",
]
