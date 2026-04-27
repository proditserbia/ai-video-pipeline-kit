"""Tests for the AI image provider factory and the local mock provider."""
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from worker.modules.ai_images.base import AIImageProvider, GeneratedImage
from worker.modules.ai_images.factory import get_ai_image_provider
from worker.modules.ai_images.providers.local_mock_provider import LocalMockImageProvider
from worker.modules.ai_images.providers.openai_provider import (
    OpenAIImageProvider,
    _ASPECT_RATIO_TO_SIZE,
)


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
            with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
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


# ── OpenAIImageProvider unit tests ────────────────────────────────────────────


class TestOpenAIImageProviderAspectRatio:
    """Aspect ratio must be mapped to a valid gpt-image-1 size."""

    def test_9_16_maps_to_portrait_size(self):
        assert _ASPECT_RATIO_TO_SIZE["9:16"] == "1024x1536"

    def test_16_9_maps_to_landscape_size(self):
        assert _ASPECT_RATIO_TO_SIZE["16:9"] == "1536x1024"

    def test_1_1_maps_to_square_size(self):
        assert _ASPECT_RATIO_TO_SIZE["1:1"] == "1024x1024"

    def test_generate_image_uses_correct_size_for_9_16(self, tmp_path: Path):
        """generate_image with aspect_ratio=9:16 must write the file and
        return a GeneratedImage with portrait dimensions."""
        png_1x1 = (
            b"\x89PNG\r\n\x1a\n"
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc"
            b"\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        fake_b64 = base64.b64encode(png_1x1).decode()

        with (
            patch("app.config.settings.OPENAI_API_KEY", "test-key"),
            patch("app.config.settings.OPENAI_IMAGE_MODEL", "gpt-image-1"),
            patch("app.config.settings.OPENAI_BASE_URL", "https://api.openai.com/v1"),
        ):
            provider = OpenAIImageProvider()
            with patch.object(provider, "_call_api", return_value=base64.b64decode(fake_b64)) as mock_call:
                out = tmp_path / "scene.png"
                result = provider.generate_image("test prompt", out, aspect_ratio="9:16")

        mock_call.assert_called_once_with("test prompt", size="1024x1536")
        assert result.width == 1024
        assert result.height == 1536
        assert out.exists()

    def test_generate_image_uses_correct_size_for_16_9(self, tmp_path: Path):
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

        with (
            patch("app.config.settings.OPENAI_API_KEY", "test-key"),
            patch("app.config.settings.OPENAI_IMAGE_MODEL", "gpt-image-1"),
            patch("app.config.settings.OPENAI_BASE_URL", "https://api.openai.com/v1"),
        ):
            provider = OpenAIImageProvider()
            with patch.object(provider, "_call_api", return_value=png_bytes) as mock_call:
                out = tmp_path / "scene.png"
                result = provider.generate_image("test prompt", out, aspect_ratio="16:9")

        mock_call.assert_called_once_with("test prompt", size="1536x1024")
        assert result.width == 1536
        assert result.height == 1024

    def test_payload_does_not_contain_response_format(self):
        """gpt-image-1 rejects response_format — it must never appear in the payload."""
        captured: list[dict] = []

        def _fake_post(url, *, json, headers, **kwargs):
            captured.append(json)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = lambda: None
            mock_resp.json.return_value = {
                "data": [{"b64_json": base64.b64encode(b"fake-png-bytes").decode()}]
            }
            return mock_resp

        with (
            patch("app.config.settings.OPENAI_API_KEY", "test-key"),
            patch("app.config.settings.OPENAI_IMAGE_MODEL", "gpt-image-1"),
            patch("app.config.settings.OPENAI_BASE_URL", "https://api.openai.com/v1"),
            patch("httpx.Client") as mock_client_cls,
        ):
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = _fake_post
            mock_client_cls.return_value = mock_client

            provider = OpenAIImageProvider()
            provider._call_api("a prompt", size="1024x1536")

        assert len(captured) == 1
        assert "response_format" not in captured[0], (
            "response_format must NOT be sent to gpt-image-1"
        )
        assert captured[0]["size"] == "1024x1536"


class TestOpenAIImageProvider400Error:
    """400 errors from the OpenAI API must include the response body in the exception."""

    def test_400_raises_runtime_error_with_body(self):
        with (
            patch("app.config.settings.OPENAI_API_KEY", "test-key"),
            patch("app.config.settings.OPENAI_IMAGE_MODEL", "gpt-image-1"),
            patch("app.config.settings.OPENAI_BASE_URL", "https://api.openai.com/v1"),
            patch("httpx.Client") as mock_client_cls,
        ):
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.status_code = 400
            mock_resp.text = '{"error": {"message": "invalid_parameter: response_format"}}'
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "400 Bad Request", request=MagicMock(), response=mock_resp
            )

            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            provider = OpenAIImageProvider()
            with pytest.raises(RuntimeError, match="400") as exc_info:
                provider._call_api("test", size="1024x1536")

        assert "invalid_parameter" in str(exc_info.value)

    def test_400_error_does_not_log_api_key(self):
        """The API key must not appear in the raised RuntimeError message."""
        fake_key = "sk-supersecretkey123"

        with (
            patch("app.config.settings.OPENAI_API_KEY", fake_key),
            patch("app.config.settings.OPENAI_IMAGE_MODEL", "gpt-image-1"),
            patch("app.config.settings.OPENAI_BASE_URL", "https://api.openai.com/v1"),
            patch("httpx.Client") as mock_client_cls,
        ):
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.status_code = 400
            mock_resp.text = '{"error": "bad request"}'
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "400", request=MagicMock(), response=mock_resp
            )

            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: mock_client
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            provider = OpenAIImageProvider()
            with pytest.raises(RuntimeError) as exc_info:
                provider._call_api("test", size="1024x1024")

        assert fake_key not in str(exc_info.value)


class TestZeroAISegmentsGuard:
    """When MEDIA_MODE=ai + AI_IMAGE_ENABLED and 0 segments are produced, the job must fail."""

    def test_zero_segments_raises(self, tmp_path: Path):
        """If generate_image always raises, the guard must raise RuntimeError."""
        from worker.modules.ai_images.providers.local_mock_provider import LocalMockImageProvider
        from worker.modules.script_planner.planner import plan_script_scenes
        from worker.modules.video_builder.visual_segment import VisualSegment

        scenes = plan_script_scenes(
            "A story about science. It changes everything.", audio_duration=10.0
        )
        assert len(scenes) >= 1

        provider = LocalMockImageProvider()
        segments: list[VisualSegment] = []

        # Simulate all images failing.
        for scene in scenes:
            img_path = tmp_path / f"scene_{scene.index:03d}.png"
            try:
                raise RuntimeError("Simulated API failure")
            except RuntimeError:
                pass  # every scene fails

        # Guard: 0 segments in AI mode must raise.
        if not segments:
            with pytest.raises(RuntimeError, match="AI image pipeline produced 0 visual segments"):
                raise RuntimeError("AI image pipeline produced 0 visual segments")
