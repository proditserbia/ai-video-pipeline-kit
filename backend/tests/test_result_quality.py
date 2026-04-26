"""Tests for result_quality and warnings classification in output_metadata,
surfaced through JobResponse computed fields."""
from __future__ import annotations

import pytest

from app.schemas.job import JobResponse


def _make_job_response(**overrides) -> JobResponse:
    """Build a minimal JobResponse for unit testing computed fields."""
    base: dict = {
        "id": "00000000-0000-0000-0000-000000000002",
        "project_id": None,
        "user_id": 1,
        "title": "Quality Test Job",
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


class TestResultQualityComputedField:
    def test_result_quality_none_when_no_metadata(self):
        job = _make_job_response(output_metadata=None)
        assert job.result_quality is None

    def test_result_quality_none_when_key_absent(self):
        job = _make_job_response(output_metadata={"upload_url": "file:///out.mp4"})
        assert job.result_quality is None

    def test_result_quality_complete(self):
        job = _make_job_response(output_metadata={
            "result_quality": "complete",
            "warnings": [],
        })
        assert job.result_quality == "complete"
        assert job.warnings == []

    def test_result_quality_partial_tts_skipped(self):
        """No TTS provider → partial."""
        job = _make_job_response(output_metadata={
            "tts_status": "skipped",
            "tts_warning": "TTS was skipped. No provider is configured.",
            "result_quality": "partial",
            "warnings": ["TTS was skipped. No provider is configured."],
        })
        assert job.result_quality == "partial"
        assert len(job.warnings) == 1
        assert "TTS" in job.warnings[0]

    def test_result_quality_partial_tts_failed(self):
        """TTS provider raised → partial."""
        err = "TTS provider EdgeTTSProvider failed: network timeout"
        job = _make_job_response(output_metadata={
            "tts_status": "failed",
            "tts_warning": err,
            "result_quality": "partial",
            "warnings": [err],
        })
        assert job.result_quality == "partial"
        assert job.warnings[0] == err

    def test_result_quality_partial_captions_skipped(self):
        """Caption generation exception → partial."""
        warn = "Captions were skipped: whisper model not found"
        job = _make_job_response(output_metadata={
            "result_quality": "partial",
            "warnings": [warn],
        })
        assert job.result_quality == "partial"
        assert job.warnings == [warn]

    def test_result_quality_fallback_placeholder_stock(self):
        """Placeholder stock media only → fallback."""
        warn = "Stock media: no real clips available. Placeholder visuals were used."
        job = _make_job_response(output_metadata={
            "stock_provider": "placeholder",
            "result_quality": "fallback",
            "warnings": [warn],
        })
        assert job.result_quality == "fallback"
        assert len(job.warnings) == 1
        assert "Placeholder" in job.warnings[0]

    def test_result_quality_partial_overrides_fallback(self):
        """If both TTS and placeholder stock are bad, result should be partial."""
        tts_warn = "TTS was skipped. No provider is configured."
        stock_warn = "Stock media: no real clips available. Placeholder visuals were used."
        job = _make_job_response(output_metadata={
            "tts_status": "skipped",
            "tts_warning": tts_warn,
            "stock_provider": "placeholder",
            "result_quality": "partial",
            "warnings": [tts_warn, stock_warn],
        })
        assert job.result_quality == "partial"
        assert len(job.warnings) == 2

    def test_multiple_warnings_all_surfaced(self):
        """All accumulated warnings are present in the warnings list."""
        tts_warn = "TTS was skipped. No provider is configured."
        cap_warn = "Captions were skipped: model error"
        job = _make_job_response(output_metadata={
            "result_quality": "partial",
            "warnings": [tts_warn, cap_warn],
        })
        assert job.warnings == [tts_warn, cap_warn]

    def test_warnings_empty_list_when_complete(self):
        job = _make_job_response(output_metadata={
            "result_quality": "complete",
            "warnings": [],
            "upload_url": "file:///out.mp4",
        })
        assert job.warnings == []
        assert job.result_quality == "complete"

    def test_warnings_returns_empty_list_when_metadata_has_no_warnings_key(self):
        job = _make_job_response(output_metadata={"upload_url": "file:///out.mp4"})
        assert job.warnings == []

    def test_result_quality_coexists_with_tts_and_stock_metadata(self):
        """All related keys coexist in output_metadata without conflict."""
        job = _make_job_response(output_metadata={
            "tts_status": "skipped",
            "tts_warning": "TTS skipped.",
            "stock_provider": "pexels",
            "clip_sources": ["pexels", "pexels"],
            "upload_url": "file:///out.mp4",
            "result_quality": "partial",
            "warnings": ["TTS skipped."],
        })
        assert job.result_quality == "partial"
        assert job.tts_status == "skipped"
        assert job.output_metadata["stock_provider"] == "pexels"
        assert job.output_metadata["upload_url"] == "file:///out.mp4"
        assert job.warnings == ["TTS skipped."]
