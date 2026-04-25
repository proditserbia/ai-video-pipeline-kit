from __future__ import annotations

import structlog

from worker.modules.base import TrendItem
from worker.modules.trends.base import AbstractTrendProvider

logger = structlog.get_logger(__name__)

DEFAULT_FEEDS = [
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.cnn.com/rss/edition.rss",
    "https://feeds.reuters.com/reuters/topNews",
]


class RSSProvider(AbstractTrendProvider):
    """RSS feed trend provider using feedparser."""

    def __init__(self, feed_urls: list[str] | None = None) -> None:
        self._feeds = feed_urls or DEFAULT_FEEDS

    def fetch(self, keyword: str | None, limit: int = 10) -> list[TrendItem]:
        try:
            import feedparser
        except ImportError:
            logger.warning("feedparser_not_installed")
            return []

        items: list[TrendItem] = []
        for url in self._feeds:
            if len(items) >= limit:
                break
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    if len(items) >= limit:
                        break
                    title = entry.get("title", "")
                    if not title:
                        continue
                    if keyword and keyword.lower() not in title.lower():
                        continue
                    items.append(TrendItem(
                        title=title,
                        description=entry.get("summary"),
                        source=f"rss:{url}",
                        keywords=[keyword] if keyword else [],
                    ))
            except Exception as exc:
                logger.warning("rss_feed_error", url=url, error=str(exc))

        return items
