"""Tests for TTS status and warning values stored in output_metadata and
surfaced through JobResponse computed fields."""
from __future__ import annotations

import pytest

from app.schemas.job import JobResponse


def _make_job_response(**overrides) -> JobResponse:
    """Build a minimal JobResponse for unit testing computed fields."""
    base: dict = {
        "id": "00000000-0000-0000-0000-000000000001",
        "project_id": None,
        "user_id": 1,
        "title": "Test Job",
        "status": "completed",
        "job_type": "manual",
        "input_data": None,
        "dry_run": False,
        "max_retries": 3,
        "output_path": None,
        "output_metadata": None,
        "logs": [],
        "error_message": None,
        "retry_count": 0,
        "celery_task_id": None,
        "validation_result": None,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "started_at": None,
        "completed_at": None,
    }
    base.update(overrides)
    return JobResponse.model_validate(base)


class TestTTSStatusComputedFields:
    def test_tts_status_none_when_no_output_metadata(self):
        job = _make_job_response(output_metadata=None)
        assert job.tts_status is None
        assert job.tts_warning is None

    def test_tts_status_none_when_metadata_has_no_tts_keys(self):
        job = _make_job_response(output_metadata={"upload_url": "file:///out.mp4"})
        assert job.tts_status is None
        assert job.tts_warning is None

    def test_tts_status_success(self):
        job = _make_job_response(output_metadata={"tts_status": "success"})
        assert job.tts_status == "success"
        assert job.tts_warning is None

    def test_tts_status_skipped_with_warning(self):
        warning = "TTS was skipped. No provider is configured. Video will render without voiceover."
        job = _make_job_response(output_metadata={
            "tts_status": "skipped",
            "tts_warning": warning,
        })
        assert job.tts_status == "skipped"
        assert job.tts_warning == warning

    def test_tts_status_failed_with_warning(self):
        error = "TTS provider EdgeTTSProvider failed: network timeout"
        job = _make_job_response(output_metadata={
            "tts_status": "failed",
            "tts_warning": error,
        })
        assert job.tts_status == "failed"
        assert job.tts_warning == error

    def test_tts_status_coexists_with_other_metadata(self):
        """tts_status/tts_warning should be readable alongside stock_provider etc."""
        job = _make_job_response(output_metadata={
            "upload_url": "file:///out.mp4",
            "stock_provider": "pexels",
            "clip_sources": ["pexels", "pexels"],
            "tts_status": "skipped",
            "tts_warning": "No provider configured.",
        })
        assert job.tts_status == "skipped"
        assert job.tts_warning == "No provider configured."
        # Other metadata keys still accessible via output_metadata
        assert job.output_metadata["stock_provider"] == "pexels"
        assert job.output_metadata["upload_url"] == "file:///out.mp4"

    def test_output_metadata_merge_preserves_tts_fields(self):
        """Verify that the upload_url merge pattern used in Step 10 of the
        pipeline does not erase previously written tts_status."""
        existing: dict = {"tts_status": "skipped", "tts_warning": "No provider."}
        merged = {**existing, "upload_url": "file:///out.mp4"}
        job = _make_job_response(output_metadata=merged)
        assert job.tts_status == "skipped"
        assert job.tts_warning == "No provider."
        assert job.output_metadata["upload_url"] == "file:///out.mp4"
