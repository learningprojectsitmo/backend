from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.uow import SqlAlchemyUoW


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["commit", "rollback"])
async def test_session_is_closed_even_when_transaction_exit_fails(phase):
    uow = SqlAlchemyUoW()
    uow.session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), close=AsyncMock())
    getattr(uow.session, phase).side_effect = RuntimeError("transaction failed")
    with pytest.raises(RuntimeError, match="transaction failed"):
        await uow.__aexit__(None, None if phase == "commit" else ValueError("request failed"), None)
    uow.session.close.assert_awaited_once()
