from __future__ import annotations

from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/token")

# Отдельная схема для публичных ручек: auto_error=False возвращает None вместо
# 401, когда заголовка Authorization нет. На oauth2_scheme опциональная
# аутентификация невозможна — FastAPI отдаёт 401 до входа в тело зависимости.
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/token", auto_error=False)
