"""Pydantic schemas for Location hierarchy nodes."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ProvinceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=50)


class ProvinceResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    code: str

    model_config = {"from_attributes": True}


class CityCreate(BaseModel):
    province_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=50)


class CityResponse(BaseModel):
    id: uuid.UUID
    province_id: uuid.UUID
    name: str
    code: str

    model_config = {"from_attributes": True}


class AreaCreate(BaseModel):
    city_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=50)


class AreaResponse(BaseModel):
    id: uuid.UUID
    city_id: uuid.UUID
    name: str
    code: str

    model_config = {"from_attributes": True}


class SiteCreate(BaseModel):
    area_id: uuid.UUID
    name: str = Field(min_length=1, max_length=150)
    code: str = Field(min_length=1, max_length=50)
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class SiteResponse(BaseModel):
    id: uuid.UUID
    area_id: uuid.UUID
    name: str
    code: str
    address: str | None
    latitude: float | None
    longitude: float | None

    model_config = {"from_attributes": True}
