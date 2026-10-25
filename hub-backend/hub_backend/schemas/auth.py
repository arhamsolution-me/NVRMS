"""Pydantic schemas for authentication and profile."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """User login request payload."""

    email: str = Field(min_length=3, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1)
    totp_code: str | None = None


class TokenResponse(BaseModel):
    """Token response on successful login or refresh."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserScopeSchema(BaseModel):
    """User scope information."""

    id: uuid.UUID
    scope_type: str
    scope_id: uuid.UUID

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    """Profile response for the /me endpoint."""

    id: uuid.UUID
    email: str
    full_name: str
    tenant_id: uuid.UUID
    role_id: uuid.UUID
    role_name: str
    is_superuser: bool
    totp_enabled: bool
    scopes: list[UserScopeSchema]
    permissions: list[str]

    model_config = {"from_attributes": True}


class TOTPSetupResponse(BaseModel):
    """Response containing TOTP secret and provisioning URI for authenticator apps."""

    secret: str
    provisioning_uri: str


class TOTPVerifyRequest(BaseModel):
    """Request to verify TOTP code and enable 2FA."""

    code: str = Field(min_length=6, max_length=6)
