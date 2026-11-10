from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from src.core.exceptions import PermissionError
from src.model.project import ProjectStage, ProjectType
from src.repository.stage_repository import ProjectTypeRepository
from src.schema.stage import ProjectTypeCreate, ProjectTypeFull, ProjectTypeUpdate
from src.services.stage_service import ProjectStageService


@pytest.mark.parametrize("kind", [None, "product", "technical_integration", "research"])
def test_create_mapping_schema(kind):
    data = ProjectTypeCreate(name="Курсовой проект", assessment_kind=kind)
    assert data.assessment_kind == kind
    assert ProjectTypeFull(id=1, **data.model_dump()).assessment_kind == kind


def test_omitted_category_does_not_default_to_product():
    assert ProjectTypeCreate(name="Курсовой проект").assessment_kind is None
    assert ProjectTypeFull(id=1, name="Курсовой проект").assessment_kind is None


@pytest.mark.parametrize("schema", [ProjectTypeCreate, ProjectTypeUpdate])
@pytest.mark.parametrize("kind", ["other", "", "Product", 1])
def test_invalid_mapping_is_rejected(schema, kind):
    with pytest.raises(ValidationError):
        schema(name="Курсовой проект", assessment_kind=kind)


def test_update_distinguishes_omission_and_null():
    assert ProjectTypeUpdate(name="Новое имя").model_dump(exclude_unset=True) == {"name": "Новое имя"}
    assert ProjectTypeUpdate(assessment_kind=None).model_dump(exclude_unset=True) == {"assessment_kind": None}


@pytest.fixture
def components():
    # Only database I/O is replaced; repository schema handling and service permissions run unchanged.
    session = Mock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock(return_value=SimpleNamespace(role=SimpleNamespace(name="teacher")))
    repo = ProjectTypeRepository(SimpleNamespace(session=session))
    return session, repo, ProjectStageService(repo, Mock())


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [None, "research"])
async def test_create_roundtrip(components, kind):
    session, _, service = components

    def assign_id(obj):
        obj.id = 42

    session.add.side_effect = assign_id
    result = await service.create_project_type(ProjectTypeCreate(name="Курсовой проект", assessment_kind=kind), None, 7)
    assert (result.id, result.name, result.assessment_kind, result.stages) == (42, "Курсовой проект", kind, [])


@pytest.mark.asyncio
async def test_get_and_list_preserve_mapping_and_stages(components):
    session, _, service = components
    stage = ProjectStage(id=9, name="Защита", order=0, requires_approval=True, visible_to_participants=True)
    ptype = ProjectType(id=42, name="Курсовой проект", assessment_kind="technical_integration", stages=[stage])
    response = Mock()
    response.scalar_one_or_none.return_value = ptype
    response.scalars.return_value.all.return_value = [ptype]
    session.execute.return_value = response
    for result in [await service.get_project_type(42), *(await service.list_project_types())]:
        assert (result.id, result.name, result.assessment_kind) == (42, "Курсовой проект", "technical_integration")
        assert [(s.id, s.name, s.order) for s in result.stages] == [(9, "Защита", 0)]


@pytest.mark.asyncio
async def test_update_omission_preserves_then_null_clears(components):
    session, _, service = components
    ptype = ProjectType(id=42, name="Курсовой проект", workspace_id=3, assessment_kind="research", stages=[])
    response = Mock()
    response.scalar_one_or_none.return_value = ptype
    session.execute.return_value = response
    unchanged = await service.update_project_type(42, 3, ProjectTypeUpdate(description="Описание"), 7)
    assert unchanged.assessment_kind == "research"
    cleared = await service.update_project_type(42, 3, ProjectTypeUpdate(assessment_kind=None), 7)
    assert cleared.assessment_kind is None
    changed = await service.update_project_type(42, 3, ProjectTypeUpdate(assessment_kind="product"), 7)
    assert changed.assessment_kind == "product"
    assert (ptype.id, ptype.name, ptype.workspace_id) == (42, "Курсовой проект", 3)


@pytest.mark.asyncio
@pytest.mark.parametrize("denial", ["wrong_workspace", "student"])
async def test_mapping_update_keeps_permissions(components, denial):
    session, _, service = components
    ptype = ProjectType(id=42, name="Курсовой проект", workspace_id=3, assessment_kind="research")
    response = Mock()
    response.scalar_one_or_none.return_value = ptype
    response.first.return_value = None
    session.execute.return_value = response
    if denial == "student":
        session.get.return_value = SimpleNamespace(role=SimpleNamespace(name="student"))
    with pytest.raises(PermissionError):
        await service.update_project_type(
            42, 8 if denial == "wrong_workspace" else 3, ProjectTypeUpdate(assessment_kind="product"), 7
        )
    assert ptype.assessment_kind == "research"
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [None, "technical_integration"])
async def test_copy_system_type_preserves_assessment_kind(components, kind):
    session, repo, _ = components
    template = ProjectType(id=1, name="Курсовой проект", description="Шаблон", assessment_kind=kind, stages=[])
    templates = Mock()
    templates.scalars.return_value.all.return_value = [template]
    absent = Mock()
    absent.scalar_one_or_none.return_value = None
    session.execute.side_effect = [templates, absent]
    created = []

    def persist(obj):
        obj.id = 99
        created.append(obj)

    session.add.side_effect = persist
    assert await repo.copy_system_types_to_workspace(3) == 1
    assert len(created) == 1
    assert (created[0].workspace_id, created[0].name, created[0].description, created[0].assessment_kind) == (
        3,
        "Курсовой проект",
        "Шаблон",
        kind,
    )
