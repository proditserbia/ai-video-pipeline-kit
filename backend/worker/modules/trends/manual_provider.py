from __future__ import annotations

from worker.modules.base import TrendItem
from worker.modules.trends.base import AbstractTrendProvider

DEFAULT_KEYWORDS = [
    "artificial intelligence",
    "climate change",
    "space exploration",
    "cryptocurrency",
    "health tips",
]


class ManualTrendProvider(AbstractTrendProvider):
    """
    Returns trends from a static keyword list defined in settings or hardcoded defaults.
    Useful for offline / test environments.
    """

    def __init__(self, keywords: list[str] | None = None) -> None:
        self._keywords = keywords or DEFAULT_KEYWORDS

    def fetch(self, keyword: str | None, limit: int = 10) -> list[TrendItem]:
        items = [
            TrendItem(title=kw, source="manual", keywords=[kw])
            for kw in self._keywords[:limit]
        ]
        if keyword:
            items = [i for i in items if keyword.lower() in i.title.lower()] or items
        return items[:limit]
