from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import aiofiles

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.models.asset import Asset
from app.models.user import User
from app.schemas.asset import AssetResponse

router = APIRouter(prefix="/assets", tags=["assets"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mp3", ".wav", ".jpg", ".jpeg", ".png", ".gif"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


@router.get("", response_model=list[AssetResponse])
async def list_assets(
    project_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AssetResponse]:
    query = select(Asset)
    if project_id is not None:
        query = query.where(Asset.project_id == project_id)
    result = await db.execute(query)
    return [AssetResponse.model_validate(a) for a in result.scalars().all()]


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

    upload_dir = Path(settings.STORAGE_PATH) / "uploads"
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
        project_id=project_id,
        filename=safe_name,
        file_path=str(dest),
        file_type=ext.lstrip("."),
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
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
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
