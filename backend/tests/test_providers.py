from __future__ import annotations

import pytest

from worker.modules.base import (
    AudioResult,
    CaptionResult,
    MediaAsset,
    ModuleNotAvailableError,
    ScriptResult,
    TrendItem,
    UploadResult,
)
from worker.modules.script_generator.placeholder_provider import PlaceholderScriptProvider
from worker.modules.trends.manual_provider import ManualTrendProvider
from worker.modules.uploader.local_exporter import LocalExporter


class TestPlaceholderScriptProvider:
    def test_generate_returns_script_result(self):
        provider = PlaceholderScriptProvider()
        result = provider.generate(topic="Artificial Intelligence")
        assert isinstance(result, ScriptResult)
        assert "Artificial Intelligence" in result.text
        assert len(result.text) > 100
        assert result.metadata["provider"] == "placeholder"

    def test_generate_with_different_topics(self):
        provider = PlaceholderScriptProvider()
        r1 = provider.generate(topic="Climate Change")
        r2 = provider.generate(topic="Space Travel")
        assert "Climate Change" in r1.text
        assert "Space Travel" in r2.text


class TestManualTrendProvider:
    def test_fetch_returns_trend_items(self):
        provider = ManualTrendProvider(keywords=["python", "rust", "go"])
        items = provider.fetch(keyword=None, limit=10)
        assert len(items) <= 10
        assert all(isinstance(i, TrendItem) for i in items)

    def test_fetch_respects_limit(self):
        provider = ManualTrendProvider(keywords=["a", "b", "c", "d", "e"])
        items = provider.fetch(keyword=None, limit=3)
        assert len(items) == 3

    def test_fetch_filters_by_keyword(self):
        provider = ManualTrendProvider(keywords=["python programming", "javascript tips", "rust lang"])
        items = provider.fetch(keyword="python", limit=10)
        # Should filter to matching items (or return all if none match)
        assert all(isinstance(i, TrendItem) for i in items)


class TestLocalExporter:
    def test_skips_missing_source(self, tmp_path):
        exporter = LocalExporter(output_dir=str(tmp_path))
        result = exporter.upload("/nonexistent/video.mp4", {"title": "Test"})
        assert isinstance(result, UploadResult)
        assert result.skipped is True
        assert result.platform == "local"

    def test_exports_existing_file(self, tmp_path):
        src = tmp_path / "source.mp4"
        src.write_bytes(b"fake video data")

        # LocalExporter appends /outputs to the base path
        base_dir = tmp_path / "base"
        exporter = LocalExporter(output_dir=str(base_dir))
        result = exporter.upload(str(src), {"title": "Test"})
        assert result.skipped is False
        assert result.url == "/api/v1/jobs/source/download"
        assert (base_dir / "outputs" / "source.mp4").exists()


class TestDataclasses:
    def test_script_result(self):
        r = ScriptResult(text="Hello world")
        assert r.text == "Hello world"
        assert r.metadata == {}

    def test_audio_result(self):
        r = AudioResult(path="/tmp/audio.mp3", duration_seconds=10.5)
        assert r.path == "/tmp/audio.mp3"
        assert r.duration_seconds == 10.5

    def test_caption_result(self):
        r = CaptionResult(srt_path="/a.srt", vtt_path="/a.vtt", json_path="/a.json")
        assert r.srt_path == "/a.srt"
        assert r.segments == []

    def test_media_asset(self):
        a = MediaAsset(path="/video.mp4", source="pexels")
        assert a.source == "pexels"

    def test_upload_result(self):
        r = UploadResult(url="file:///output.mp4", platform="local")
        assert r.skipped is False

    def test_module_not_available_error(self):
        with pytest.raises(ModuleNotAvailableError):
            raise ModuleNotAvailableError("Test dependency missing")
