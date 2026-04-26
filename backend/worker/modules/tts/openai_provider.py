from __future__ import annotations

from pathlib import Path

import httpx

from app.config import settings
from worker.modules.base import AudioResult
from worker.modules.tts.base import AbstractTTSProvider

_OPENAI_TTS_VOICES = frozenset({"alloy", "echo", "fable", "onyx", "nova", "shimmer"})
_DEFAULT_VOICE = "alloy"


class OpenAITTSProvider(AbstractTTSProvider):
    """OpenAI text-to-speech API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.OPENAI_API_KEY
        self._model = settings.OPENAI_TTS_MODEL

    async def synthesize(self, text: str, voice: str, output_path: str) -> AudioResult:
        # Map Edge TTS / other voice names to a valid OpenAI voice; fall back to default.
        openai_voice = voice.lower() if (voice and voice.lower() in _OPENAI_TTS_VOICES) else _DEFAULT_VOICE
        url = f"{settings.OPENAI_BASE_URL}/audio/speech"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "input": text,
            "voice": openai_voice,
            "response_format": "mp3",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            Path(output_path).write_bytes(response.content)

        size = Path(output_path).stat().st_size
        return AudioResult(
            path=output_path,
            metadata={
                "provider": "openai",
                "voice": openai_voice,
                "model": self._model,
                "size_bytes": size,
            },
        )
