from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import structlog

from app.config import settings
from worker.modules.base import UploadResult
from worker.modules.uploader.base import AbstractUploader

logger = structlog.get_logger(__name__)


class LocalExporter(AbstractUploader):
    """Copies the finished video to the outputs directory and returns an API download URL."""

    def __init__(self, output_dir: str | None = None) -> None:
        self._output_dir = Path(output_dir or settings.STORAGE_PATH) / "outputs"

    def upload(self, video_path: str, metadata: dict[str, Any]) -> UploadResult:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        src = Path(video_path)

        if not src.exists():
            logger.error("local_export_file_missing", path=video_path)
            return UploadResult(url="", platform="local", skipped=True, skip_reason="source file missing")

        dest = self._output_dir / src.name

        # Only copy if source != destination
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)

        # Return an API download URL — never a raw filesystem path.
        # dest.stem is the job UUID (outputs are stored as {job_id}.mp4).
        job_id = dest.stem
        url = f"/api/v1/jobs/{job_id}/download"
        logger.info("local_export_complete", url=url)
        return UploadResult(url=url, platform="local")
