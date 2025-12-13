from __future__ import annotations

from pydantic import BaseModel


class Token(BaseModel):
    """Схема токена для аутентификации"""

    access_token: str
    token_type: str
