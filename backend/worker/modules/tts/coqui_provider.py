from __future__ import annotations

from pathlib import Path

import httpx

from app.config import settings
from worker.modules.base import AudioResult
from worker.modules.tts.base import AbstractTTSProvider


class CoquiTTSProvider(AbstractTTSProvider):
    """
    Coqui TTS HTTP client.
    TODO: Implement full Coqui TTS API integration once the API schema is stable.
          See: https://github.com/coqui-ai/TTS for server endpoints.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.COQUI_TTS_URL).rstrip("/")

    async def synthesize(self, text: str, voice: str, output_path: str) -> AudioResult:
        # TODO: Replace with actual Coqui TTS API call when endpoint spec is confirmed.
        # Expected endpoint: POST /api/tts  with body {"text": ..., "speaker_id": ...}
        raise NotImplementedError(
            "CoquiTTSProvider.synthesize is not yet implemented. "
            "Set COQUI_TTS_ENABLED=False and use EdgeTTSProvider instead."
        )
