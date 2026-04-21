from __future__ import annotations

import traceback

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.container import get_role_service
from src.core.dependencies import get_current_user
from src.model.models import User
from src.schema.permission import PermissionMatrix
from src.schema.role import RoleCreate, RoleFull, RoleListResponse
from src.services.role_service import RoleService

role_router = APIRouter(prefix="/roles", tags=["roles"])
role_permission_router = APIRouter(prefix="/role_permissions", tags=["roles"])


@role_permission_router.put("/{role_id}")
async def remap_role_permission(
    role_id: int,
    role_permission_matrix: PermissionMatrix,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(get_current_user),
) -> PermissionMatrix:
    try:
        role_permission = await role_service.remap_role_permission(role_id, role_permission_matrix)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create role permission: {e!s}",
        ) from e
    else:
        return role_permission


@role_permission_router.get("/{role_id}")
async def get_permissions(
    role_id: int,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(get_current_user),
) -> PermissionMatrix:
    return await role_service.get_role_permissions(role_id=role_id)


@role_router.post("/", response_model=RoleFull)
async def create_role(
    role_data: RoleCreate,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(get_current_user),
) -> RoleFull:
    role = await role_service.create(role_data)
    return RoleFull.model_validate(role)


@role_router.get("/{role_id}", response_model=RoleFull)
async def get_role(
    role_id: int,
    role_service: RoleService = Depends(get_role_service),
    _current_user: User = Depends(get_current_user),
) -> RoleFull:
    role = await role_service.get_by_id(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    return RoleFull.model_validate(role)


@role_router.delete("/{role_id}")
async def delete_role(
    role_id: int,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    try:
        await role_service.delete(role_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete role: {e!s}",
        ) from e
    else:
        return {"message": "Role deleted successfully"}


@role_router.get("/")
async def get_roles(
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(10, ge=1, le=100, description="Количество roles на странице"),
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(get_current_user),
) -> RoleListResponse:
    result = await role_service.get_paginated(page=page, page_size=page_size)
    try:
        # force validation to surface precise error
        RoleListResponse.model_validate(result)  # or parse_obj for pydantic v1
    except Exception:
        print("RESULT TYPE:", type(result))
        print("RESULT REPR:", repr(result))
        print("VALIDATION TRACEBACK:\n", traceback.format_exc())
        raise
    return result
