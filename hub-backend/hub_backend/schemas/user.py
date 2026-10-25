"""Pydantic schemas for User management and User Scopes."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from hub_backend.schemas.auth import UserScopeSchema


class UserCreate(BaseModel):
    """Schema for creating a new user account."""

    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=150)
    role_id: uuid.UUID
    is_active: bool = True
    scopes: list[ScopeAssignment] = []


class ScopeAssignment(BaseModel):
    """Scope assignment for a user."""

    scope_type: str = Field(pattern="^(global|tenant|province|city|area|site)$")
    scope_id: uuid.UUID


class UserUpdate(BaseModel):
    """Schema for updating a user account."""

    full_name: str | None = None
    role_id: uuid.UUID | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)
    scopes: list[ScopeAssignment] | None = None


class UserResponse(BaseModel):
    """User response schema."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str
    role_id: uuid.UUID
    is_active: bool
    is_superuser: bool
    totp_enabled: bool
    scopes: list[UserScopeSchema]

    model_config = {"from_attributes": True}
