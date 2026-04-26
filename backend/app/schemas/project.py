from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ProjectBase(BaseModel):
    name: str
    description: str | None = None
    brand_settings: dict[str, Any] | None = None
    watermark_path: str | None = None
    watermark_asset_id: int | None = None
    background_music_asset_id: int | None = None
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
    description: str | None = None
    brand_settings: dict[str, Any] | None = None
    watermark_path: str | None = None
    watermark_asset_id: int | None = None
    background_music_asset_id: int | None = None
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
    # job_count is not stored in the DB but defaults to 0 so the frontend
    # card renders without crashing; a future improvement can populate it.
    job_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    page: int
    size: int
    pages: int = 1
