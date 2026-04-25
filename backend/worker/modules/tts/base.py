from __future__ import annotations

from abc import abstractmethod

from worker.modules.base import AudioResult, BaseTTSProvider


class AbstractTTSProvider(BaseTTSProvider):
    """Shared helpers for TTS providers."""

    @abstractmethod
    async def synthesize(self, text: str, voice: str, output_path: str) -> AudioResult: ...
