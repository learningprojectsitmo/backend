from __future__ import annotations

import pytest

from src.schema.exam_queue import QueueReason


@pytest.mark.parametrize("reason", ["Причина", "  Проектор  "])
def test_reason_is_trimmed(reason):
    parsed = QueueReason(expected_version=1, reason=reason)
    assert parsed.reason == reason.strip()
