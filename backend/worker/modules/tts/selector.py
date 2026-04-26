from __future__ import annotations

import logging

import httpx

from app.config import settings
from worker.modules.tts.base import AbstractTTSProvider

logger = logging.getLogger(__name__)


def _coqui_reachable() -> bool:
    """Return True if the Coqui TTS server responds to a health-check request."""
    url = settings.COQUI_TTS_URL.rstrip("/") + "/api/tts"
    try:
        # Any HTTP response (including 4xx) confirms the server is up.
        httpx.get(url, params={"text": "ping"}, timeout=5.0)
        return True
    except (httpx.HTTPStatusError, httpx.RequestError, OSError) as exc:
        logger.warning("Coqui TTS health check failed (%s) – skipping provider.", exc)
        return False


def get_tts_provider() -> AbstractTTSProvider | None:
    """
    Return the highest-priority TTS provider that is available based on the
    current configuration, or *None* if no provider is configured.

    Priority order:
    1. ElevenLabs  – if ``ELEVENLABS_API_KEY`` is set
    2. OpenAI TTS  – if ``OPENAI_API_KEY`` is set
    3. Coqui TTS   – if ``COQUI_TTS_ENABLED`` is True AND the server is reachable
    4. Edge TTS    – if ``EDGE_TTS_ENABLED`` is True (must be explicitly enabled;
                     not used by default)
    """
    if settings.ELEVENLABS_API_KEY:
        from worker.modules.tts.elevenlabs_provider import ElevenLabsTTSProvider
        return ElevenLabsTTSProvider()

    if settings.OPENAI_API_KEY:
        from worker.modules.tts.openai_provider import OpenAITTSProvider
        return OpenAITTSProvider()

    if settings.COQUI_TTS_ENABLED and _coqui_reachable():
        from worker.modules.tts.coqui_provider import CoquiTTSProvider
        return CoquiTTSProvider()

    if settings.EDGE_TTS_ENABLED:
        from worker.modules.tts.edge_tts_provider import EdgeTTSProvider
        return EdgeTTSProvider()

    return None
