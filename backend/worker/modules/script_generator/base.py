from __future__ import annotations

from abc import abstractmethod
from typing import Any

from worker.modules.base import BaseScriptProvider, ScriptResult


class AbstractScriptProvider(BaseScriptProvider):
    """Shared helpers for script providers."""

    @abstractmethod
    def generate(self, topic: str, settings: dict[str, Any]) -> ScriptResult: ...
