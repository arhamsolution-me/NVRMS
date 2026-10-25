"""Pydantic schemas for Roles, Permissions, and RolePermission toggles."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class PermissionResponse(BaseModel):
    """Permission detail schema."""

    id: uuid.UUID
    code: str
    name: str
    module: str
    description: str | None = None

    model_config = {"from_attributes": True}


class RolePermissionItem(BaseModel):
    """Permission item within a role matrix."""

    permission_id: uuid.UUID
    code: str
    name: str
    module: str
    is_granted: bool


class RoleCreate(BaseModel):
    """Schema for creating a new role."""

    name: str = Field(min_length=2, max_length=100)
    description: str | None = None


class RoleUpdate(BaseModel):
    """Schema for updating an existing role."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = None


class RoleResponse(BaseModel):
    """Role response schema."""

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    name: str
    description: str | None
    is_system: bool

    model_config = {"from_attributes": True}


class RolePermissionToggleRequest(BaseModel):
    """Request to toggle a permission on or off for a role."""

    permission_code: str
    is_granted: bool
