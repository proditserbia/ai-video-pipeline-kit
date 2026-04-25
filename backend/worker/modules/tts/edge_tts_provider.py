from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

from worker.modules.base import AudioResult
from worker.modules.tts.base import AbstractTTSProvider


class EdgeTTSProvider(AbstractTTSProvider):
    """Microsoft Edge TTS via the edge-tts library."""

    async def synthesize(self, text: str, voice: str, output_path: str) -> AudioResult:
        communicate = edge_tts.Communicate(text=text, voice=voice)
        await communicate.save(output_path)

        path = Path(output_path)
        size = path.stat().st_size if path.exists() else 0
        return AudioResult(
            path=output_path,
            metadata={"voice": voice, "size_bytes": size},
        )

    async def list_voices(self) -> list[dict]:
        """Return available voices."""
        voices = await edge_tts.list_voices()
        return [{"name": v["ShortName"], "locale": v["Locale"], "gender": v["Gender"]} for v in voices]
