from __future__ import annotations

import subprocess
from pathlib import Path

import structlog

from app.config import settings
from worker.modules.base import MediaAsset
from worker.modules.stock_media.base import AbstractStockProvider

logger = structlog.get_logger(__name__)

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


class LocalMediaProvider(AbstractStockProvider):
    """
    Serves video files from a local asset library directory.
    Falls back to generating coloured rectangle placeholders via FFmpeg
    when no matching assets are available.
    """

    def __init__(self, library_path: str | None = None) -> None:
        self._library = Path(library_path or settings.STORAGE_PATH) / "assets"

    def fetch(self, query: str, count: int, output_dir: str) -> list[MediaAsset]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        local_files = [
            f for f in self._library.rglob("*")
            if f.suffix.lower() in SUPPORTED_EXTENSIONS
        ] if self._library.exists() else []

        assets: list[MediaAsset] = []
        for f in local_files[:count]:
            assets.append(MediaAsset(path=str(f), source="local"))

        # Generate placeholder coloured clips for any remaining slots
        needed = count - len(assets)
        colours = ["0x2c3e50", "0x8e44ad", "0x16a085"]
        for i in range(needed):
            colour = colours[i % len(colours)]
            dest = out / f"placeholder_{i}.mp4"
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-f", "lavfi",
                        "-i", f"color=c={colour}:size=1080x1920:rate=30:duration=10",
                        "-c:v", "libx264",
                        "-pix_fmt", "yuv420p",
                        str(dest),
                    ],
                    capture_output=True,
                    check=True,
                )
                assets.append(MediaAsset(
                    path=str(dest),
                    source="local_placeholder",
                    width=1080,
                    height=1920,
                    duration=10.0,
                ))
            except Exception as exc:
                logger.warning("placeholder_clip_failed", error=str(exc))

        return assets
