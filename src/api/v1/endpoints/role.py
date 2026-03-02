from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.container import get_role_service
from src.core.dependencies import get_current_user, setup_audit
from src.schema.role import RoleCreate, RoleFull, RoleListResponse, RoleUpdate, RolePermissionFull, RolePermissionCreate
from src.model.models import User
from src.services.role_service import RoleService

role_router = APIRouter(prefix="/roles", tags=["roles"])
role_permission_router = APIRouter(prefix="/role_permissions", tags=["roles"])

# TODO: permissions should be hardcoded, no create and delete


@role_permission_router.delete("/{permission_id}")
async def delete_permission(
    permission_id: int,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:

    try:
        await role_service.delete_role_permission(permission_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete permission: {e!s}",
        ) from e
    else:
        return {"message": "Role permission deleted successfully"}

@role_permission_router.post("/")
async def create_permission(
    role_permission_data: RolePermissionCreate,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(get_current_user),
) -> RolePermissionFull:

    try:
        role_permission = await role_service.create_role_permission(role_permission_data)
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
) -> list[RolePermissionFull]:
    result = await role_service.get_role_permissions(role_id=role_id)
    return result

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


''' I don't think roles should have update
@role_router.put("/{role_id}", response_model=RoleFull)
async def update_role(
    role_id: int,
    role_data: RoleUpdate,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(get_current_user),
    _audit=Depends(setup_audit),
) -> RoleFull:

    def _check_role_exists_or_raise_not_found() -> None:
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")

    try:
        role = await role_service.update(role_id, role_data)
        _check_role_exists_or_raise_not_found()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update role: {e!s}",
        ) from e
    else:
        return RoleFull.model_validate(role)
'''


@role_router.delete("/{role_id}")
async def delete_role(
    role_id: int,
    role_service: RoleService = Depends(get_role_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:

    try:
        role = await role_service.delete(role_id)
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
    # return await role_service.get_paginated(page=page, page_size=page_size)
    result = await role_service.get_paginated(page=page, page_size=page_size)
    try:
        # force validation to surface precise error
        RoleListResponse.model_validate(result)  # or parse_obj for pydantic v1
    except Exception as e:
        import traceback
        print("RESULT TYPE:", type(result))
        print("RESULT REPR:", repr(result))
        print("VALIDATION TRACEBACK:\n", traceback.format_exc())
        raise
    return result

