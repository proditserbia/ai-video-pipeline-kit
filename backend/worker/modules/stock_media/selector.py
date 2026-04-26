from __future__ import annotations

import structlog

from app.config import settings
from worker.modules.base import MediaAsset

logger = structlog.get_logger(__name__)


class StockMediaSelector:
    """
    Select stock media clips using a priority chain:

    1. Pexels  – if ``PEXELS_API_KEY`` is set and returns results
    2. Pixabay – if ``PIXABAY_API_KEY`` is set and returns results
    3. Local assets – video files under ``STORAGE_PATH/assets``
    4. FFmpeg placeholder clips – generated on the fly (always succeeds)

    Steps 3 and 4 are handled by :class:`LocalMediaProvider`, which tries local
    files first and generates coloured placeholder clips for any remaining slots.
    """

    def fetch(
        self,
        query: str,
        count: int,
        output_dir: str,
    ) -> tuple[list[MediaAsset], str]:
        """
        Fetch *count* video clips relevant to *query*.

        Returns a ``(assets, provider_name)`` tuple where *provider_name* is one
        of ``"pexels"``, ``"pixabay"``, ``"local"``, or ``"placeholder"``.
        """
        # 1. Pexels
        if settings.PEXELS_API_KEY:
            from worker.modules.stock_media.pexels_provider import PexelsProvider

            assets = PexelsProvider().fetch(query, count, output_dir)
            if assets:
                logger.info("stock_media_provider_used", provider="pexels", clips=len(assets), query=query)
                return assets, "pexels"
            logger.warning("stock_media_pexels_empty", query=query)

        # 2. Pixabay
        if settings.PIXABAY_API_KEY:
            from worker.modules.stock_media.pixabay_provider import PixabayProvider

            assets = PixabayProvider().fetch(query, count, output_dir)
            if assets:
                logger.info("stock_media_provider_used", provider="pixabay", clips=len(assets), query=query)
                return assets, "pixabay"
            logger.warning("stock_media_pixabay_empty", query=query)

        # 3 + 4. Local assets with FFmpeg placeholder fallback
        from worker.modules.stock_media.local_provider import LocalMediaProvider

        assets = LocalMediaProvider().fetch(query, count, output_dir)
        # Determine whether any real local files were returned
        real_local = [a for a in assets if a.source == "local"]
        provider_name = "local" if real_local else "placeholder"
        logger.info("stock_media_provider_used", provider=provider_name, clips=len(assets), query=query)
        return assets, provider_name
