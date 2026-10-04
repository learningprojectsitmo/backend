"""Политика доставки уведомлений: какой канал срабатывает на какой тип.

Живёт отдельно от `push_payload` (там — как собирается текст) и отдельно от
моделей, потому что это продуктовое решение, а не структура данных.

Почему так: уведомления о движении задач в канбане создаются десятками за
день и на каждом раньше уходило письмо. Почта для такого — не канал: её не
видно на телефоне без уведомлений, и человек быстро перестаёт её открывать,
а вместе с ней перестаёт читать и важные письма про приглашения. Поэтому
важные события идут и в почту, и в push, а канбан — только в push.
"""

from __future__ import annotations

from typing import Final

from src.model.notification import NotificationType

#: Типы, на которые уходит письмо. Push получают все типы.
EMAIL_TYPES: Final = frozenset(
    {
        NotificationType.response_received,
        NotificationType.response_accepted,
        NotificationType.response_rejected,
        NotificationType.response_confirmed,
        NotificationType.invitation_received,
        NotificationType.invitation_accepted,
        NotificationType.invitation_rejected,
        NotificationType.stage_approval_required,
    }
)

#: Важные события: их телефон будит, они же дублируются письмом. Остальное
#: доставляется тихо — в шторке, без звука.
HIGH_PRIORITY_TYPES: Final = EMAIL_TYPES


def needs_email(type: NotificationType) -> bool:
    """Стоит ли дублировать уведомление письмом."""
    return type in EMAIL_TYPES


def is_high_priority(type: NotificationType) -> bool:
    """Будить ли телефон."""
    return type in HIGH_PRIORITY_TYPES
