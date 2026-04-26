"""Tests for the TTS provider selector.

Each test patches the relevant settings values and (where needed) the
``_coqui_reachable`` network helper so that no real I/O occurs.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from worker.modules.tts.selector import get_tts_provider, get_tts_provider_name


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

class TestGetTTSProvider:
    """Verify the priority chain: ElevenLabs → OpenAI → Coqui → Edge → None."""

    def test_openai_selected_when_api_key_set(self):
        with (
            patch("app.config.settings.ELEVENLABS_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", "sk-test"),
        ):
            from worker.modules.tts.openai_provider import OpenAITTSProvider
            provider = get_tts_provider()
        assert isinstance(provider, OpenAITTSProvider)

    def test_openai_takes_priority_over_coqui(self):
        """OpenAI must win even when Coqui is enabled and reachable."""
        with (
            patch("app.config.settings.ELEVENLABS_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", "sk-test"),
            patch("app.config.settings.COQUI_TTS_ENABLED", True),
            patch("worker.modules.tts.selector._coqui_reachable", return_value=True),
        ):
            from worker.modules.tts.openai_provider import OpenAITTSProvider
            provider = get_tts_provider()
        assert isinstance(provider, OpenAITTSProvider)

    def test_coqui_selected_when_openai_missing_and_coqui_reachable(self):
        with (
            patch("app.config.settings.ELEVENLABS_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", None),
            patch("app.config.settings.COQUI_TTS_ENABLED", True),
            patch("worker.modules.tts.selector._coqui_reachable", return_value=True),
        ):
            from worker.modules.tts.coqui_provider import CoquiTTSProvider
            provider = get_tts_provider()
        assert isinstance(provider, CoquiTTSProvider)

    def test_coqui_skipped_when_unreachable(self):
        """Coqui must be skipped when the health check fails, even if enabled."""
        with (
            patch("app.config.settings.ELEVENLABS_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", None),
            patch("app.config.settings.COQUI_TTS_ENABLED", True),
            patch("worker.modules.tts.selector._coqui_reachable", return_value=False),
            patch("app.config.settings.EDGE_TTS_ENABLED", False),
        ):
            provider = get_tts_provider()
        assert provider is None

    def test_edge_selected_when_explicitly_enabled_and_no_other_provider(self):
        with (
            patch("app.config.settings.ELEVENLABS_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", None),
            patch("app.config.settings.COQUI_TTS_ENABLED", False),
            patch("app.config.settings.EDGE_TTS_ENABLED", True),
        ):
            from worker.modules.tts.edge_tts_provider import EdgeTTSProvider
            provider = get_tts_provider()
        assert isinstance(provider, EdgeTTSProvider)

    def test_none_returned_when_no_provider_configured(self):
        with (
            patch("app.config.settings.ELEVENLABS_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", None),
            patch("app.config.settings.COQUI_TTS_ENABLED", False),
            patch("app.config.settings.EDGE_TTS_ENABLED", False),
        ):
            provider = get_tts_provider()
        assert provider is None

    def test_none_returned_when_openai_key_is_empty_string(self):
        """An empty string OPENAI_API_KEY must be treated as not configured."""
        with (
            patch("app.config.settings.ELEVENLABS_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", ""),
            patch("app.config.settings.COQUI_TTS_ENABLED", False),
            patch("app.config.settings.EDGE_TTS_ENABLED", False),
        ):
            provider = get_tts_provider()
        assert provider is None

    def test_elevenlabs_takes_highest_priority(self):
        with (
            patch("app.config.settings.ELEVENLABS_API_KEY", "el-key"),
            patch("app.config.settings.OPENAI_API_KEY", "sk-test"),
        ):
            from worker.modules.tts.elevenlabs_provider import ElevenLabsTTSProvider
            provider = get_tts_provider()
        assert isinstance(provider, ElevenLabsTTSProvider)

    def test_coqui_not_tried_when_disabled(self):
        """_coqui_reachable must not be called at all when COQUI_TTS_ENABLED is False."""
        coqui_spy = patch("worker.modules.tts.selector._coqui_reachable", return_value=True)
        with (
            patch("app.config.settings.ELEVENLABS_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", None),
            patch("app.config.settings.COQUI_TTS_ENABLED", False),
            patch("app.config.settings.EDGE_TTS_ENABLED", False),
            coqui_spy as mock_reachable,
        ):
            provider = get_tts_provider()
        mock_reachable.assert_not_called()
        assert provider is None


# ---------------------------------------------------------------------------
# Provider name helper
# ---------------------------------------------------------------------------

class TestGetTTSProviderName:
    def test_none_returns_none_string(self):
        assert get_tts_provider_name(None) == "none"

    def test_openai_provider_name(self):
        with (
            patch("app.config.settings.ELEVENLABS_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", "sk-test"),
        ):
            provider = get_tts_provider()
        assert get_tts_provider_name(provider) == "openai"

    def test_coqui_provider_name(self):
        with (
            patch("app.config.settings.ELEVENLABS_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", None),
            patch("app.config.settings.COQUI_TTS_ENABLED", True),
            patch("worker.modules.tts.selector._coqui_reachable", return_value=True),
        ):
            provider = get_tts_provider()
        assert get_tts_provider_name(provider) == "coqui"

    def test_edge_provider_name(self):
        with (
            patch("app.config.settings.ELEVENLABS_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", None),
            patch("app.config.settings.COQUI_TTS_ENABLED", False),
            patch("app.config.settings.EDGE_TTS_ENABLED", True),
        ):
            provider = get_tts_provider()
        assert get_tts_provider_name(provider) == "edge"

    def test_elevenlabs_provider_name(self):
        with patch("app.config.settings.ELEVENLABS_API_KEY", "el-key"):
            provider = get_tts_provider()
        assert get_tts_provider_name(provider) == "elevenlabs"
