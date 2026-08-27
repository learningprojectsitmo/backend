from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib

from src.core.config import settings
from src.core.logging_config import get_logger


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

    async def send_signup_code(self, to: str, code: int) -> bool:
        html = (
            f"<h2>Подтверждение регистрации</h2>"
            f"<p>Ваш код подтверждения:</p>"
            f"<h1 style='letter-spacing:4px'>{code}</h1>"
            f"<p>Код действует 5 минут.</p>"
        )
        return await self.send_html(to, "Код подтверждения регистрации", html)

    async def send_password_reset(self, to: str, reset_url: str) -> bool:
        html = (
            f"<h2>Сброс пароля</h2>"
            f"<p>Для сброса пароля перейдите по ссылке:</p>"
            f"<p><a href='{reset_url}'>Сбросить пароль</a></p>"
            f"<p>Ссылка действует 1 час.</p>"
        )
        return await self.send_html(to, "Сброс пароля", html)
