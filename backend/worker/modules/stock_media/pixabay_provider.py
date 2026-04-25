from __future__ import annotations

import structlog

from app.config import settings
from worker.modules.base import MediaAsset
from worker.modules.stock_media.base import AbstractStockProvider

logger = structlog.get_logger(__name__)

PIXABAY_SEARCH_URL = "https://pixabay.com/api/videos/"


class PixabayProvider(AbstractStockProvider):
    """Pixabay stock video provider. Returns empty list + logs warning if no API key."""

    def fetch(self, query: str, count: int, output_dir: str) -> list[MediaAsset]:
        if not settings.PIXABAY_API_KEY:
            logger.warning("pixabay_no_api_key", hint="Set PIXABAY_API_KEY in .env")
            return []

        import httpx
        from pathlib import Path

        params = {
            "key": settings.PIXABAY_API_KEY,
            "q": query,
            "per_page": min(count, 20),
            "video_type": "film",
        }

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(PIXABAY_SEARCH_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("pixabay_fetch_error", error=str(exc))
            return []

        assets: list[MediaAsset] = []
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        for hit in data.get("hits", [])[:count]:
            videos = hit.get("videos", {})
            # Prefer "small" size for speed
            chosen = videos.get("small") or videos.get("medium") or videos.get("large")
            if not chosen:
                continue
            file_url = chosen.get("url")
            if not file_url:
                continue

            dest = out / f"pixabay_{hit['id']}.mp4"
            try:
                with httpx.Client(timeout=60) as dl:
                    with dl.stream("GET", file_url) as r:
                        with open(dest, "wb") as f:
                            for chunk in r.iter_bytes(65536):
                                f.write(chunk)
                assets.append(MediaAsset(
                    path=str(dest),
                    source="pixabay",
                    width=chosen.get("width", 0),
                    height=chosen.get("height", 0),
                    duration=float(hit.get("duration", 0)),
                    metadata={"id": hit["id"]},
                ))
            except Exception as exc:
                logger.warning("pixabay_download_error", url=file_url, error=str(exc))

        return assets
