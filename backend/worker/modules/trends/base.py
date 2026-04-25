from __future__ import annotations

from abc import abstractmethod

from worker.modules.base import BaseTrendProvider, TrendItem


class AbstractTrendProvider(BaseTrendProvider):
    @abstractmethod
    def fetch(self, keyword: str | None, limit: int) -> list[TrendItem]: ...
