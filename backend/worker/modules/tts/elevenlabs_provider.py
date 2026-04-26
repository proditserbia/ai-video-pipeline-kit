from __future__ import annotations

from pathlib import Path

import httpx

from app.config import settings
from worker.modules.base import AudioResult
from worker.modules.tts.base import AbstractTTSProvider

_API_BASE = "https://api.elevenlabs.io/v1"
# Rachel – stable default voice available on all ElevenLabs tiers
_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
_DEFAULT_MODEL = "eleven_turbo_v2_5"


def _is_elevenlabs_voice_id(voice: str) -> bool:
    """Return True when *voice* looks like an ElevenLabs voice ID (alphanumeric, ≤ 25 chars)."""
    return bool(voice) and len(voice) <= 25 and voice.replace("-", "").replace("_", "").isalnum()


class ElevenLabsTTSProvider(AbstractTTSProvider):
    """ElevenLabs text-to-speech API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.ELEVENLABS_API_KEY

    async def synthesize(self, text: str, voice: str, output_path: str) -> AudioResult:
        voice_id = voice if _is_elevenlabs_voice_id(voice) else _DEFAULT_VOICE_ID
        url = f"{_API_BASE}/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": _DEFAULT_MODEL,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            Path(output_path).write_bytes(response.content)

        size = Path(output_path).stat().st_size
        return AudioResult(
            path=output_path,
            metadata={"provider": "elevenlabs", "voice_id": voice_id, "size_bytes": size},
        )
