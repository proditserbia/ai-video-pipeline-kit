from __future__ import annotations

import structlog

from worker.modules.base import TrendItem
from worker.modules.trends.base import AbstractTrendProvider

logger = structlog.get_logger(__name__)


class GoogleTrendsProvider(AbstractTrendProvider):
    """Google Trends via pytrends."""

    def fetch(self, keyword: str | None, limit: int = 10) -> list[TrendItem]:
        try:
            from pytrends.request import TrendReq
        except ImportError:
            logger.warning("pytrends_not_installed")
            return []

        try:
            pt = TrendReq(hl="en-US", tz=360)
            df = pt.trending_searches(pn="united_states")
            items: list[TrendItem] = []
            for row in df.values[:limit]:
                title = str(row[0])
                items.append(TrendItem(title=title, source="google_trends"))
            return items
        except Exception as exc:
            logger.error("google_trends_error", error=str(exc))
            return []
