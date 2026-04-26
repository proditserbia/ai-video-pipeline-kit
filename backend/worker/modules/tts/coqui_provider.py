from __future__ import annotations

from pathlib import Path

import httpx

from app.config import settings
from worker.modules.base import AudioResult
from worker.modules.tts.base import AbstractTTSProvider


class CoquiTTSProvider(AbstractTTSProvider):
    """
    Coqui TTS HTTP client (local service).

    Expects a running Coqui TTS server (https://github.com/coqui-ai/TTS) with
    the default HTTP API enabled.  The server responds to GET /api/tts?text=…
    with raw PCM/WAV audio.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.COQUI_TTS_URL).rstrip("/")

    async def synthesize(self, text: str, voice: str, output_path: str) -> AudioResult:
        url = f"{self._base_url}/api/tts"
        params: dict[str, str] = {"text": text}
        if voice:
            params["speaker_id"] = voice

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            Path(output_path).write_bytes(response.content)

        size = Path(output_path).stat().st_size
        return AudioResult(
            path=output_path,
            metadata={"provider": "coqui", "voice": voice, "size_bytes": size},
        )
