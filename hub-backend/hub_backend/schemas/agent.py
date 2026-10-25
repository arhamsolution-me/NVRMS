"""Pydantic schemas for Agent management and enrolment."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EnrolmentTokenCreate(BaseModel):
    """Request to generate an agent enrolment token."""

    name: str = Field(min_length=2, max_length=150)


class EnrolmentTokenResponse(BaseModel):
    """Response containing the plaintext enrolment code (shown once)."""

    id: uuid.UUID
    name: str
    code: str
    expires_at: datetime


class AgentEnrolRequest(BaseModel):
    """Payload sent by edge agent to claim an enrolment code."""

    enrolment_code: str = Field(min_length=6)
    name: str | None = None
    version: str | None = None


class AgentEnrolResponse(BaseModel):
    """Credentials issued to the enrolled agent."""

    agent_id: uuid.UUID
    agent_token: str
    name: str
    hub_url: str


class AgentResponse(BaseModel):
    """Agent entity detail schema."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    is_active: bool
    version: str | None
    status: str
    is_online: bool = False
    last_heartbeat_at: datetime | None
    last_ip_address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentCommandRequest(BaseModel):
    """Request schema for dispatching an arbitrary whitelisted command to an agent."""

    command: str
    payload: dict[str, Any] = {}
    timeout_seconds: float = 10.0
