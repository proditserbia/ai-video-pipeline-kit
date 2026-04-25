from __future__ import annotations

from abc import abstractmethod

from worker.modules.base import BaseStockProvider, MediaAsset


class AbstractStockProvider(BaseStockProvider):
    @abstractmethod
    def fetch(self, query: str, count: int, output_dir: str) -> list[MediaAsset]: ...
