from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import NotFoundError, PermissionError
from src.schema.project_type_question import QuestionListReplace
from src.services.project_type_question_service import ProjectTypeQuestionService
from src.services.question_template_service import QuestionTemplateService


@pytest.mark.parametrize(
    ("global_role", "membership", "local_role", "author", "status"),
    [
        ("admin", False, None, False, 200),
        ("teacher", True, "member", False, 200),
        ("member", True, "teacher", False, 200),
        ("member", True, "admin", False, 200),
        ("teacher", False, None, True, 200),
        ("teacher", False, None, False, 404),
        ("member", True, "manager", False, 403),
        ("manager", True, "manager", True, 403),
        ("member", True, None, False, 403),
        ("member", False, None, False, 404),
    ],
)
@pytest.mark.asyncio
async def test_write_scope_and_role_matrix(global_role, membership, local_role, author, status):
    repo = SimpleNamespace(
        get_question_lock=AsyncMock(return_value=None),
        get_workspace=AsyncMock(return_value=SimpleNamespace(author_id=7 if author else 8)),
        get_type=AsyncMock(return_value=SimpleNamespace(id=42, workspace_id=3)),
        get_membership_role=AsyncMock(return_value=(membership, local_role)),
        replace_questions=AsyncMock(return_value=[]),
        list_questions=AsyncMock(return_value=[]),
    )
    user = SimpleNamespace(id=7, role=SimpleNamespace(name=global_role))
    service = ProjectTypeQuestionService(repo, QuestionTemplateService())
    if status != 200:
        error = NotFoundError if status == 404 else PermissionError
        with pytest.raises(error):
            await service.replace_questions(3, 42, QuestionListReplace(questions=[]), user)
        repo.replace_questions.assert_not_awaited()
    else:
        result = await service.replace_questions(3, 42, QuestionListReplace(questions=[]), user)
        assert result.project_type_id == 42
        assert result.questions == []
        assert (result.min_score, result.max_score) == (1, 5)


@pytest.mark.asyncio
async def test_null_role_member_can_read_but_foreign_type_is_not_found():
    repo = SimpleNamespace(
        get_question_lock=AsyncMock(return_value=None),
        get_workspace=AsyncMock(return_value=SimpleNamespace(author_id=8)),
        get_type=AsyncMock(return_value=SimpleNamespace(id=42, workspace_id=3)),
        get_membership_role=AsyncMock(return_value=(True, None)),
        list_questions=AsyncMock(return_value=[]),
    )
    service = ProjectTypeQuestionService(repo, QuestionTemplateService())
    user = SimpleNamespace(id=7, role=SimpleNamespace(name="member"))
    assert (await service.get_questions(3, 42, user)).questions == []
    repo.get_type.return_value = None
    with pytest.raises(NotFoundError):
        await service.get_questions(3, 42, user)
