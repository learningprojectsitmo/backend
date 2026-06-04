from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, select

from src.model.project import Project, ProjectParticipation, ProjectVacancy, Response
from src.model.resume import (
    Resume,
    ResumeEducation,
    ResumeExperience,
    ResumeInterest,
    ResumeLanguage,
    ResumeLink,
    ResumeSkill,
)
from src.model.settings import SettingsType
from src.model.workspace import WorkSpace, WorkSpaceCategories, WorkSpaceParticipation, WorkSpaceStatus
from src.repository.project_repository import ProjectRepository
from src.schema.education import EducationCreate
from src.schema.kanban import TaskCreate
from src.schema.language import LanguageCreate
from src.schema.permission import PermissionMatrix
from src.schema.portfolio import PortfolioCreate
from src.schema.project import ProjectCreate, VacancyCreate
from src.schema.resume import ResumeCreate
from src.schema.settings import SpaceSettingsUpdate
from src.schema.user import UserCreate
from src.schema.workspace import WorkSpaceCreate
from src.services.education_service import EducationService
from src.services.kanban_service import KanbanService
from src.services.language_service import LanguageService
from src.services.permission_service import PermissionService
from src.services.portfolio_service import PortfolioService
from src.services.project_service import ProjectService
from src.services.resume_service import ResumeService
from src.services.role_service import RoleService
from src.services.settings_service import SpaceSettingsService
from src.services.user_service import UserService
from src.services.workspace_service import WorkSpaceService


class FixtureService:
    """Сервис для создания тестовых данных (фикстур)"""

    def __init__(
        self,
        permission_service: PermissionService,
        role_service: RoleService,
        user_service: UserService,
        workspace_service: WorkSpaceService,
        project_service: ProjectService,
        project_repository: ProjectRepository,
        settings_service: SpaceSettingsService,
        kanban_service: KanbanService,
        resume_service: ResumeService,
        portfolio_service: PortfolioService,
        education_service: EducationService,
        language_service: LanguageService,
    ) -> None:
        self._permission_service = permission_service
        self._role_service = role_service
        self._user_service = user_service
        self._workspace_service = workspace_service
        self._project_service = project_service
        self._project_repository = project_repository
        self._settings_service = settings_service
        self._kanban_service = kanban_service
        self._resume_service = resume_service
        self._portfolio_service = portfolio_service
        self._education_service = education_service
        self._language_service = language_service

    # ─── main entry ────────────────────────────────────────────────────────

    async def create_fixtures(self) -> None:
        await self._seed_permissions()
        await self._seed_roles()
        users = await self._seed_users()
        admin = users[0]
        await self._seed_workspace_statuses()
        categories_by_name = await self._seed_workspace_categories()
        workspaces_by_name = await self._seed_workspaces(admin, categories_by_name)
        await self._seed_projects(users, workspaces_by_name)
        await self._seed_responses(users, workspaces_by_name)
        await self._seed_settings_types()
        await self._seed_resumes(users)
        await self._seed_portfolio(admin)
        await self._seed_education(admin)
        await self._seed_languages(admin)

    # ─── permissions ───────────────────────────────────────────────────────

    async def _seed_permissions(self) -> None:
        permissions = [
            "project:create",
            "project:read",
            "project:update",
            "project:delete",
            "resume:create",
            "resume:read",
            "resume:update",
            "resume:delete",
            "user:read",
            "user:update",
        ]
        perm_repo = self._permission_service._repository
        for perm_name in permissions:
            await self._permission_service.get_or_create({"name": perm_name})
        await perm_repo.uow.commit()

    # ─── roles ─────────────────────────────────────────────────────────────

    async def _seed_roles(self) -> None:
        role_repo = self._role_service._repository

        await self._role_service.get_or_create(
            {"name": "admin", "description": "Полный доступ ко всем функциям системы"}
        )
        await self._role_service.get_or_create({"name": "teacher", "description": "Создание и оценка заданий"})
        await self._role_service.get_or_create(
            {"name": "member", "description": "Доступ к проектам и учебным материалам"}
        )
        await role_repo.uow.commit()

        role_admin = await role_repo.get_by_name("admin")
        role_teacher = await role_repo.get_by_name("teacher")
        role_member = await role_repo.get_by_name("member")

        admin_matrix = {
            "project": {"create": True, "read": True, "update": True, "delete": True},
            "resume": {"create": True, "read": True, "update": True, "delete": True},
            "user": {"create": False, "read": True, "update": True, "delete": True},
        }
        teacher_matrix = {
            "project": {"create": True, "read": True, "update": True, "delete": False},
            "resume": {"create": True, "read": True, "update": True, "delete": False},
            "user": {"create": False, "read": True, "update": True, "delete": False},
        }
        member_matrix = {
            "project": {"create": True, "read": True, "update": True, "delete": False},
            "resume": {"create": True, "read": True, "update": True, "delete": False},
            "user": {"create": False, "read": True, "update": False, "delete": False},
        }

        await self._role_service.remap_role_permission(role_admin.id, PermissionMatrix(permissions_matrix=admin_matrix))
        await self._role_service.remap_role_permission(
            role_teacher.id, PermissionMatrix(permissions_matrix=teacher_matrix)
        )
        await self._role_service.remap_role_permission(
            role_member.id, PermissionMatrix(permissions_matrix=member_matrix)
        )

    # ─── users ─────────────────────────────────────────────────────────────

    async def _seed_users(self) -> list:
        role_repo = self._role_service._repository
        role_admin = await role_repo.get_by_name("admin")
        role_teacher = await role_repo.get_by_name("teacher")
        role_member = await role_repo.get_by_name("member")

        users_data = [
            {
                "email": "admin@example.com",
                "first_name": "Admin",
                "middle_name": "",
                "last_name": "User",
                "password": "admin_password",
                "role_id": role_admin.id,
                "tg_nickname": "@admin_tg",
                "vk_nickname": "@admin_vk",
                "phone": "+7 (999) 123-45-67",
            },
            {
                "email": "member@example.com",
                "first_name": "Member",
                "middle_name": "",
                "last_name": "User",
                "password": "member_password",
                "role_id": role_member.id,
                "tg_nickname": "@member_tg",
                "phone": "+7 (999) 987-65-43",
            },
            {
                "email": "kirill@example.com",
                "first_name": "Кирилл",
                "middle_name": "",
                "last_name": "Сомов",
                "password": "kirill_password",
                "role_id": role_member.id,
                "tg_nickname": "@kirillsomov",
            },
            {
                "email": "anna@example.com",
                "first_name": "Анна",
                "middle_name": "",
                "last_name": "Красина",
                "password": "anna_password",
                "role_id": role_member.id,
                "tg_nickname": "@anutakrasina",
            },
            {
                "email": "ilya@example.com",
                "first_name": "Илья",
                "middle_name": "",
                "last_name": "Поперечный",
                "password": "ilya_password",
                "role_id": role_member.id,
                "tg_nickname": "@ilya_poperechny",
            },
            {
                "email": "maria@example.com",
                "first_name": "Мария",
                "middle_name": "",
                "last_name": "Петрова",
                "password": "maria_password",
                "role_id": role_teacher.id,
                "tg_nickname": "@maria_petrova",
            },
            {
                "email": "dmitry@example.com",
                "first_name": "Дмитрий",
                "middle_name": "",
                "last_name": "Козлов",
                "password": "dmitry_password",
                "role_id": role_member.id,
                "tg_nickname": "@dmitry_kozlov",
            },
            {
                "email": "elena@example.com",
                "first_name": "Елена",
                "middle_name": "",
                "last_name": "Соколова",
                "password": "elena_password",
                "role_id": role_member.id,
                "tg_nickname": "@elena_sokolova",
            },
            {
                "email": "alexey@example.com",
                "first_name": "Алексей",
                "middle_name": "",
                "last_name": "Иванов",
                "password": "alexey_password",
                "role_id": role_member.id,
                "tg_nickname": "@alexey_ivanov",
            },
        ]

        created_users = []
        for user_data in users_data:
            existing = await self._user_service.get_user_by_email(user_data["email"])
            if not existing:
                existing = await self._user_service.create(UserCreate(**user_data))
            created_users.append(existing)

        return created_users

    # ─── responses / invitations ───────────────────────────────────────────

    async def _seed_responses(self, users: list, workspaces_by_name: dict | None = None) -> None:
        session = self._project_repository.uow.session

        result = await session.execute(select(Response).limit(1))
        if result.scalar_one_or_none():
            return

        admin = users[0]
        await self._seed_accepted_responses(session, users)
        await self._seed_accepted_invitations(session, users, admin)
        await self._seed_pending_responses(session, users)
        await self._seed_pending_invitations(session, users, admin)

        await session.flush()

    async def _find_vacancy_id(self, project_name: str, title: str | None) -> int | None:
        if title is None:
            return None
        session = self._project_repository.uow.session
        r = await session.execute(
            select(ProjectVacancy.id).where(
                and_(
                    ProjectVacancy.title == title,
                    ProjectVacancy.project.has(Project.name == project_name),
                )
            )
        )
        return r.scalar_one_or_none()

    async def _vacancy_from_id(self, vacancy_id: int) -> ProjectVacancy | None:
        session = self._project_repository.uow.session
        vr = await session.execute(select(ProjectVacancy).where(ProjectVacancy.id == vacancy_id))
        return vr.scalar_one_or_none()

    async def _seed_accepted_responses(self, session, users: list) -> None:
        pairs = [
            (users[2], "Tasker", "Backend Developer"),
            (users[3], "Tasker", "Backend Developer"),
            (users[4], "Tasker", "Frontend Developer"),
            (users[6], "Campus Map", "Mobile Developer (React Native)"),
            (users[7], "Telegram-бот", "Python Developer"),
        ]
        for user, project_name, title in pairs:
            vacancy_id = await self._find_vacancy_id(project_name, title)
            if not vacancy_id:
                continue
            vacancy = await self._vacancy_from_id(vacancy_id)
            if not vacancy:
                continue
            session.add(
                Response(
                    respondent_id=user.id,
                    project_id=vacancy.project_id,
                    vacancy_id=vacancy_id,
                    inviter_id=None,
                    type="response",
                    status="accepted",
                )
            )

    async def _seed_accepted_invitations(self, session, users: list, admin) -> None:
        pairs = [
            (users[4], "Campus Map", "Mobile Developer (React Native)"),
            (users[3], "Аналитика", "Data Analyst"),
            (users[7], "Аналитика", "Data Analyst"),
            (users[2], "Хакатоны", "Fullstack Developer"),
            (users[5], "Хакатоны", "Fullstack Developer"),
            (users[6], "Хакатоны", "Fullstack Developer"),
            (users[8], "Хакатоны", "Fullstack Developer"),
            (users[4], "Конструктор резюме", "UI/UX Designer"),
            (users[8], "Конструктор резюме", "Frontend Developer"),
        ]
        for user, project_name, title in pairs:
            vacancy_id = await self._find_vacancy_id(project_name, title)
            if not vacancy_id:
                continue
            vacancy = await self._vacancy_from_id(vacancy_id)
            if not vacancy:
                continue
            session.add(
                Response(
                    respondent_id=user.id,
                    project_id=vacancy.project_id,
                    vacancy_id=vacancy_id,
                    inviter_id=admin.id,
                    type="invitation",
                    status="accepted",
                )
            )

    async def _seed_pending_responses(self, session, users: list) -> None:
        pairs = [
            (users[1], "Tasker", "Backend Developer"),
            (users[8], "Tasker", "Frontend Developer"),
            (users[5], "Campus Map", "Mobile Developer (React Native)"),
            (users[1], "AI Learning Platform", "ML Engineer"),
        ]
        for user, project_name, title in pairs:
            vacancy_id = await self._find_vacancy_id(project_name, title)
            if not vacancy_id:
                continue
            vacancy = await self._vacancy_from_id(vacancy_id)
            if not vacancy:
                continue
            session.add(
                Response(
                    respondent_id=user.id,
                    project_id=vacancy.project_id,
                    vacancy_id=vacancy_id,
                    inviter_id=None,
                    type="response",
                    status="pending",
                )
            )

    async def _seed_pending_invitations(self, session, users: list, admin) -> None:
        pairs = [
            (users[1], "AI Learning Platform", "ML Engineer"),
            (users[3], "AI Learning Platform", "ML Engineer"),
            (users[6], "Аналитика", "Data Analyst"),
            (users[2], "Конструктор резюме", "Frontend Developer"),
            (users[7], "База знаний", None),
        ]
        for user, project_name, title in pairs:
            if title:
                vacancy_id = await self._find_vacancy_id(project_name, title)
                if not vacancy_id:
                    continue
                vacancy = await self._vacancy_from_id(vacancy_id)
                if not vacancy:
                    continue
                session.add(
                    Response(
                        respondent_id=user.id,
                        project_id=vacancy.project_id,
                        vacancy_id=vacancy_id,
                        inviter_id=admin.id,
                        type="invitation",
                        status="pending",
                    )
                )
            else:
                project_result = await session.execute(select(Project).where(Project.name == project_name))
                project = project_result.scalar_one_or_none()
                if project:
                    session.add(
                        Response(
                            respondent_id=user.id,
                            project_id=project.id,
                            vacancy_id=None,
                            inviter_id=admin.id,
                            type="invitation",
                            status="pending",
                        )
                    )

    # ─── settings types ────────────────────────────────────────────────────

    async def _seed_settings_types(self) -> None:
        repo = self._workspace_service._repository
        types = [
            {"name": "space", "description": "Настройки пространства"},
        ]

        for st_data in types:
            result = await repo.uow.session.execute(select(SettingsType).where(SettingsType.name == st_data["name"]))
            if not result.scalar_one_or_none():
                repo.uow.session.add(SettingsType(**st_data))

        await repo.uow.commit()

    # ─── resumes ───────────────────────────────────────────────────────────

    async def _seed_resumes(self, users: list) -> None:
        repo = self._resume_service._repository
        session = repo.uow.session

        result = await session.execute(select(Resume).where(Resume.role.isnot(None)).limit(1))
        if result.scalar_one_or_none():
            return

        admin, _member, kirill, anna, ilya, *_ = users

        # удаляем старые резюме без role
        for u in [admin, kirill, anna, ilya]:
            old = await session.execute(select(Resume).where(Resume.author_id == u.id))
            for r in old.scalars().all():
                await session.delete(r)
        await session.flush()

        # ────── Admin: UX/UI Designer — 2 exp, 6 skills, 4 interests, 2 links, 1 edu, 2 lang ──────
        resume_admin = await self._resume_service.create_resume(
            ResumeCreate(
                header="UX/UI-дизайнер",
                resume_text="Опыт работы в продуктовом дизайне 3 года. Работал над образовательными платформами.",
                role="UX/UI Designer",
                about="Проектирую интуитивно понятные цифровые продукты. Специализируюсь на создании пользовательских интерфейсов для веб и мобильных приложений. Работаю в тесной связке с разработчиками и продакт-менеджерами, чтобы превращать сложные задачи в простые и эстетичные решения.",
                cover_letter="Я — UX/UI дизайнер с опытом работы над образовательными платформами и мобильными приложениями. За время работы я провел более 10 исследований пользователей, спроектировал информационную архитектуру для трёх крупных проектов и создал дизайн-системы, которые используются командами до 15 человек. Моя цель — создавать продукты, которые не только выглядят современно, но и решают реальные проблемы пользователей. Уверенно владею Figma, Sketch и Adobe Creative Suite. Понимаю технические ограничения и умею находить компромиссы между дизайном и разработкой.",
            ),
            admin.id,
        )

        session.add_all(
            [
                ResumeExperience(
                    resume_id=resume_admin.id,
                    company="Мобильное приложение «Plan It»",
                    position="UX/UI-дизайнер",
                    period_from=datetime(2024, 8, 1),
                    period_to=datetime(2025, 8, 1),
                    duration="7 месяцев",
                    responsibilities=[
                        "Провел детальный анализ конкурентов и определил ключевые UX-метрики",
                        "Разработал информационную архитектуру и пользовательские сценарии",
                        "Создал вайрфреймы и интерактивные прототипы в Figma",
                        "Подготовил UI-kit и дизайн-систему для разработчиков",
                    ],
                    skills=["Figma", "UX Research", "Wireframing", "UI Design"],
                    sort_order=0,
                ),
                ResumeExperience(
                    resume_id=resume_admin.id,
                    company="Веб-сервис для студентов",
                    position="UI/UX Designer",
                    period_from=datetime(2023, 2, 1),
                    period_to=datetime(2024, 6, 1),
                    duration="1 год 4 месяца",
                    responsibilities=[
                        "Проектировал интерфейс для платформы управления задачами",
                        "Проводил юзабилити-тестирование и A/B тесты",
                        "Разработал адаптивный дизайн для мобильной и десктопной версий",
                    ],
                    skills=["Figma", "Sketch", "Usability Testing"],
                    sort_order=1,
                ),
            ]
        )
        session.add_all(
            [
                ResumeSkill(resume_id=resume_admin.id, name="Figma", sort_order=0),
                ResumeSkill(resume_id=resume_admin.id, name="Sketch", sort_order=1),
                ResumeSkill(resume_id=resume_admin.id, name="UX Research", sort_order=2),
                ResumeSkill(resume_id=resume_admin.id, name="Wireframing", sort_order=3),
                ResumeSkill(resume_id=resume_admin.id, name="UI Design", sort_order=4),
                ResumeSkill(resume_id=resume_admin.id, name="Adobe Illustrator", sort_order=5),
            ]
        )
        session.add_all(
            [
                ResumeInterest(resume_id=resume_admin.id, name="Веб-дизайн", sort_order=0),
                ResumeInterest(resume_id=resume_admin.id, name="Мобильный дизайн", sort_order=1),
                ResumeInterest(resume_id=resume_admin.id, name="UX-исследования", sort_order=2),
                ResumeInterest(resume_id=resume_admin.id, name="Адаптивный дизайн", sort_order=3),
            ]
        )
        session.add_all(
            [
                ResumeLink(
                    resume_id=resume_admin.id, platform="Behance", url="https://behance.net/ezhidze", sort_order=0
                ),
                ResumeLink(
                    resume_id=resume_admin.id, platform="Dribbble", url="https://dribbble.com/ezhidze", sort_order=1
                ),
            ]
        )
        session.add_all(
            [
                ResumeEducation(
                    resume_id=resume_admin.id,
                    institution="ИТМО, Санкт-Петербург",
                    faculty="Мобильные и облачные технологии",
                    degree="Магистр",
                    years="2026",
                    sort_order=0,
                ),
            ]
        )
        session.add_all(
            [
                ResumeLanguage(resume_id=resume_admin.id, name="Русский", level="Родной", sort_order=0),
                ResumeLanguage(resume_id=resume_admin.id, name="English", level="B2", sort_order=1),
            ]
        )

        # ────── Кирилл Сомов: Product Manager — 1 exp, 4 skills, 2 interests, 0 links, 1 edu, 1 lang ──────
        resume_kirill = await self._resume_service.create_resume(
            ResumeCreate(
                header="Продуктовый менеджер",
                resume_text="Управляю продуктовой разработкой в EdTech.",
                role="Product Manager",
                about="Начинающий продакт-менеджер с фокусом на образовательные продукты.",
                cover_letter="Участвовал в запуске двух учебных курсов на платформе ИТМО.",
            ),
            kirill.id,
        )
        session.add_all(
            [
                ResumeExperience(
                    resume_id=resume_kirill.id,
                    company="ИТМО, Проектный офис",
                    position="Product Manager (стажёр)",
                    period_from=datetime(2025, 2, 1),
                    period_to=datetime(2025, 8, 1),
                    duration="6 месяцев",
                    responsibilities=[
                        "Собирал требования от заказчиков и формировал бэклог",
                        "Проводил продуктовые синки и ревью спринтов",
                        "Готовил аналитические отчёты по вовлечённости пользователей",
                    ],
                    skills=["Jira", "SQL", "Product Analytics"],
                    sort_order=0,
                ),
            ]
        )
        session.add_all(
            [
                ResumeSkill(resume_id=resume_kirill.id, name="Jira", sort_order=0),
                ResumeSkill(resume_id=resume_kirill.id, name="SQL", sort_order=1),
                ResumeSkill(resume_id=resume_kirill.id, name="Product Analytics", sort_order=2),
                ResumeSkill(resume_id=resume_kirill.id, name="Notion", sort_order=3),
            ]
        )
        session.add_all(
            [
                ResumeInterest(resume_id=resume_kirill.id, name="Управление продуктами", sort_order=0),
                ResumeInterest(resume_id=resume_kirill.id, name="EdTech", sort_order=1),
            ]
        )
        session.add_all(
            [
                ResumeEducation(
                    resume_id=resume_kirill.id,
                    institution="ИТМО, Санкт-Петербург",
                    faculty="Бизнес-информатика",
                    degree="Бакалавр",
                    years="2026",
                    sort_order=0,
                ),
            ]
        )
        session.add_all(
            [
                ResumeLanguage(resume_id=resume_kirill.id, name="Русский", level="Родной", sort_order=0),
            ]
        )

        # ────── Анна Красина: Backend Developer — 3 exp, 8 skills, 3 interests, 1 link, 2 edu, 2 lang ──────
        resume_anna = await self._resume_service.create_resume(
            ResumeCreate(
                header="Backend-разработчик",
                resume_text="Пишу на Python и Go. Проектирую API для высоконагруженных систем.",
                role="Backend Developer",
                about="Более 4 лет коммерческой разработки. Специализируюсь на микросервисной архитектуре и оптимизации производительности.",
                cover_letter="За последние два года разработала и запустила три микросервиса для обработки заказов, снизив latency на 30%. Активно участвую в код-ревью и внедрении best practices. Ищу команду, где смогу расти как лид.",
            ),
            anna.id,
        )
        session.add_all(
            [
                ResumeExperience(
                    resume_id=resume_anna.id,
                    company="Ozon Tech",
                    position="Backend Developer",
                    period_from=datetime(2024, 6, 1),
                    period_to=None,
                    duration="настоящее время",
                    responsibilities=[
                        "Разрабатываю микросервисы на Go для платформы логистики",
                        "Реализовал сервис кэширования, сокративший нагрузку на БД на 40%",
                        "Провожу код-ревью в команде из 8 человек",
                    ],
                    skills=["Go", "PostgreSQL", "Kafka", "Docker"],
                    sort_order=0,
                ),
                ResumeExperience(
                    resume_id=resume_anna.id,
                    company="Тинькофф",
                    position="Python Developer",
                    period_from=datetime(2022, 9, 1),
                    period_to=datetime(2024, 5, 1),
                    duration="1 год 8 месяцев",
                    responsibilities=[
                        "Писал бэкенд для внутренних инструментов банка на FastAPI",
                        "Автоматизировал отчёты, сэкономив 20 часов работы команды в месяц",
                        "Интегрировал внешние API (банки, CRM)",
                    ],
                    skills=["Python", "FastAPI", "SQLAlchemy", "Celery"],
                    sort_order=1,
                ),
                ResumeExperience(
                    resume_id=resume_anna.id,
                    company="Яндекс.Практикум",
                    position="Junior Python Developer",
                    period_from=datetime(2021, 6, 1),
                    period_to=datetime(2022, 8, 1),
                    duration="1 год 2 месяца",
                    responsibilities=[
                        "Разрабатывал учебные проекты и автоматические тесты",
                        "Поддерживал документацию API в Swagger",
                    ],
                    skills=["Python", "Django", "REST API"],
                    sort_order=2,
                ),
            ]
        )
        session.add_all(
            [
                ResumeSkill(resume_id=resume_anna.id, name="Python", sort_order=0),
                ResumeSkill(resume_id=resume_anna.id, name="Go", sort_order=1),
                ResumeSkill(resume_id=resume_anna.id, name="FastAPI", sort_order=2),
                ResumeSkill(resume_id=resume_anna.id, name="PostgreSQL", sort_order=3),
                ResumeSkill(resume_id=resume_anna.id, name="Docker", sort_order=4),
                ResumeSkill(resume_id=resume_anna.id, name="Kafka", sort_order=5),
                ResumeSkill(resume_id=resume_anna.id, name="Redis", sort_order=6),
                ResumeSkill(resume_id=resume_anna.id, name="GitHub Actions", sort_order=7),
            ]
        )
        session.add_all(
            [
                ResumeInterest(resume_id=resume_anna.id, name="Бэкенд-разработка", sort_order=0),
                ResumeInterest(resume_id=resume_anna.id, name="Системная архитектура", sort_order=1),
                ResumeInterest(resume_id=resume_anna.id, name="Open Source", sort_order=2),
            ]
        )
        session.add_all(
            [
                ResumeLink(
                    resume_id=resume_anna.id, platform="GitHub", url="https://github.com/annakrasina", sort_order=0
                ),
            ]
        )
        session.add_all(
            [
                ResumeEducation(
                    resume_id=resume_anna.id,
                    institution="ИТМО, Санкт-Петербург",
                    faculty="Программная инженерия",
                    degree="Магистр",
                    years="2025",
                    sort_order=0,
                ),
                ResumeEducation(
                    resume_id=resume_anna.id,
                    institution="ИТМО, Санкт-Петербург",
                    faculty="Информационные системы",
                    degree="Бакалавр",
                    years="2023",
                    sort_order=1,
                ),
            ]
        )
        session.add_all(
            [
                ResumeLanguage(resume_id=resume_anna.id, name="Русский", level="Родной", sort_order=0),
                ResumeLanguage(resume_id=resume_anna.id, name="English", level="C1", sort_order=1),
            ]
        )

        # ────── Илья Поперечный: Junior Frontend — 0 exp, 3 skills, 1 interest, 1 link, 0 edu, 1 lang ──────
        resume_ilya = await self._resume_service.create_resume(
            ResumeCreate(
                header="Frontend-разработчик (стажёр)",
                resume_text="Изучаю React и TypeScript. Хочу расти в продуктовой команде.",
                role="Junior Frontend Developer",
            ),
            ilya.id,
        )
        session.add_all(
            [
                ResumeSkill(resume_id=resume_ilya.id, name="React", sort_order=0),
                ResumeSkill(resume_id=resume_ilya.id, name="TypeScript", sort_order=1),
                ResumeSkill(resume_id=resume_ilya.id, name="Tailwind CSS", sort_order=2),
            ]
        )
        session.add_all(
            [
                ResumeInterest(resume_id=resume_ilya.id, name="Фронтенд-разработка", sort_order=0),
            ]
        )
        session.add_all(
            [
                ResumeLink(
                    resume_id=resume_ilya.id, platform="GitHub", url="https://github.com/ilya-front", sort_order=0
                ),
            ]
        )
        session.add_all(
            [
                ResumeLanguage(resume_id=resume_ilya.id, name="Русский", level="Родной", sort_order=0),
            ]
        )

        # ────── Member User: Fullstack Developer — 1 exp, 4 skills ──────
        _member, _maria, _dmitry, _elena, _alexey, *_ = users[1:]

        resume_member = await self._resume_service.create_resume(
            ResumeCreate(
                header="Fullstack-разработчик",
                resume_text="Пишу на Python и JavaScript. Интересуюсь веб-разработкой.",
                role="Fullstack Developer",
                about="Начинающий разработчик, изучаю FastAPI и React.",
            ),
            _member.id,
        )
        session.add_all(
            [
                ResumeExperience(
                    resume_id=resume_member.id,
                    company="Учебные проекты ИТМО",
                    position="Fullstack Developer (стажёр)",
                    period_from=datetime(2025, 9, 1),
                    period_to=None,
                    duration="настоящее время",
                    responsibilities=["Разработка API", "Вёрстка интерфейсов", "Работа с БД"],
                    skills=["Python", "JavaScript", "PostgreSQL"],
                    sort_order=0,
                ),
            ]
        )
        session.add_all(
            [
                ResumeSkill(resume_id=resume_member.id, name="Python", sort_order=0),
                ResumeSkill(resume_id=resume_member.id, name="JavaScript", sort_order=1),
                ResumeSkill(resume_id=resume_member.id, name="React", sort_order=2),
                ResumeSkill(resume_id=resume_member.id, name="PostgreSQL", sort_order=3),
            ]
        )
        session.add_all(
            [
                ResumeEducation(
                    resume_id=resume_member.id,
                    institution="ИТМО, Санкт-Петербург",
                    faculty="Программная инженерия",
                    degree="Бакалавр",
                    years="2027",
                    sort_order=0,
                ),
            ]
        )
        session.add_all(
            [
                ResumeLanguage(resume_id=resume_member.id, name="Русский", level="Родной", sort_order=0),
            ]
        )

        # ────── Мария Петрова: Project Manager — 1 exp, 4 skills, 1 link ──────

        resume_maria = await self._resume_service.create_resume(
            ResumeCreate(
                header="Project Manager",
                resume_text="Управляю проектами в EdTech. Координирую команды до 10 человек.",
                role="Project Manager",
                about="Опыт управления образовательными проектами более 3 лет. Специализируюсь на Agile-методологиях.",
                cover_letter="Ищу проект, где смогу применить навыки управления распределённой командой.",
            ),
            _maria.id,
        )
        session.add_all(
            [
                ResumeExperience(
                    resume_id=resume_maria.id,
                    company="ИТМО, Учебный офис",
                    position="Project Manager",
                    period_from=datetime(2023, 9, 1),
                    period_to=None,
                    duration="настоящее время",
                    responsibilities=["Координация проектных команд", "Ведение документации", "Организация демо-дней"],
                    skills=["Jira", "Agile", "MS Project"],
                    sort_order=0,
                ),
            ]
        )
        session.add_all(
            [
                ResumeSkill(resume_id=resume_maria.id, name="Jira", sort_order=0),
                ResumeSkill(resume_id=resume_maria.id, name="Agile", sort_order=1),
                ResumeSkill(resume_id=resume_maria.id, name="Scrum", sort_order=2),
                ResumeSkill(resume_id=resume_maria.id, name="Confluence", sort_order=3),
            ]
        )
        session.add_all(
            [
                ResumeLink(
                    resume_id=resume_maria.id,
                    platform="LinkedIn",
                    url="https://linkedin.com/in/maria-petrova",
                    sort_order=0,
                ),
            ]
        )
        session.add_all(
            [
                ResumeEducation(
                    resume_id=resume_maria.id,
                    institution="ИТМО, Санкт-Петербург",
                    faculty="Управление проектами",
                    degree="Магистр",
                    years="2025",
                    sort_order=0,
                ),
            ]
        )
        session.add_all(
            [
                ResumeLanguage(resume_id=resume_maria.id, name="Русский", level="Родной", sort_order=0),
                ResumeLanguage(resume_id=resume_maria.id, name="English", level="B2", sort_order=1),
            ]
        )

        # ────── Дмитрий Козлов: QA Engineer — 2 exp, 5 skills, 1 link ──────
        resume_dmitry = await self._resume_service.create_resume(
            ResumeCreate(
                header="QA Engineer",
                resume_text="Ручное и автоматизированное тестирование веб-приложений.",
                role="QA Engineer",
                about="Опыт тестирования 2 года. Пишу автотесты на Python + Selenium.",
            ),
            _dmitry.id,
        )
        session.add_all(
            [
                ResumeExperience(
                    resume_id=resume_dmitry.id,
                    company="Яндекс",
                    position="QA Engineer",
                    period_from=datetime(2024, 3, 1),
                    period_to=None,
                    duration="настоящее время",
                    responsibilities=["Функциональное тестирование", "Автоматизация регресса", "Ведение тест-кейсов"],
                    skills=["Selenium", "Python", "Postman"],
                    sort_order=0,
                ),
                ResumeExperience(
                    resume_id=resume_dmitry.id,
                    company="Технопарк ИТМО",
                    position="Junior QA",
                    period_from=datetime(2023, 2, 1),
                    period_to=datetime(2024, 2, 1),
                    duration="1 год",
                    responsibilities=["Ручное тестирование", "Составление баг-репортов"],
                    skills=["Jira", "TestRail"],
                    sort_order=1,
                ),
            ]
        )
        session.add_all(
            [
                ResumeSkill(resume_id=resume_dmitry.id, name="Python", sort_order=0),
                ResumeSkill(resume_id=resume_dmitry.id, name="Selenium", sort_order=1),
                ResumeSkill(resume_id=resume_dmitry.id, name="Postman", sort_order=2),
                ResumeSkill(resume_id=resume_dmitry.id, name="SQL", sort_order=3),
                ResumeSkill(resume_id=resume_dmitry.id, name="Git", sort_order=4),
            ]
        )
        session.add_all(
            [
                ResumeLink(
                    resume_id=resume_dmitry.id, platform="GitHub", url="https://github.com/dmitry-qa", sort_order=0
                ),
            ]
        )
        session.add_all(
            [
                ResumeEducation(
                    resume_id=resume_dmitry.id,
                    institution="ИТМО, Санкт-Петербург",
                    faculty="Программная инженерия",
                    degree="Бакалавр",
                    years="2026",
                    sort_order=0,
                ),
            ]
        )
        session.add_all(
            [
                ResumeLanguage(resume_id=resume_dmitry.id, name="Русский", level="Родной", sort_order=0),
            ]
        )

        # ────── Елена Соколова: Data Scientist — 1 exp, 4 skills ──────
        resume_elena = await self._resume_service.create_resume(
            ResumeCreate(
                header="Data Scientist",
                resume_text="Анализ данных, ML-модели, визуализация. Работаю с Python и R.",
                role="Data Scientist",
                about="Магистр прикладной математики. Построила модель прогнозирования оттока студентов.",
            ),
            _elena.id,
        )
        session.add_all(
            [
                ResumeExperience(
                    resume_id=resume_elena.id,
                    company="ИТМО, Data Lab",
                    position="Data Scientist",
                    period_from=datetime(2024, 6, 1),
                    period_to=None,
                    duration="настоящее время",
                    responsibilities=["Сбор и очистка данных", "Обучение моделей", "Подготовка отчётов"],
                    skills=["Python", "Pandas", "Scikit-learn"],
                    sort_order=0,
                ),
            ]
        )
        session.add_all(
            [
                ResumeSkill(resume_id=resume_elena.id, name="Python", sort_order=0),
                ResumeSkill(resume_id=resume_elena.id, name="Pandas", sort_order=1),
                ResumeSkill(resume_id=resume_elena.id, name="Scikit-learn", sort_order=2),
                ResumeSkill(resume_id=resume_elena.id, name="SQL", sort_order=3),
            ]
        )
        session.add_all(
            [
                ResumeEducation(
                    resume_id=resume_elena.id,
                    institution="ИТМО, Санкт-Петербург",
                    faculty="Прикладная математика",
                    degree="Магистр",
                    years="2026",
                    sort_order=0,
                ),
            ]
        )
        session.add_all(
            [
                ResumeLanguage(resume_id=resume_elena.id, name="Русский", level="Родной", sort_order=0),
                ResumeLanguage(resume_id=resume_elena.id, name="English", level="B2", sort_order=1),
            ]
        )

        # ────── Алексей Иванов: DevOps Engineer — 1 exp, 4 skills ──────
        resume_alexey = await self._resume_service.create_resume(
            ResumeCreate(
                header="DevOps Engineer",
                resume_text="Настройка CI/CD, Docker, Kubernetes. Инфраструктура как код.",
                role="DevOps Engineer",
                about="Автоматизирую развёртывание и мониторинг. Опыт работы с Yandex Cloud.",
            ),
            _alexey.id,
        )
        session.add_all(
            [
                ResumeExperience(
                    resume_id=resume_alexey.id,
                    company="VK Cloud",
                    position="DevOps Engineer",
                    period_from=datetime(2024, 1, 1),
                    period_to=None,
                    duration="настоящее время",
                    responsibilities=[
                        "Настройка CI/CD pipelines",
                        "Контейнеризация сервисов",
                        "Мониторинг инфраструктуры",
                    ],
                    skills=["Docker", "Kubernetes", "GitLab CI"],
                    sort_order=0,
                ),
            ]
        )
        session.add_all(
            [
                ResumeSkill(resume_id=resume_alexey.id, name="Docker", sort_order=0),
                ResumeSkill(resume_id=resume_alexey.id, name="Kubernetes", sort_order=1),
                ResumeSkill(resume_id=resume_alexey.id, name="Linux", sort_order=2),
                ResumeSkill(resume_id=resume_alexey.id, name="Terraform", sort_order=3),
            ]
        )
        session.add_all(
            [
                ResumeLink(
                    resume_id=resume_alexey.id, platform="GitHub", url="https://github.com/alexey-devops", sort_order=0
                ),
            ]
        )
        session.add_all(
            [
                ResumeEducation(
                    resume_id=resume_alexey.id,
                    institution="ИТМО, Санкт-Петербург",
                    faculty="Инфокоммуникационные технологии",
                    degree="Бакалавр",
                    years="2025",
                    sort_order=0,
                ),
            ]
        )
        session.add_all(
            [
                ResumeLanguage(resume_id=resume_alexey.id, name="Русский", level="Родной", sort_order=0),
            ]
        )

        await session.flush()

    # ─── portfolio ─────────────────────────────────────────────────────────

    async def _seed_portfolio(self, admin: object) -> None:
        existing = await self._portfolio_service.get_by_user_id(admin.id)
        if existing:
            return

        await self._portfolio_service.create_portfolio(
            PortfolioCreate(title="ezhidze.figma.site", url="https://ezhidze.figma.site"),
            admin.id,
        )
        await self._portfolio_service.create_portfolio(
            PortfolioCreate(title="dribbble.com/ezhidze", url="https://dribbble.com/ezhidze"),
            admin.id,
        )

    # ─── education ─────────────────────────────────────────────────────────

    async def _seed_education(self, admin: object) -> None:
        existing = await self._education_service.get_by_user_id(admin.id)
        if existing:
            return

        await self._education_service.create_education(
            EducationCreate(
                institution="ИТМО, Санкт-Петербург",
                faculty="Мобильные и облачные технологии",
                degree="Магистр",
                years="2026",
            ),
            admin.id,
        )
        await self._education_service.create_education(
            EducationCreate(
                institution="ИТМО, Санкт-Петербург",
                faculty="Мобильные и сетевые технологии",
                degree="Бакалавр",
                years="2024",
            ),
            admin.id,
        )

    # ─── languages ─────────────────────────────────────────────────────────

    async def _seed_languages(self, admin: object) -> None:
        existing = await self._language_service.get_by_user_id(admin.id)
        if existing:
            return

        await self._language_service.create_language(
            LanguageCreate(name="Русский", level="Родной", flag="🇷🇺"),
            admin.id,
        )
        await self._language_service.create_language(
            LanguageCreate(name="English", level="B2", flag="🇬🇧"),
            admin.id,
        )

    # ─── workspace statuses ────────────────────────────────────────────────

    async def _seed_workspace_statuses(self) -> None:
        repo = self._workspace_service._repository
        statuses = [
            {"name": "active"},
            {"name": "archived"},
            {"name": "on_hold"},
        ]

        for status_data in statuses:
            result = await repo.uow.session.execute(
                select(WorkSpaceStatus).where(WorkSpaceStatus.name == status_data["name"])
            )
            if not result.scalar_one_or_none():
                repo.uow.session.add(WorkSpaceStatus(**status_data))

        await repo.uow.commit()

    # ─── workspace categories ──────────────────────────────────────────────

    async def _seed_workspace_categories(self) -> dict[str, WorkSpaceCategories]:
        categories_data = [
            {"name": "Дисциплины", "color": "#10b981"},
            {"name": "Общеуниверситетские проекты", "color": "#6366f1"},
        ]

        categories_by_name = {}
        for cat_data in categories_data:
            category = await self._workspace_service.get_or_create_category(cat_data)
            categories_by_name[category.name] = category

        await self._workspace_service._repository.uow.commit()
        return categories_by_name

    # ─── workspaces ────────────────────────────────────────────────────────

    async def _seed_workspaces(
        self,
        admin: object,
        categories_by_name: dict[str, WorkSpaceCategories],
    ) -> dict[str, WorkSpace]:
        repo = self._workspace_service._repository
        workspaces_data = [
            ("Admin Workspace 1", "Общеуниверситетские проекты", "bg-blue-500", False),
            ("Admin Workspace 2", "Дисциплины", "bg-green-500", True),
        ]

        workspaces_by_name = {}
        for ws_name, category_name, ws_color, is_private in workspaces_data:
            result = await repo.uow.session.execute(select(WorkSpace).where(WorkSpace.name == ws_name))
            existing = result.scalar_one_or_none()

            if not existing:
                category = categories_by_name.get(category_name)
                workspace_data = WorkSpaceCreate(
                    name=ws_name,
                    author_id=admin.id,
                    status_id=1,
                    category_id=category.id if category else None,
                    color=ws_color,
                )
                existing = await repo.create(workspace_data)

                # Добавить автора в участники
                participation = WorkSpaceParticipation(
                    workspace_id=existing.id,
                    participant_id=admin.id,
                )
                repo.uow.session.add(participation)

                # Создать настройки
                await self._settings_service.create_defaults(existing.id)

                # Если приватное — выставить visibility
                if is_private:
                    await self._settings_service.create_or_update(
                        existing.id,
                        SpaceSettingsUpdate(visibility="private"),
                    )

            workspaces_by_name[ws_name] = existing

        return workspaces_by_name

    # ─── projects ──────────────────────────────────────────────────────────

    async def _seed_projects(
        self,
        users: list,
        workspaces_by_name: dict[str, WorkSpace],
    ) -> None:
        admin = users[0]
        ws1 = workspaces_by_name.get("Admin Workspace 1")
        ws2 = workspaces_by_name.get("Admin Workspace 2")

        # status_id: 1=planned, 2=in_progress, 3=completed, 4=review
        projects_data = [
            # ── Project 0 ──
            {
                "name": "Tasker — платформа управления задачами",
                "description": (
                    "Tasker — учебный проект по разработке веб-сервиса для управления "
                    "задачами и проектами. Сервис предназначен для планирования задач, "
                    "распределения ролей в команде, работы с дедлайнами и отслеживания "
                    "прогресса выполнения проекта."
                ),
                "workspace": ws1,
                "status_id": 2,
                "progress": 75,
                "max_participants": 8,
                "tags": ["Frontend", "Backend", "Design"],
                "deadline": datetime(2026, 8, 15),
                "vacancies": [
                    VacancyCreate(
                        title="Backend Developer",
                        tasks=[
                            "Проектирование и реализация серверной логики",
                            "Разработка API и интеграция с БД",
                            "Написание тестов и документации",
                        ],
                        required_count=2,
                    ),
                    VacancyCreate(
                        title="Frontend Developer",
                        tasks=[
                            "Разработка пользовательского интерфейса",
                            "Интеграция с REST API",
                            "Оптимизация производительности",
                        ],
                        required_count=3,
                    ),
                ],
                "participants": [users[2], users[3], users[4]],
            },
            # ── Project 1 ──
            {
                "name": "AI Learning Platform",
                "description": "Разработка цифровой платформы с искусственным интеллектом для персонализированного обучения",
                "workspace": ws2,
                "status_id": 2,
                "progress": 30,
                "max_participants": 5,
                "tags": ["AI/ML", "Design", "UI/UX"],
                "deadline": datetime(2026, 12, 1),
                "vacancies": [
                    VacancyCreate(
                        title="ML Engineer",
                        tasks=[
                            "Разработка и обучение моделей ML",
                            "Подготовка данных и фич-инжиниринг",
                        ],
                        required_count=2,
                    ),
                ],
                "participants": [],
            },
            # ── Project 2 ──
            {
                "name": "Мобильное приложение Campus Map",
                "description": "Интерактивная карта кампуса ИТМО с навигацией по аудиториям, расписанием занятий и push-уведомлениями",
                "workspace": ws1,
                "status_id": 1,
                "progress": 10,
                "max_participants": 6,
                "tags": ["Mobile", "UI/UX", "Frontend"],
                "deadline": datetime(2026, 10, 1),
                "vacancies": [
                    VacancyCreate(
                        title="Mobile Developer (React Native)",
                        tasks=[
                            "Разработка мобильного интерфейса",
                            "Интеграция с картами и геолокацией",
                            "Публикация в App Store и Google Play",
                        ],
                        required_count=2,
                    ),
                ],
                "participants": [users[4], users[6]],
            },
            # ── Project 3 ──
            {
                "name": "Система аналитики учебных групп",
                "description": "Веб-сервис для сбора и визуализации статистики успеваемости студентов по группам и дисциплинам",
                "workspace": ws2,
                "status_id": 3,
                "progress": 100,
                "max_participants": 4,
                "tags": ["Backend", "Data Science", "Design"],
                "deadline": datetime(2026, 5, 20),
                "vacancies": [
                    VacancyCreate(
                        title="Data Analyst",
                        tasks=[
                            "Разработка дашбордов и отчётов",
                            "Агрегация данных из разных источников",
                        ],
                        required_count=1,
                    ),
                ],
                "participants": [users[3], users[7]],
            },
            # ── Project 4 ──
            {
                "name": "Платформа для хакатонов",
                "description": "Сервис для организации и проведения хакатонов: регистрация команд, загрузка решений, оценка жюри",
                "workspace": ws1,
                "status_id": 2,
                "progress": 45,
                "max_participants": 10,
                "tags": ["Backend", "Frontend", "Design"],
                "deadline": datetime(2026, 9, 10),
                "vacancies": [
                    VacancyCreate(
                        title="Fullstack Developer",
                        tasks=[
                            "Разработка API и фронтенда",
                            "Система аутентификации и ролей",
                            "Реализация таймеров и ленты событий",
                        ],
                        required_count=3,
                    ),
                ],
                "participants": [users[2], users[5], users[6], users[8]],
            },
            # ── Project 5 ──
            {
                "name": "Telegram-бот для учебных опросов",
                "description": "Автоматизированный бот для проведения опросов и тестов в учебных группах с экспортом результатов",
                "workspace": ws2,
                "status_id": 4,
                "progress": 85,
                "max_participants": 3,
                "tags": ["Backend", "Mobile"],
                "deadline": datetime(2026, 7, 1),
                "vacancies": [
                    VacancyCreate(
                        title="Python Developer",
                        tasks=[
                            "Разработка логики бота на python-telegram-bot",
                            "Интеграция с БД для хранения результатов",
                        ],
                        required_count=1,
                    ),
                ],
                "participants": [users[7]],
            },
            # ── Project 6 ──
            {
                "name": "Конструктор резюме",
                "description": "Визуальный редактор для создания резюме с готовыми шаблонами и экспортом в PDF",
                "workspace": ws1,
                "status_id": 1,
                "progress": 5,
                "max_participants": 4,
                "tags": ["Frontend", "Design", "UI/UX"],
                "deadline": None,
                "vacancies": [
                    VacancyCreate(
                        title="UI/UX Designer",
                        tasks=[
                            "Дизайн шаблонов резюме",
                            "Прототипирование редактора",
                        ],
                        required_count=1,
                    ),
                    VacancyCreate(
                        title="Frontend Developer",
                        tasks=[
                            "Реализация drag-and-drop редактора",
                            "Генерация PDF на клиенте",
                        ],
                        required_count=2,
                    ),
                ],
                "participants": [users[4], users[8]],
            },
            # ── Project 7 ──
            {
                "name": "База знаний факультета",
                "description": "Wiki-платформа для факультета с возможностью коллективного редактирования, поиском и разграничением прав",
                "workspace": ws2,
                "status_id": 3,
                "progress": 100,
                "max_participants": 6,
                "tags": ["Backend", "Frontend", "Design"],
                "deadline": datetime(2026, 6, 15),
                "vacancies": [],
                "participants": [users[5], users[6]],
            },
        ]

        # Демо-задачи для каждого проекта (по имени колонки)
        demo_tasks: list[list[dict[str, list[str]]]] = [
            # Project 0: Tasker
            [
                {"Нужно сделать": ["Настроить CI/CD", "Добавить тесты для API"]},
                {"В процессе": ["Реализовать аутентификацию", "Сверстать главную страницу"]},
                {"Готово": ["Спроектировать БД", "Настроить Docker"]},
            ],
            # Project 1: AI Learning Platform
            [
                {"Нужно сделать": ["Собрать датасет", "Написать пайплайн обучения"]},
                {"В процессе": ["Разработать архитектуру ML", "Подготовить фичи"]},
                {"Готово": []},
            ],
            # Project 2: Campus Map
            [
                {"Нужно сделать": ["Выбрать стек", "Исследовать библиотеки карт", "Нарисовать прототип"]},
                {"В процессе": []},
                {"Готово": []},
            ],
            # Project 3: Аналитика
            [
                {"Нужно сделать": []},
                {"В процессе": []},
                {
                    "Готово": [
                        "Собрать требования",
                        "Спроектировать БД",
                        "Реализовать ETL-пайплайн",
                        "Настроить дашборды",
                        "Написать документацию",
                    ]
                },
            ],
            # Project 4: Хакатоны
            [
                {"Нужно сделать": ["Спроектировать API", "Разработать макет главной страницы"]},
                {"В процессе": ["Реализовать регистрацию команд", "Создать систему оценки"]},
                {"Готово": ["Определить MVP", "Настроить окружение"]},
            ],
            # Project 5: Telegram-бот
            [
                {"Нужно сделать": ["Добавить экспорт в Excel"]},
                {"В процессе": ["Реализовать команду /poll", "Интеграция с Google Forms"]},
                {"Готово": ["Базовая архитектура бота", "Подключение к БД", "Команда /start и /help"]},
            ],
            # Project 6: Конструктор резюме
            [
                {"Нужно сделать": ["Исследовать существующие решения", "Создать прототип в Figma"]},
                {"В процессе": []},
                {"Готово": []},
            ],
            # Project 7: База знаний
            [
                {"Нужно сделать": []},
                {"В процессе": []},
                {
                    "Готово": [
                        "Разработать архитектуру",
                        "Реализовать поиск",
                        "Создать редактор статей",
                        "Настроить права доступа",
                        "Провести тестирование",
                    ]
                },
            ],
        ]

        for idx, data in enumerate(projects_data):
            # Проверяем существование проекта по имени через репозиторий
            result = await self._project_repository.uow.session.execute(
                select(Project).where(Project.name == data["name"])
            )
            if result.scalar_one_or_none():
                continue

            ws = data["workspace"]
            project_data = ProjectCreate(
                name=data["name"],
                description=data["description"],
                status_id=data["status_id"],
                progress=data["progress"],
                tags=data["tags"],
                author_id=admin.id,
                workspace_id=ws.id,
                max_participants=data.get("max_participants"),
                deadline=data.get("deadline"),
                vacancies=data.get("vacancies"),
            )

            # Используем сервис — он сам разберётся с тегами и связями
            project = await self._project_service.create_project(project_data, admin.id)

            # Добавляем участников в проект (админ уже добавлен через create_project)
            for participant in data.get("participants", []):
                self._project_repository.uow.session.add(
                    ProjectParticipation(
                        project_id=project.id,
                        participant_id=participant.id,
                    )
                )
                # Синхронизируем с участниками workspace
                existing_ws = await self._project_repository.uow.session.execute(
                    select(WorkSpaceParticipation).where(
                        WorkSpaceParticipation.workspace_id == ws.id,
                        WorkSpaceParticipation.participant_id == participant.id,
                    )
                )
                if not existing_ws.scalar_one_or_none():
                    self._project_repository.uow.session.add(
                        WorkSpaceParticipation(
                            workspace_id=ws.id,
                            participant_id=participant.id,
                        )
                    )

            await self._project_repository.uow.session.flush()

            # Создаём колонки канбан-доски
            columns = await self._kanban_service.create_default_columns(project.id)
            col_by_name = {col.name: col for col in columns}

            # Создаём демо-задачи
            if idx < len(demo_tasks):
                for col_tasks in demo_tasks[idx]:
                    for col_name, task_titles in col_tasks.items():
                        column = col_by_name.get(col_name)
                        if not column or not task_titles:
                            continue
                        for title in task_titles:
                            await self._kanban_service.create_task(
                                TaskCreate(column_id=column.id, title=title),
                                admin.id,
                            )
