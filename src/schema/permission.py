from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PermissionCreate(BaseModel):
    name: str
    model_config = ConfigDict(from_attributes=True)


class PermissionFull(PermissionCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class PermissionMatrixElement(BaseModel):
    create: bool
    read: bool
    update: bool  # use update instead of write
    delete: bool


class PermissionMatrix(BaseModel):
    permissions_matrix: dict[str, PermissionMatrixElement]
