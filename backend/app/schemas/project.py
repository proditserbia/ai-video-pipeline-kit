from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ProjectBase(BaseModel):
    name: str
    brand_settings: dict[str, Any] | None = None
    watermark_path: str | None = None
    fonts: list[str] | None = None
    colors: dict[str, str] | None = None
    default_output_format: str = "mp4"
    enabled_platforms: list[str] | None = None
    default_caption_style: dict[str, Any] | None = None
    default_voice: str | None = None
    storage_settings: dict[str, Any] | None = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = None
    brand_settings: dict[str, Any] | None = None
    watermark_path: str | None = None
    fonts: list[str] | None = None
    colors: dict[str, str] | None = None
    default_output_format: str | None = None
    enabled_platforms: list[str] | None = None
    default_caption_style: dict[str, Any] | None = None
    default_voice: str | None = None
    storage_settings: dict[str, Any] | None = None


class ProjectResponse(ProjectBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
