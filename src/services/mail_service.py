from __future__ import annotations

from email.message import EmailMessage
from typing import ClassVar

import aiosmtplib

from src.core.config import settings
from src.core.logging_config import get_logger

# ─────────── EduFlow email design tokens ───────────
# Inline-styled, table-based HTML for maximum email-client compatibility.
# Mirrors the frontend design system (frontend/src/index.css):
#   background #f7f7f8, surface #ffffff, text #111827, muted #6b7280,
#   button #030213 (white text), accent link #155dfc, border #e5e7eb.
_BRAND = "EduFlow"
_BACKGROUND = "#f7f7f8"
_SURFACE = "#ffffff"
_TEXT = "#111827"
_MUTED = "#6b7280"
_BORDER = "#e5e7eb"
_BUTTON_BG = "#030213"
_BUTTON_TEXT = "#ffffff"
_ACCENT = "#155dfc"
_GHOST_BG = "#f3f4f6"


class MailService:
    """Отправка писем через SMTP (по умолчанию maildev: localhost:2500, UI localhost:9000)."""

    def __init__(self) -> None:
        self._logger = get_logger(self.__class__.__name__)

    async def send_html(self, to: str, subject: str, html: str) -> bool:
        message = EmailMessage()
        message["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
        message["To"] = to
        message["Subject"] = subject
        message.set_content("Смотрите содержимое письма в HTML-клиенте.")
        message.add_alternative(html, subtype="html")

        try:
            await aiosmtplib.send(
                message,
                hostname=settings.MAIL_SMTP_HOST,
                port=settings.MAIL_SMTP_PORT,
                username=settings.MAIL_SMTP_USER,
                password=settings.MAIL_SMTP_PASSWORD,
                use_tls=settings.MAIL_TLS,
                timeout=10,
            )
        except Exception:
            self._logger.exception(f"Failed to send email to {to}: {subject}")
            return False
        else:
            self._logger.info(f"Email sent to {to}: {subject}")
            return True

    @staticmethod
    def _wrap(body: str, heading: str) -> str:
        """Обёртка письма: фон, шапка с брендом, карточка, футер."""
        return f"""
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{heading} — {_BRAND}</title>
<style>
    body, table, td, a {{ font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }}
    @media only screen and (max-width: 620px) {{
        .container {{ width: 100% !important; }}
        .card {{ border-radius: 12px !important; }}
        .card-pad {{ padding: 24px 20px !important; }}
        .heading {{ font-size: 24px !important; }}
        .code {{ font-size: 34px !important; letter-spacing: 4px !important; }}
        .btn {{ padding: 13px 26px !important; }}
    }}
</style>
</head>
<body style="margin:0;padding:0;background-color:{_BACKGROUND};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:{_BACKGROUND};">
  <tr>
    <td align="center" style="padding:32px 16px;">
      <table role="presentation" class="container" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
        <tr>
          <td align="center" style="padding:0 0 24px 0;">
            <span style="font-size:22px;font-weight:700;color:{_TEXT};letter-spacing:-0.02em;">{_BRAND}</span>
          </td>
        </tr>
        <tr>
          <td bgcolor="{_SURFACE}" style="background-color:{_SURFACE};border:1px solid {_BORDER};border-radius:16px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td class="card-pad" style="padding:32px;">
                  <h1 class="heading" style="margin:0 0 12px 0;font-size:28px;line-height:1.3;font-weight:700;color:{_TEXT};letter-spacing:-0.01em;">{heading}</h1>
                  {body}
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td align="center" style="padding:24px 0 0 0;">
            <p style="margin:0;font-size:12px;line-height:1.4;color:{_MUTED};">&copy; 2024-2026 {_BRAND}. Все права защищены.</p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>
"""

    async def send_signup_code(self, to: str, code: int) -> bool:
        body = f"""
                    <p style="margin:0 0 20px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        Добро пожаловать в {_BRAND}! Для завершения регистрации введите код подтверждения:
                    </p>
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px 0;">
                        <tr>
                            <td align="center" bgcolor="{_GHOST_BG}" style="background-color:{_GHOST_BG};border-radius:12px;padding:20px 16px;">
                                <span class="code" style="font-size:40px;line-height:1.2;font-weight:700;color:{_TEXT};letter-spacing:4px;">{code}</span>
                            </td>
                        </tr>
                    </table>
                    <p style="margin:0;font-size:13px;line-height:1.4;color:{_MUTED};">
                        Код действует 5 минут. Если вы не запрашивали регистрацию, просто проигнорируйте это письмо.
                    </p>
        """
        html = self._wrap(body, "Подтверждение регистрации")
        return await self.send_html(to, f"Код подтверждения — {_BRAND}", html)

    async def send_password_reset(self, to: str, reset_url: str) -> bool:
        body = f"""
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        Мы получили запрос на сброс пароля для вашего аккаунта {_BRAND}. Для продолжения нажмите кнопку ниже:
                    </p>
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px 0;">
                        <tr>
                            <td align="center">
                                <a class="btn" href="{reset_url}"
                                   style="display:inline-block;padding:14px 28px;border-radius:12px;background-color:{_BUTTON_BG};color:{_BUTTON_TEXT};font-size:16px;font-weight:600;line-height:1.5;letter-spacing:0.02em;text-decoration:none;">
                                    Сбросить пароль
                                </a>
                            </td>
                        </tr>
                    </table>
                    <p style="margin:0;font-size:13px;line-height:1.4;color:{_MUTED};">
                        Ссылка действует 1 час. Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо.
                    </p>
        """
        html = self._wrap(body, "Сброс пароля")
        return await self.send_html(to, f"Сброс пароля — {_BRAND}", html)

    def _action_button(self, url: str, label: str) -> str:
        return f"""
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px 0;">
                        <tr>
                            <td align="center">
                                <a class="btn" href="{url}"
                                   style="display:inline-block;padding:14px 28px;border-radius:12px;background-color:{_BUTTON_BG};color:{_BUTTON_TEXT};font-size:16px;font-weight:600;line-height:1.5;letter-spacing:0.02em;text-decoration:none;">
                                    {label}
                                </a>
                            </td>
                        </tr>
                    </table>
        """

    async def send_response_received_email(self, to: str, first_name: str, project_name: str, project_id: int) -> bool:
        """Автору проекта: поступил новый отклик."""
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        На ваш проект «{project_name}» поступил новый отклик. Загляните на страницу проекта,
                        чтобы рассмотреть кандидата.
                    </p>
        """
        body += self._action_button(f"{settings.FRONTEND_URL}/app/project?id={project_id}", "Открыть проект")
        html = self._wrap(body, "Новый отклик на проект")
        return await self.send_html(to, f"Новый отклик на проект — {_BRAND}", html)

    async def send_invitation_received_email(
        self, to: str, first_name: str, project_name: str, vacancy_title: str | None = None
    ) -> bool:
        """Участнику: автор пригласил его в проект."""
        role_line = f" на роль «{vacancy_title}»" if vacancy_title else ""
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        Вас пригласили в проект «{project_name}»{role_line}. Приглашение ждёт вашего ответа в профиле.
                    </p>
        """
        body += self._action_button(f"{settings.FRONTEND_URL}/app/profile?tab=responses", "Ответить на приглашение")
        html = self._wrap(body, "Вам пришло приглашение в проект")
        return await self.send_html(to, f"Приглашение в проект — {_BRAND}", html)

    async def send_response_accepted_email(
        self, to: str, first_name: str, project_name: str, vacancy_title: str | None = None
    ) -> bool:
        """Участнику: его отклик принят, нужно подтвердить вступление."""
        role_line = f" на роль «{vacancy_title}»" if vacancy_title else ""
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        Автор принял ваш отклик на проект «{project_name}»{role_line}. Подтвердите участие, чтобы попасть в команду.
                    </p>
        """
        body += self._action_button(f"{settings.FRONTEND_URL}/app/profile?tab=responses", "Подтвердить участие")
        html = self._wrap(body, "Ваш отклик принят")
        return await self.send_html(to, f"Ваш отклик принят — {_BRAND}", html)

    async def send_response_confirmed_email(
        self, to: str, first_name: str, project_name: str, project_id: int, vacancy_title: str | None = None
    ) -> bool:
        """Автору проекта: участник подтвердил вступление."""
        role_line = f" на роль «{vacancy_title}»" if vacancy_title else ""
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        Участник подтвердил вступление в проект «{project_name}»{role_line}. Команда укомплектована чуть ближе к цели.
                    </p>
        """
        body += self._action_button(f"{settings.FRONTEND_URL}/app/project?id={project_id}", "Открыть проект")
        html = self._wrap(body, "Новый участник в проекте")
        return await self.send_html(to, f"Новый участник — {_BRAND}", html)

    async def send_response_rejected_email(self, to: str, first_name: str, project_name: str) -> bool:
        """Участнику: его отклик отклонён."""
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        К сожалению, автор пока не готов взять вас в проект «{project_name}». Не расстраивайтесь — вас ждут другие команды.
                    </p>
        """
        html = self._wrap(body, "Ваш отклик отклонён")
        return await self.send_html(to, f"Отклик отклонён — {_BRAND}", html)

    async def send_invitation_accepted_email(
        self, to: str, first_name: str, project_name: str, project_id: int, vacancy_title: str | None = None
    ) -> bool:
        """Автору проекта: участник принял приглашение."""
        role_line = f" на роль «{vacancy_title}»" if vacancy_title else ""
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        Участник принял приглашение в проект «{project_name}»{role_line} и стал частью команды.
                    </p>
        """
        body += self._action_button(f"{settings.FRONTEND_URL}/app/project?id={project_id}", "Открыть проект")
        html = self._wrap(body, "Приглашение принято")
        return await self.send_html(to, f"Приглашение принято — {_BRAND}", html)

    async def send_invitation_rejected_email(
        self, to: str, first_name: str, project_name: str, project_id: int
    ) -> bool:
        """Автору проекта: участник отклонил приглашение."""
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        Участник отклонил приглашение в проект «{project_name}». Возможно, стоит поискать кандидатов ещё.
                    </p>
        """
        body += self._action_button(f"{settings.FRONTEND_URL}/app/project?id={project_id}", "Открыть проект")
        html = self._wrap(body, "Приглашение отклонено")
        return await self.send_html(to, f"Приглашение отклонено — {_BRAND}", html)

    #   === Канбан-доска ===

    _CHANGE_LABELS: ClassVar[dict[str, str]] = {
        "title": "название",
        "description": "описание",
        "priority": "приоритет",
        "due_date": "срок выполнения",
        "tags": "теги",
        "assignees": "ответственные",
        "is_completed": "статус выполнения",
    }

    async def send_task_created_email(
        self, to: str, first_name: str, task_title: str, project_name: str, project_id: int
    ) -> bool:
        """Получателю: создана новая задача на канбан-доске проекта."""
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        На доске проекта «{project_name}» создана задача «{task_title}».
                        Загляните на доску, чтобы не упустить детали.
                    </p>
        """
        body += self._action_button(f"{settings.FRONTEND_URL}/app/project?id={project_id}", "Открыть доску")
        html = self._wrap(body, "Новая задача на доске")
        return await self.send_html(to, f"Новая задача — {_BRAND}", html)

    async def send_task_updated_email(
        self,
        to: str,
        first_name: str,
        task_title: str,
        project_name: str,
        project_id: int,
        *,
        changes: list[str],
    ) -> bool:
        """Получателю: задача обновлена."""
        changes_text = ", ".join(self._CHANGE_LABELS.get(ch, ch) for ch in changes) or "поля задачи"
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        В задаче «{task_title}» проекта «{project_name}» изменено: {changes_text}.
                    </p>
        """
        body += self._action_button(f"{settings.FRONTEND_URL}/app/project?id={project_id}", "Открыть доску")
        html = self._wrap(body, "Задача обновлена")
        return await self.send_html(to, f"Задача обновлена — {_BRAND}", html)

    async def send_task_moved_email(
        self,
        to: str,
        first_name: str,
        task_title: str,
        project_name: str,
        project_id: int,
        *,
        from_column: str,
        to_column: str,
    ) -> bool:
        """Получателю: задача перемещена между колонками."""
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        Задача «{task_title}» в проекте «{project_name}» перемещена
                        из колонки «{from_column}» в колонку «{to_column}».
                    </p>
        """
        body += self._action_button(f"{settings.FRONTEND_URL}/app/project?id={project_id}", "Открыть доску")
        html = self._wrap(body, "Задача перемещена")
        return await self.send_html(to, f"Задача перемещена — {_BRAND}", html)

    async def send_task_deleted_email(
        self, to: str, first_name: str, task_title: str, project_name: str, project_id: int
    ) -> bool:
        """Получателю: задача удалена."""
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        Задача «{task_title}» была удалена с доски проекта «{project_name}».
                    </p>
        """
        body += self._action_button(f"{settings.FRONTEND_URL}/app/project?id={project_id}", "Открыть доску")
        html = self._wrap(body, "Задача удалена")
        return await self.send_html(to, f"Задача удалена — {_BRAND}", html)

    async def send_subtask_created_email(
        self,
        to: str,
        first_name: str,
        task_title: str,
        project_name: str,
        project_id: int,
        *,
        subtask_title: str,
    ) -> bool:
        """Получателю: добавлена подзадача."""
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        В задачу «{task_title}» проекта «{project_name}» добавлена подзадача «{subtask_title}».
                    </p>
        """
        body += self._action_button(f"{settings.FRONTEND_URL}/app/project?id={project_id}", "Открыть доску")
        html = self._wrap(body, "Новая подзадача")
        return await self.send_html(to, f"Новая подзадача — {_BRAND}", html)

    async def send_subtask_updated_email(
        self,
        to: str,
        first_name: str,
        task_title: str,
        project_name: str,
        project_id: int,
        *,
        subtask_title: str,
        completed: bool | None = None,
    ) -> bool:
        """Получателю: подзадача обновлена / переключён статус выполнения."""
        if completed is not None:
            status = "выполнена" if completed else "возобновлена"
            detail = f"Подзадача «{subtask_title}» в задаче «{task_title}» проекта «{project_name}» теперь {status}."
        else:
            detail = f"Подзадача «{subtask_title}» в задаче «{task_title}» проекта «{project_name}» была изменена."
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">{detail}</p>
        """
        body += self._action_button(f"{settings.FRONTEND_URL}/app/project?id={project_id}", "Открыть доску")
        html = self._wrap(body, "Подзадача обновлена")
        return await self.send_html(to, f"Подзадача обновлена — {_BRAND}", html)

    async def send_subtask_deleted_email(
        self,
        to: str,
        first_name: str,
        task_title: str,
        project_name: str,
        project_id: int,
        *,
        subtask_title: str,
    ) -> bool:
        """Получателю: подзадача удалена."""
        body = f"""
                    <p style="margin:0 0 16px 0;font-size:16px;line-height:1.5;color:{_TEXT};">Здравствуйте, {first_name}!</p>
                    <p style="margin:0 0 24px 0;font-size:16px;line-height:1.5;color:{_MUTED};">
                        Подзадача «{subtask_title}» была удалена из задачи «{task_title}» проекта «{project_name}».
                    </p>
        """
        body += self._action_button(f"{settings.FRONTEND_URL}/app/project?id={project_id}", "Открыть доску")
        html = self._wrap(body, "Подзадача удалена")
        return await self.send_html(to, f"Подзадача удалена — {_BRAND}", html)
