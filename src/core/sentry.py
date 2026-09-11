from __future__ import annotations

import sentry_sdk

from src.core.config import settings


def setup_sentry() -> None:
    """Инициализация Sentry SDK (совместим с GlitchTip)"""
    if not settings.SENTRY_DSN:
        return

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        auto_session_tracking=False,
        send_default_pii=True,
    )
