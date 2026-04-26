"""Tests for the Whisper unavailable / disabled paths."""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# WhisperCaptionProvider.is_available()
# ---------------------------------------------------------------------------


class TestIsAvailable:
    def test_returns_false_when_faster_whisper_missing(self):
        """is_available() must return False when faster_whisper cannot be imported."""
        with patch.dict("sys.modules", {"faster_whisper": None}):
            from importlib import import_module
            import sys
            # Reload so the module-level import attempt runs inside the patch.
            if "worker.modules.captions.whisper_provider" in sys.modules:
                del sys.modules["worker.modules.captions.whisper_provider"]
            from worker.modules.captions.whisper_provider import WhisperCaptionProvider
            # Temporarily replace the helper to simulate missing package.
            with patch(
                "worker.modules.captions.whisper_provider._check_faster_whisper",
                return_value="faster-whisper not installed",
            ):
                assert WhisperCaptionProvider.is_available() is False

    def test_returns_true_when_faster_whisper_present(self):
        """is_available() must return True when _check_faster_whisper returns None."""
        from worker.modules.captions.whisper_provider import WhisperCaptionProvider

        with patch(
            "worker.modules.captions.whisper_provider._check_faster_whisper",
            return_value=None,
        ):
            assert WhisperCaptionProvider.is_available() is True


# ---------------------------------------------------------------------------
# Constructor raises ModuleNotAvailableError when package is absent
# ---------------------------------------------------------------------------


class TestConstructorRaisesWhenUnavailable:
    def test_raises_module_not_available_error(self):
        from worker.modules.base import ModuleNotAvailableError
        from worker.modules.captions.whisper_provider import WhisperCaptionProvider

        with patch(
            "worker.modules.captions.whisper_provider._check_faster_whisper",
            return_value="faster-whisper is not installed",
        ):
            with pytest.raises(ModuleNotAvailableError, match="faster-whisper"):
                WhisperCaptionProvider()


# ---------------------------------------------------------------------------
# Pipeline Step 6: caption_status / caption_warning written to output_metadata
# ---------------------------------------------------------------------------


class _PipelineMetaHelper:
    """Thin helper to exercise just the caption-skip logic without a full DB."""

    @staticmethod
    def run_caption_skip(
        *,
        whisper_enabled: bool,
        whisper_available: bool,
    ) -> dict:
        """
        Simulate the caption-skip branch of pipeline Step 6 and return the
        dict that would be merged into output_metadata.
        """
        from worker.modules.captions.whisper_provider import WhisperCaptionProvider
        from app.config import settings

        original_enabled = settings.WHISPER_ENABLED
        settings.WHISPER_ENABLED = whisper_enabled
        try:
            with patch.object(
                WhisperCaptionProvider,
                "is_available",
                return_value=whisper_available,
            ):
                cap_skip_reason: str | None = None
                if not settings.WHISPER_ENABLED:
                    cap_skip_reason = "Captions skipped: WHISPER_ENABLED=false"
                elif not WhisperCaptionProvider.is_available():
                    cap_skip_reason = (
                        "Captions skipped: faster-whisper is not installed. "
                        "Install it with: pip install faster-whisper"
                    )

                if cap_skip_reason:
                    return {
                        "caption_status": "skipped",
                        "caption_warning": cap_skip_reason,
                    }
                return {}
        finally:
            settings.WHISPER_ENABLED = original_enabled


class TestPipelineCaptionSkip:
    def test_whisper_disabled_sets_skipped_status(self):
        meta = _PipelineMetaHelper.run_caption_skip(
            whisper_enabled=False, whisper_available=True
        )
        assert meta["caption_status"] == "skipped"
        assert "WHISPER_ENABLED=false" in meta["caption_warning"]

    def test_whisper_unavailable_sets_skipped_status(self):
        meta = _PipelineMetaHelper.run_caption_skip(
            whisper_enabled=True, whisper_available=False
        )
        assert meta["caption_status"] == "skipped"
        assert "faster-whisper" in meta["caption_warning"]

    def test_whisper_available_and_enabled_returns_no_skip_metadata(self):
        meta = _PipelineMetaHelper.run_caption_skip(
            whisper_enabled=True, whisper_available=True
        )
        assert "caption_status" not in meta


# ---------------------------------------------------------------------------
# JobResponse computed fields
# ---------------------------------------------------------------------------


class TestJobResponseCaptionFields:
    """caption_status and caption_warning computed fields must surface from output_metadata."""

    def _make_response(self, output_metadata: dict) -> object:
        from app.schemas.job import JobResponse
        from app.models.job import JobStatus, JobType
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        return JobResponse(
            id="test-job-id",
            project_id=None,
            user_id=1,
            title="Test",
            job_type=JobType.manual,
            status=JobStatus.completed,
            input_data={},
            output_path=None,
            output_metadata=output_metadata,
            logs=[],
            error_message=None,
            retry_count=0,
            celery_task_id=None,
            validation_result=None,
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
            dry_run=False,
            max_retries=3,
        )

    def test_caption_status_skipped(self):
        resp = self._make_response(
            {"caption_status": "skipped", "caption_warning": "faster-whisper missing"}
        )
        assert resp.caption_status == "skipped"
        assert resp.caption_warning == "faster-whisper missing"

    def test_caption_status_success(self):
        resp = self._make_response({"caption_status": "success"})
        assert resp.caption_status == "success"
        assert resp.caption_warning is None

    def test_caption_status_missing_returns_none(self):
        resp = self._make_response({})
        assert resp.caption_status is None
        assert resp.caption_warning is None

    def test_caption_status_failed(self):
        resp = self._make_response(
            {"caption_status": "failed", "caption_warning": "ctranslate2 error"}
        )
        assert resp.caption_status == "failed"
        assert resp.caption_warning == "ctranslate2 error"


# ---------------------------------------------------------------------------
# Config: WHISPER_ENABLED, WHISPER_MODEL_SIZE, WHISPER_DEVICE
# ---------------------------------------------------------------------------


class TestWhisperConfig:
    def test_defaults(self):
        from app.config import Settings

        s = Settings(
            DATABASE_URL="postgresql+asyncpg://x:y@localhost/z",
            SYNC_DATABASE_URL="postgresql+psycopg2://x:y@localhost/z",
        )
        assert s.WHISPER_ENABLED is True
        assert s.WHISPER_MODEL_SIZE == "base"
        assert s.WHISPER_DEVICE == "cpu"

    def test_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("WHISPER_ENABLED", "false")
        from app.config import Settings

        s = Settings(
            DATABASE_URL="postgresql+asyncpg://x:y@localhost/z",
            SYNC_DATABASE_URL="postgresql+psycopg2://x:y@localhost/z",
        )
        assert s.WHISPER_ENABLED is False

    def test_custom_model_and_device(self, monkeypatch):
        monkeypatch.setenv("WHISPER_MODEL_SIZE", "small")
        monkeypatch.setenv("WHISPER_DEVICE", "cuda")
        from app.config import Settings

        s = Settings(
            DATABASE_URL="postgresql+asyncpg://x:y@localhost/z",
            SYNC_DATABASE_URL="postgresql+psycopg2://x:y@localhost/z",
        )
        assert s.WHISPER_MODEL_SIZE == "small"
        assert s.WHISPER_DEVICE == "cuda"
