from __future__ import annotations

import math
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import aiofiles

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.models.asset import Asset
from app.models.user import User
from app.schemas.asset import AssetListResponse, AssetResponse

router = APIRouter(prefix="/assets", tags=["assets"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mp3", ".wav", ".jpg", ".jpeg", ".png", ".gif"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB

_EXT_TO_ASSET_TYPE: dict[str, str] = {
    "mp4": "video", "mov": "video", "avi": "video", "mkv": "video", "webm": "video",
    "mp3": "audio", "wav": "audio", "ogg": "audio", "aac": "audio", "flac": "audio",
    "jpg": "image", "jpeg": "image", "png": "image", "gif": "image", "webp": "image",
    "svg": "image", "bmp": "image",
}


def _derive_asset_type(ext: str) -> str:
    return _EXT_TO_ASSET_TYPE.get(ext.lower().lstrip("."), "other")


@router.get("", response_model=AssetListResponse)
async def list_assets(
    project_id: int | None = None,
    asset_type: str | None = None,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssetListResponse:
    if size < 1:
        size = 20
    query = select(Asset).where(Asset.user_id == current_user.id)
    count_query = select(func.count(Asset.id)).where(Asset.user_id == current_user.id)

    if project_id is not None:
        query = query.where(Asset.project_id == project_id)
        count_query = count_query.where(Asset.project_id == project_id)
    if asset_type is not None:
        query = query.where(Asset.asset_type == asset_type)
        count_query = count_query.where(Asset.asset_type == asset_type)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(query.offset((page - 1) * size).limit(size))
    assets = result.scalars().all()

    return AssetListResponse(
        items=[AssetResponse.model_validate(a) for a in assets],
        total=total,
        page=page,
        size=size,
        pages=max(1, math.ceil(total / size)),
    )


@router.post("/upload", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    file: UploadFile = File(...),
    project_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssetResponse:
    original_filename = file.filename or "upload"
    ext = Path(original_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File type '{ext}' not allowed. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    upload_dir = Path(settings.STORAGE_PATH) / "assets"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Prevent path traversal: store only the basename
    safe_name = Path(original_filename).name
    dest = upload_dir / safe_name

    # Ensure destination is within the storage directory
    try:
        dest.resolve().relative_to(Path(settings.STORAGE_PATH).resolve())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")

    bytes_written = 0
    async with aiofiles.open(dest, "wb") as out_file:
        while chunk := await file.read(64 * 1024):
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="File too large",
                )
            await out_file.write(chunk)

    asset = Asset(
        user_id=current_user.id,
        project_id=project_id,
        name=safe_name,
        filename=safe_name,
        file_path=str(dest),
        file_type=ext.lstrip("."),
        asset_type=_derive_asset_type(ext),
        file_size=bytes_written,
        mime_type=file.content_type,
        source="local",
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return AssetResponse.model_validate(asset)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_asset(
    asset_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.user_id == current_user.id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    path = Path(asset.file_path)
    # Safety: only delete files within storage directory
    try:
        path.resolve().relative_to(Path(settings.STORAGE_PATH).resolve())
        if path.exists():
            path.unlink()
    except ValueError:
        pass

    await db.delete(asset)
    await db.commit()
