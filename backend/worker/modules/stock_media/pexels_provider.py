from __future__ import annotations

import structlog
from concurrent.futures import ThreadPoolExecutor

from app.config import settings
from worker.modules.base import MediaAsset
from worker.modules.stock_media.base import AbstractStockProvider

logger = structlog.get_logger(__name__)

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"


class PexelsProvider(AbstractStockProvider):
    """Pexels stock video provider. Returns empty list + logs warning if no API key."""

    def fetch(self, query: str, count: int, output_dir: str) -> list[MediaAsset]:
        if not settings.PEXELS_API_KEY:
            logger.warning("pexels_no_api_key", hint="Set PEXELS_API_KEY in .env")
            return []

        import httpx
        from pathlib import Path

        headers = {"Authorization": settings.PEXELS_API_KEY}
        params = {"query": query, "per_page": min(count, 15), "orientation": "portrait"}

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(PEXELS_SEARCH_URL, headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("pexels_fetch_error", error=str(exc))
            return []

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # Build list of (video_metadata, file_url, dest) for parallel download.
        tasks: list[tuple[dict, str, Path]] = []
        for video in data.get("videos", [])[:count]:
            video_files = sorted(video.get("video_files", []), key=lambda f: f.get("file_size", 999999))
            if not video_files:
                continue
            file_url = video_files[0].get("link")
            if not file_url:
                continue
            dest = out / f"pexels_{video['id']}.mp4"
            tasks.append((video, file_url, dest))

        if not tasks:
            return []

        def _download(task: tuple[dict, str, Path]) -> MediaAsset | None:
            video, file_url, dest = task
            try:
                with httpx.Client(timeout=60) as dl:
                    with dl.stream("GET", file_url) as r:
                        with open(dest, "wb") as f:
                            for chunk in r.iter_bytes(65536):
                                f.write(chunk)
                return MediaAsset(
                    path=str(dest),
                    source="pexels",
                    width=video.get("width", 0),
                    height=video.get("height", 0),
                    duration=float(video.get("duration", 0)),
                    metadata={"id": video["id"]},
                )
            except Exception as exc:
                logger.warning("pexels_download_error", url=file_url, error=str(exc))
                return None

        max_workers = max(1, min(settings.PIPELINE_MAX_WORKERS, len(tasks)))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(_download, tasks))

        return [r for r in results if r is not None]
