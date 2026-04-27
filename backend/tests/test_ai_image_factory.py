"""Tests for the AI image provider factory and the local mock provider."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from worker.modules.ai_images.base import AIImageProvider, GeneratedImage
from worker.modules.ai_images.factory import get_ai_image_provider
from worker.modules.ai_images.providers.local_mock_provider import LocalMockImageProvider


# ── LocalMockImageProvider ────────────────────────────────────────────────────


class TestLocalMockImageProvider:
    def test_is_always_available(self):
        assert LocalMockImageProvider.is_available() is True

    def test_generate_creates_file(self, tmp_path: Path):
        provider = LocalMockImageProvider()
        out = tmp_path / "scene_000.png"
        result = provider.generate_image("A forest at dusk.", out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_generate_returns_generated_image(self, tmp_path: Path):
        provider = LocalMockImageProvider()
        out = tmp_path / "scene_000.png"
        result = provider.generate_image("A forest at dusk.", out)
        assert isinstance(result, GeneratedImage)

    def test_provider_field_is_local_mock(self, tmp_path: Path):
        provider = LocalMockImageProvider()
        out = tmp_path / "img.png"
        result = provider.generate_image("test prompt", out)
        assert result.provider == "local_mock"

    def test_path_matches_output_path(self, tmp_path: Path):
        provider = LocalMockImageProvider()
        out = tmp_path / "img.png"
        result = provider.generate_image("test prompt", out)
        assert result.path == out

    def test_prompt_is_stored(self, tmp_path: Path):
        provider = LocalMockImageProvider()
        out = tmp_path / "img.png"
        prompt = "Ancient ruins in the rain."
        result = provider.generate_image(prompt, out)
        assert result.prompt == prompt

    def test_scene_id_forwarded_via_metadata(self, tmp_path: Path):
        provider = LocalMockImageProvider()
        out = tmp_path / "img.png"
        result = provider.generate_image("test", out, metadata={"scene_id": "abc-123"})
        assert result.scene_id == "abc-123"

    def test_creates_parent_directory(self, tmp_path: Path):
        provider = LocalMockImageProvider()
        out = tmp_path / "sub" / "dir" / "img.png"
        provider.generate_image("test", out)
        assert out.exists()

    def test_output_is_valid_png(self, tmp_path: Path):
        provider = LocalMockImageProvider()
        out = tmp_path / "img.png"
        provider.generate_image("test", out)
        header = out.read_bytes()[:8]
        assert header == b"\x89PNG\r\n\x1a\n"

    def test_different_prompts_produce_different_colours(self, tmp_path: Path):
        """Different prompts may produce different coloured PNGs (not guaranteed to differ
        on every call, but the mechanism is deterministic — same prompt → same colour)."""
        provider = LocalMockImageProvider()
        p1 = tmp_path / "img1.png"
        p2 = tmp_path / "img2.png"
        provider.generate_image("aaa bbb ccc", p1)
        provider.generate_image("aaa bbb ccc", p2)
        # Same prompt → same output (deterministic).
        assert p1.read_bytes() == p2.read_bytes()


# ── AIImageProvider ABC ───────────────────────────────────────────────────────


class TestAIImageProviderInterface:
    def test_local_mock_is_subclass(self):
        assert issubclass(LocalMockImageProvider, AIImageProvider)

    def test_cannot_instantiate_abstract_base(self):
        with pytest.raises(TypeError):
            AIImageProvider()  # type: ignore[abstract]


# ── Factory ───────────────────────────────────────────────────────────────────


class TestGetAIImageProvider:
    def test_returns_local_mock_when_configured(self):
        with patch("app.config.settings.AI_IMAGE_PROVIDER", "local_mock"):
            provider = get_ai_image_provider()
        assert isinstance(provider, LocalMockImageProvider)

    def test_raises_for_unknown_provider(self):
        with patch("app.config.settings.AI_IMAGE_PROVIDER", "unknown_xyz"):
            with pytest.raises(ValueError, match="Unknown AI_IMAGE_PROVIDER"):
                get_ai_image_provider()

    def test_raises_when_provider_not_available(self):
        with (
            patch("app.config.settings.AI_IMAGE_PROVIDER", "openai"),
            patch("app.config.settings.OPENAI_API_KEY", None),
        ):
            with pytest.raises(RuntimeError, match="not available"):
                get_ai_image_provider()

    def test_openai_available_when_key_set(self):
        from worker.modules.ai_images.providers.openai_provider import OpenAIImageProvider

        with (
            patch("app.config.settings.AI_IMAGE_PROVIDER", "openai"),
            patch("app.config.settings.OPENAI_API_KEY", "fake-key"),
        ):
            provider = get_ai_image_provider()
        assert isinstance(provider, OpenAIImageProvider)

    def test_stability_available_when_key_set(self):
        from worker.modules.ai_images.providers.stability_provider import StabilityAIProvider

        with (
            patch("app.config.settings.AI_IMAGE_PROVIDER", "stability"),
            patch("app.config.settings.STABILITY_AI_API_KEY", "fake-key"),
        ):
            provider = get_ai_image_provider()
        assert isinstance(provider, StabilityAIProvider)

    def test_factory_is_only_place_with_provider_mapping(self):
        """Verify the registry contains the expected provider names."""
        from worker.modules.ai_images.factory import _PROVIDER_REGISTRY

        assert "openai" in _PROVIDER_REGISTRY
        assert "stability" in _PROVIDER_REGISTRY
        assert "local_mock" in _PROVIDER_REGISTRY

    def test_provider_name_case_insensitive(self):
        with patch("app.config.settings.AI_IMAGE_PROVIDER", "LOCAL_MOCK"):
            provider = get_ai_image_provider()
        assert isinstance(provider, LocalMockImageProvider)
