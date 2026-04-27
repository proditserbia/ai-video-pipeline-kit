from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from worker.modules.base import MediaAsset
from worker.modules.stock_media.selector import StockMediaSelector
from worker.modules.stock_media.prompt_generator import generate_scene_prompts


# ── Helpers ──────────────────────────────────────────────────────────────────

def _asset(source: str, path: str = "/tmp/clip.mp4", ai_provider: str | None = None) -> MediaAsset:
    meta: dict = {}
    if ai_provider:
        meta["ai_provider"] = ai_provider
        meta["prompt"] = "A cinematic scene of test, dramatic lighting"
    return MediaAsset(path=path, source=source, metadata=meta)


# ── Prompt generator ─────────────────────────────────────────────────────────

class TestPromptGenerator:
    def test_returns_correct_count(self):
        prompts = generate_scene_prompts("Hello world. Goodbye world.", 3)
        assert len(prompts) == 3

    def test_empty_script_returns_fallback_prompts(self):
        prompts = generate_scene_prompts("", 2)
        assert len(prompts) == 2
        assert all("cinematic" in p for p in prompts)

    def test_single_sentence_fills_all_slots(self):
        prompts = generate_scene_prompts("Ancient giants walk through the desert.", 2)
        assert len(prompts) == 2
        assert all("cinematic" in p for p in prompts)

    def test_prompts_contain_cinematic_prefix(self):
        prompts = generate_scene_prompts("A story about the ocean.", 1)
        assert prompts[0].startswith("A cinematic scene of")

    def test_count_one(self):
        prompts = generate_scene_prompts("Short script.", 1)
        assert len(prompts) == 1


# ── MEDIA_MODE=ai ─────────────────────────────────────────────────────────────

class TestSelectorAIMode:
    """MEDIA_MODE=ai must skip all stock providers."""

    def test_ai_mode_uses_openai_and_skips_pexels(self, tmp_path):
        ai_assets = [_asset("ai", ai_provider="openai")]
        pexels_mock = MagicMock(return_value=[_asset("pexels")])

        with (
            patch("app.config.settings.MEDIA_MODE", "ai"),
            patch("app.config.settings.OPENAI_API_KEY", "fake-openai-key"),
            patch("app.config.settings.PEXELS_API_KEY", "fake-pexels-key"),
            patch(
                "worker.modules.stock_media.openai_image_provider.OpenAIImageProvider.fetch",
                return_value=ai_assets,
            ),
            patch(
                "worker.modules.stock_media.pexels_provider.PexelsProvider.fetch",
                pexels_mock,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("ancient giants", 1, str(tmp_path))

        assert provider == "openai"
        assert assets == ai_assets
        pexels_mock.assert_not_called()

    def test_ai_mode_falls_back_to_stability_when_openai_fails(self, tmp_path):
        stability_assets = [_asset("ai", ai_provider="stability")]

        with (
            patch("app.config.settings.MEDIA_MODE", "ai"),
            patch("app.config.settings.OPENAI_API_KEY", "fake-openai-key"),
            patch("app.config.settings.STABILITY_AI_API_KEY", "fake-stability-key"),
            patch(
                "worker.modules.stock_media.openai_image_provider.OpenAIImageProvider.fetch",
                return_value=[],
            ),
            patch(
                "worker.modules.stock_media.stability_provider.StabilityAIProvider.fetch",
                return_value=stability_assets,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("ancient giants", 1, str(tmp_path))

        assert provider == "stability"
        assert assets == stability_assets

    def test_ai_mode_falls_back_to_placeholder_when_all_fail(self, tmp_path):
        placeholder_assets = [_asset("local_placeholder")]

        with (
            patch("app.config.settings.MEDIA_MODE", "ai"),
            patch("app.config.settings.OPENAI_API_KEY", "fake-openai-key"),
            patch("app.config.settings.STABILITY_AI_API_KEY", None),
            patch(
                "worker.modules.stock_media.openai_image_provider.OpenAIImageProvider.fetch",
                return_value=[],
            ),
            patch(
                "worker.modules.stock_media.local_provider.LocalMediaProvider.fetch",
                return_value=placeholder_assets,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("ancient giants", 1, str(tmp_path))

        assert provider == "placeholder"

    def test_ai_mode_no_api_keys_falls_back_to_placeholder(self, tmp_path):
        placeholder_assets = [_asset("local_placeholder")]

        with (
            patch("app.config.settings.MEDIA_MODE", "ai"),
            patch("app.config.settings.OPENAI_API_KEY", None),
            patch("app.config.settings.STABILITY_AI_API_KEY", None),
            patch(
                "worker.modules.stock_media.local_provider.LocalMediaProvider.fetch",
                return_value=placeholder_assets,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("query", 1, str(tmp_path))

        assert provider == "placeholder"


# ── MEDIA_MODE=hybrid ─────────────────────────────────────────────────────────

class TestSelectorHybridMode:
    """MEDIA_MODE=hybrid: stock first, AI fallback if stock empty."""

    def test_hybrid_uses_pexels_when_available(self, tmp_path):
        pexels_assets = [_asset("pexels")]

        with (
            patch("app.config.settings.MEDIA_MODE", "hybrid"),
            patch("app.config.settings.PEXELS_API_KEY", "fake-pexels-key"),
            patch(
                "worker.modules.stock_media.pexels_provider.PexelsProvider.fetch",
                return_value=pexels_assets,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("nature", 1, str(tmp_path))

        assert provider == "pexels"
        assert assets == pexels_assets

    def test_hybrid_falls_back_to_ai_when_stock_empty(self, tmp_path):
        ai_assets = [_asset("ai", ai_provider="openai")]

        with (
            patch("app.config.settings.MEDIA_MODE", "hybrid"),
            patch("app.config.settings.PEXELS_API_KEY", "fake-pexels-key"),
            patch("app.config.settings.PIXABAY_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", "fake-openai-key"),
            patch(
                "worker.modules.stock_media.pexels_provider.PexelsProvider.fetch",
                return_value=[],
            ),
            patch(
                "worker.modules.stock_media.local_provider.LocalMediaProvider.fetch",
                return_value=[],  # No local files → triggers AI fallback
            ),
            patch(
                "worker.modules.stock_media.openai_image_provider.OpenAIImageProvider.fetch",
                return_value=ai_assets,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("ancient giants", 1, str(tmp_path))

        assert provider == "openai"
        assert assets == ai_assets

    def test_hybrid_falls_back_to_stability_when_openai_fails(self, tmp_path):
        stability_assets = [_asset("ai", ai_provider="stability")]

        with (
            patch("app.config.settings.MEDIA_MODE", "hybrid"),
            patch("app.config.settings.PEXELS_API_KEY", None),
            patch("app.config.settings.PIXABAY_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", "fake-openai-key"),
            patch("app.config.settings.STABILITY_AI_API_KEY", "fake-stability-key"),
            patch(
                "worker.modules.stock_media.local_provider.LocalMediaProvider.fetch",
                return_value=[],
            ),
            patch(
                "worker.modules.stock_media.openai_image_provider.OpenAIImageProvider.fetch",
                return_value=[],
            ),
            patch(
                "worker.modules.stock_media.stability_provider.StabilityAIProvider.fetch",
                return_value=stability_assets,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("ancient giants", 1, str(tmp_path))

        assert provider == "stability"
        assert assets == stability_assets

    def test_hybrid_placeholder_when_both_stock_and_ai_fail(self, tmp_path):
        placeholder_assets = [_asset("local_placeholder")]

        with (
            patch("app.config.settings.MEDIA_MODE", "hybrid"),
            patch("app.config.settings.PEXELS_API_KEY", None),
            patch("app.config.settings.PIXABAY_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", None),
            patch("app.config.settings.STABILITY_AI_API_KEY", None),
            patch(
                "worker.modules.stock_media.local_provider.LocalMediaProvider.fetch",
                return_value=placeholder_assets,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("query", 1, str(tmp_path))

        assert provider == "placeholder"

    def test_hybrid_does_not_use_ai_when_stock_succeeds(self, tmp_path):
        pexels_assets = [_asset("pexels")]
        openai_mock = MagicMock(return_value=[_asset("ai", ai_provider="openai")])

        with (
            patch("app.config.settings.MEDIA_MODE", "hybrid"),
            patch("app.config.settings.PEXELS_API_KEY", "fake-pexels-key"),
            patch("app.config.settings.OPENAI_API_KEY", "fake-openai-key"),
            patch(
                "worker.modules.stock_media.pexels_provider.PexelsProvider.fetch",
                return_value=pexels_assets,
            ),
            patch(
                "worker.modules.stock_media.openai_image_provider.OpenAIImageProvider.fetch",
                openai_mock,
            ),
        ):
            selector = StockMediaSelector()
            _, provider = selector.fetch("nature", 1, str(tmp_path))

        assert provider == "pexels"
        openai_mock.assert_not_called()


# ── MEDIA_MODE=stock (default, backward compat) ───────────────────────────────

class TestSelectorStockMode:
    """MEDIA_MODE=stock must behave exactly as before."""

    def test_stock_mode_uses_pexels(self, tmp_path):
        pexels_assets = [_asset("pexels")]

        with (
            patch("app.config.settings.MEDIA_MODE", "stock"),
            patch("app.config.settings.PEXELS_API_KEY", "fake-pexels-key"),
            patch(
                "worker.modules.stock_media.pexels_provider.PexelsProvider.fetch",
                return_value=pexels_assets,
            ),
        ):
            selector = StockMediaSelector()
            assets, provider = selector.fetch("nature", 1, str(tmp_path))

        assert provider == "pexels"

    def test_stock_mode_does_not_use_ai_providers(self, tmp_path):
        placeholder_assets = [_asset("local_placeholder")]
        openai_mock = MagicMock()

        with (
            patch("app.config.settings.MEDIA_MODE", "stock"),
            patch("app.config.settings.PEXELS_API_KEY", None),
            patch("app.config.settings.PIXABAY_API_KEY", None),
            patch("app.config.settings.OPENAI_API_KEY", "fake-openai-key"),
            patch(
                "worker.modules.stock_media.local_provider.LocalMediaProvider.fetch",
                return_value=placeholder_assets,
            ),
            patch(
                "worker.modules.stock_media.openai_image_provider.OpenAIImageProvider.fetch",
                openai_mock,
            ),
        ):
            selector = StockMediaSelector()
            _, provider = selector.fetch("query", 1, str(tmp_path))

        assert provider == "placeholder"
        openai_mock.assert_not_called()


# ── Image-to-video conversion ─────────────────────────────────────────────────

class TestImageToVideo:
    """Images must be converted to MP4 clips via FFmpeg (Ken Burns effect)."""

    def test_image_to_video_calls_ffmpeg(self, tmp_path):
        from unittest.mock import patch as _patch
        import subprocess as _subprocess

        image_file = tmp_path / "test.png"
        image_file.write_bytes(b"fake-image")
        output_file = tmp_path / "out.mp4"

        mock_result = MagicMock()
        mock_result.returncode = 0

        with _patch("subprocess.run", return_value=mock_result) as mock_run:
            from worker.modules.stock_media.image_to_video import image_to_video
            result = image_to_video(image_file, output_file, duration=6)

        assert result == output_file
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd
        assert "zoompan" in " ".join(cmd)

    def test_image_to_video_raises_on_ffmpeg_failure(self, tmp_path):
        from unittest.mock import patch as _patch

        image_file = tmp_path / "test.png"
        image_file.write_bytes(b"fake-image")
        output_file = tmp_path / "out.mp4"

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ffmpeg error"

        with _patch("subprocess.run", return_value=mock_result):
            from worker.modules.stock_media.image_to_video import image_to_video
            with pytest.raises(RuntimeError, match="image_to_video failed"):
                image_to_video(image_file, output_file, duration=6)

    def test_duration_clamped_to_min(self, tmp_path):
        from unittest.mock import patch as _patch

        image_file = tmp_path / "test.png"
        image_file.write_bytes(b"fake-image")
        output_file = tmp_path / "out.mp4"

        mock_result = MagicMock()
        mock_result.returncode = 0

        with _patch("subprocess.run", return_value=mock_result) as mock_run:
            from worker.modules.stock_media.image_to_video import image_to_video
            image_to_video(image_file, output_file, duration=1)  # below min of 5

        cmd = mock_run.call_args[0][0]
        t_idx = cmd.index("-t")
        assert int(cmd[t_idx + 1]) == 5

    def test_duration_clamped_to_max(self, tmp_path):
        from unittest.mock import patch as _patch

        image_file = tmp_path / "test.png"
        image_file.write_bytes(b"fake-image")
        output_file = tmp_path / "out.mp4"

        mock_result = MagicMock()
        mock_result.returncode = 0

        with _patch("subprocess.run", return_value=mock_result) as mock_run:
            from worker.modules.stock_media.image_to_video import image_to_video
            image_to_video(image_file, output_file, duration=100)  # above max of 8

        cmd = mock_run.call_args[0][0]
        t_idx = cmd.index("-t")
        assert int(cmd[t_idx + 1]) == 8


# ── OpenAI image provider unit tests ─────────────────────────────────────────

class TestOpenAIImageProvider:
    def test_returns_empty_when_no_api_key(self, tmp_path):
        with patch("app.config.settings.OPENAI_API_KEY", None):
            from worker.modules.stock_media.openai_image_provider import OpenAIImageProvider
            provider = OpenAIImageProvider()
            assets = provider.fetch("query", 2, str(tmp_path))
        assert assets == []

    def test_returns_assets_on_success(self, tmp_path):
        import base64

        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        b64_png = base64.b64encode(fake_png).decode()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"data": [{"b64_json": b64_png}]}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response

        mock_ffmpeg = MagicMock(returncode=0)

        with (
            patch("app.config.settings.OPENAI_API_KEY", "fake-key"),
            patch("app.config.settings.STORAGE_PATH", str(tmp_path)),
            patch("httpx.Client", return_value=mock_client),
            patch("subprocess.run", return_value=mock_ffmpeg),
        ):
            from worker.modules.stock_media.openai_image_provider import OpenAIImageProvider
            provider = OpenAIImageProvider()
            assets = provider.fetch("ancient giants", 1, str(tmp_path))

        assert len(assets) == 1
        assert assets[0].source == "ai"
        assert assets[0].metadata["ai_provider"] == "openai"
        assert "prompt" in assets[0].metadata

    def test_returns_empty_on_api_error(self, tmp_path):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = Exception("network error")

        with (
            patch("app.config.settings.OPENAI_API_KEY", "fake-key"),
            patch("app.config.settings.STORAGE_PATH", str(tmp_path)),
            patch("httpx.Client", return_value=mock_client),
        ):
            from worker.modules.stock_media.openai_image_provider import OpenAIImageProvider
            provider = OpenAIImageProvider()
            assets = provider.fetch("query", 1, str(tmp_path))

        assert assets == []


# ── Stability AI provider unit tests ─────────────────────────────────────────

class TestStabilityAIProvider:
    def test_returns_empty_when_no_api_key(self, tmp_path):
        with patch("app.config.settings.STABILITY_AI_API_KEY", None):
            from worker.modules.stock_media.stability_provider import StabilityAIProvider
            provider = StabilityAIProvider()
            assets = provider.fetch("query", 2, str(tmp_path))
        assert assets == []

    def test_returns_assets_on_success(self, tmp_path):
        import base64

        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        b64_png = base64.b64encode(fake_png).decode()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"artifacts": [{"base64": b64_png}]}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response

        mock_ffmpeg = MagicMock(returncode=0)

        with (
            patch("app.config.settings.STABILITY_AI_API_KEY", "fake-key"),
            patch("app.config.settings.STORAGE_PATH", str(tmp_path)),
            patch("httpx.Client", return_value=mock_client),
            patch("subprocess.run", return_value=mock_ffmpeg),
        ):
            from worker.modules.stock_media.stability_provider import StabilityAIProvider
            provider = StabilityAIProvider()
            assets = provider.fetch("ancient giants", 1, str(tmp_path))

        assert len(assets) == 1
        assert assets[0].source == "ai"
        assert assets[0].metadata["ai_provider"] == "stability"

    def test_returns_empty_on_api_error(self, tmp_path):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = Exception("network error")

        with (
            patch("app.config.settings.STABILITY_AI_API_KEY", "fake-key"),
            patch("app.config.settings.STORAGE_PATH", str(tmp_path)),
            patch("httpx.Client", return_value=mock_client),
        ):
            from worker.modules.stock_media.stability_provider import StabilityAIProvider
            provider = StabilityAIProvider()
            assets = provider.fetch("query", 1, str(tmp_path))

        assert assets == []
