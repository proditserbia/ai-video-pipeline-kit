from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AssetBase(BaseModel):
    filename: str
    file_type: str
    mime_type: str | None = None
    source: str = "local"
    metadata_: dict[str, Any] | None = None


class AssetCreate(AssetBase):
    file_path: str
    project_id: int | None = None


class AssetResponse(AssetBase):
    id: int
    project_id: int | None
    file_path: str
    created_at: datetime

    model_config = {"from_attributes": True}
