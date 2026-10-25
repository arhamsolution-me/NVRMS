"""Pydantic schemas for NVR and Camera resources."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DiscoveredChannel(BaseModel):
    channel_number: int
    name: str
    main_stream_url: str
    sub_stream_url: str | None = None
    codec: str = "h264"
    resolution: str = "1920x1080"
    fps: int = 25
    status: str = "online"


class NVRProbeRequest(BaseModel):
    agent_id: uuid.UUID
    ip: str = Field(..., description="Target NVR IP address")
    port: int = Field(default=554, ge=1, le=65535)
    username: str = Field(default="admin")
    password: str = Field(default="")
    brand: str = Field(default="auto", description="auto, hikvision, dahua, uniview, axis, generic")


class NVRProbeResponse(BaseModel):
    status: str
    brand: str
    model: str | None = None
    serial_number: str | None = None
    mac_address: str | None = None
    ip: str
    port: int
    channel_count: int
    channels: list[DiscoveredChannel] = []
    diagnostics: dict[str, Any] = {}


class NVRCreateRequest(BaseModel):
    agent_id: uuid.UUID
    site_id: uuid.UUID | None = None
    name: str = Field(..., min_length=1, max_length=150)
    brand: str = Field(default="generic", max_length=50)
    model: str | None = Field(default=None, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    mac_address: str | None = Field(default=None, max_length=50)
    ip_address: str = Field(..., min_length=7, max_length=45)
    port: int = Field(default=554, ge=1, le=65535)
    username: str = Field(default="admin")
    password: str = Field(default="")
    channels: list[DiscoveredChannel] = []


class NVRUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    site_id: uuid.UUID | None = None
    status: str | None = None


class CameraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    site_id: uuid.UUID | None = None
    nvr_id: uuid.UUID
    channel_number: int
    name: str
    main_stream_url: str
    sub_stream_url: str | None = None
    codec: str
    resolution: str
    fps: int
    is_active: bool
    status: str
    created_at: datetime


class NVRResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    site_id: uuid.UUID | None = None
    agent_id: uuid.UUID
    name: str
    brand: str
    model: str | None = None
    serial_number: str | None = None
    mac_address: str | None = None
    ip_address: str
    port: int
    channel_count: int
    status: str
    created_at: datetime
    cameras: list[CameraResponse] = []
