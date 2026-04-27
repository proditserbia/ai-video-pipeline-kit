from __future__ import annotations

import structlog

from app.config import settings
from worker.modules.base import MediaAsset

logger = structlog.get_logger(__name__)


class StockMediaSelector:
    """
    Select media clips using a priority chain controlled by ``MEDIA_MODE``:

    **stock** (default):
      1. Pexels  – if ``PEXELS_API_KEY`` is set and returns results
      2. Pixabay – if ``PIXABAY_API_KEY`` is set and returns results
      3. Local assets – video files under ``STORAGE_PATH/assets``
      4. FFmpeg placeholder clips – generated on the fly (always succeeds)

    **ai**:
      1. OpenAI Image API (gpt-image-1)  – if ``OPENAI_API_KEY`` is set
      2. Stability AI (SDXL)             – if ``STABILITY_AI_API_KEY`` is set
      3. FFmpeg placeholder clips

    **hybrid**:
      Stock chain first (Pexels → Pixabay → Local), then AI fallback
      (OpenAI → Stability) if stock returns nothing, then placeholder.
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
        of ``"pexels"``, ``"pixabay"``, ``"local"``, ``"openai"``,
        ``"stability"``, or ``"placeholder"``.
        """
        mode = (settings.MEDIA_MODE or "stock").lower()

        if mode == "ai":
            return self._fetch_ai(query, count, output_dir)
        if mode == "hybrid":
            return self._fetch_hybrid(query, count, output_dir)
        # Default: "stock"
        return self._fetch_stock(query, count, output_dir)

    # ── Stock-only chain ─────────────────────────────────────────────────────

    def _fetch_stock(
        self,
        query: str,
        count: int,
        output_dir: str,
    ) -> tuple[list[MediaAsset], str]:
        # 1. Pexels
        if settings.PEXELS_API_KEY:
            from worker.modules.stock_media.pexels_provider import PexelsProvider

            try:
                assets = PexelsProvider().fetch(query, count, output_dir)
            except Exception as exc:
                logger.error("stock_media_pexels_unexpected_error", error=str(exc), query=query)
                assets = []
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
        real_local = [a for a in assets if a.source == "local"]
        provider_name = "local" if real_local else "placeholder"
        logger.info("stock_media_provider_used", provider=provider_name, clips=len(assets), query=query)
        return assets, provider_name

    # ── AI-only chain ────────────────────────────────────────────────────────

    def _fetch_ai(
        self,
        query: str,
        count: int,
        output_dir: str,
    ) -> tuple[list[MediaAsset], str]:
        # 1. OpenAI image generation
        if settings.OPENAI_API_KEY:
            from worker.modules.stock_media.openai_image_provider import OpenAIImageProvider

            try:
                assets = OpenAIImageProvider().fetch(query, count, output_dir)
            except Exception as exc:
                logger.error("ai_image_openai_unexpected_error", error=str(exc), query=query)
                assets = []
            if assets:
                logger.info("stock_media_provider_used", provider="openai", clips=len(assets), query=query)
                return assets, "openai"
            logger.warning("ai_image_openai_empty", query=query)

        # 2. Stability AI
        if settings.STABILITY_AI_API_KEY:
            from worker.modules.stock_media.stability_provider import StabilityAIProvider

            try:
                assets = StabilityAIProvider().fetch(query, count, output_dir)
            except Exception as exc:
                logger.error("ai_image_stability_unexpected_error", error=str(exc), query=query)
                assets = []
            if assets:
                logger.info("stock_media_provider_used", provider="stability", clips=len(assets), query=query)
                return assets, "stability"
            logger.warning("ai_image_stability_empty", query=query)

        # 3. Placeholder fallback
        return self._placeholder_fallback(count, output_dir)

    # ── Hybrid chain ─────────────────────────────────────────────────────────

    def _fetch_hybrid(
        self,
        query: str,
        count: int,
        output_dir: str,
    ) -> tuple[list[MediaAsset], str]:
        # Try stock providers first (Pexels → Pixabay → Local).
        if settings.PEXELS_API_KEY:
            from worker.modules.stock_media.pexels_provider import PexelsProvider

            try:
                assets = PexelsProvider().fetch(query, count, output_dir)
            except Exception as exc:
                logger.error("stock_media_pexels_unexpected_error", error=str(exc), query=query)
                assets = []
            if assets:
                logger.info("stock_media_provider_used", provider="pexels", clips=len(assets), query=query)
                return assets, "pexels"
            logger.warning("stock_media_pexels_empty", query=query)

        if settings.PIXABAY_API_KEY:
            from worker.modules.stock_media.pixabay_provider import PixabayProvider

            try:
                assets = PixabayProvider().fetch(query, count, output_dir)
            except Exception as exc:
                logger.error("stock_media_pixabay_unexpected_error", error=str(exc), query=query)
                assets = []
            if assets:
                logger.info("stock_media_provider_used", provider="pixabay", clips=len(assets), query=query)
                return assets, "pixabay"
            logger.warning("stock_media_pixabay_empty", query=query)

        # Check local assets (not placeholder).
        from worker.modules.stock_media.local_provider import LocalMediaProvider

        local_assets = LocalMediaProvider().fetch(query, count, output_dir)
        real_local = [a for a in local_assets if a.source == "local"]
        if real_local:
            logger.info("stock_media_provider_used", provider="local", clips=len(real_local), query=query)
            return local_assets, "local"

        # Fall back to AI providers.
        logger.info("hybrid_stock_empty_trying_ai", query=query)

        if settings.OPENAI_API_KEY:
            from worker.modules.stock_media.openai_image_provider import OpenAIImageProvider

            try:
                assets = OpenAIImageProvider().fetch(query, count, output_dir)
            except Exception as exc:
                logger.error("ai_image_openai_unexpected_error", error=str(exc), query=query)
                assets = []
            if assets:
                logger.info("stock_media_provider_used", provider="openai", clips=len(assets), query=query)
                return assets, "openai"
            logger.warning("ai_image_openai_empty", query=query)

        if settings.STABILITY_AI_API_KEY:
            from worker.modules.stock_media.stability_provider import StabilityAIProvider

            try:
                assets = StabilityAIProvider().fetch(query, count, output_dir)
            except Exception as exc:
                logger.error("ai_image_stability_unexpected_error", error=str(exc), query=query)
                assets = []
            if assets:
                logger.info("stock_media_provider_used", provider="stability", clips=len(assets), query=query)
                return assets, "stability"
            logger.warning("ai_image_stability_empty", query=query)

        # Last resort: placeholder.
        return self._placeholder_fallback(count, output_dir)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _placeholder_fallback(count: int, output_dir: str) -> tuple[list[MediaAsset], str]:
        from worker.modules.stock_media.local_provider import LocalMediaProvider

        assets = LocalMediaProvider().fetch("", count, output_dir)
        logger.info("stock_media_provider_used", provider="placeholder", clips=len(assets))
        return assets, "placeholder"
