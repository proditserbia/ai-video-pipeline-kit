from __future__ import annotations

from app.config import settings
from worker.modules.tts.base import AbstractTTSProvider


def get_tts_provider() -> AbstractTTSProvider | None:
    """
    Return the highest-priority TTS provider that is available based on the
    current configuration, or *None* if no provider is configured.

    Priority order:
    1. ElevenLabs  – if ``ELEVENLABS_API_KEY`` is set
    2. OpenAI TTS  – if ``OPENAI_API_KEY`` is set
    3. Coqui TTS   – if ``COQUI_TTS_ENABLED`` is True
    4. Edge TTS    – if ``EDGE_TTS_ENABLED`` is True (best-effort, may fail in
                     server environments)
    """
    if settings.ELEVENLABS_API_KEY:
        from worker.modules.tts.elevenlabs_provider import ElevenLabsTTSProvider
        return ElevenLabsTTSProvider()

    if settings.OPENAI_API_KEY:
        from worker.modules.tts.openai_provider import OpenAITTSProvider
        return OpenAITTSProvider()

    if settings.COQUI_TTS_ENABLED:
        from worker.modules.tts.coqui_provider import CoquiTTSProvider
        return CoquiTTSProvider()

    if settings.EDGE_TTS_ENABLED:
        from worker.modules.tts.edge_tts_provider import EdgeTTSProvider
        return EdgeTTSProvider()

    return None
