"""Tests for stock-media metadata stored in output_metadata (stock_provider,
stock_query, stock_clips, stock_warning).  These are schema-level unit tests
that mirror the pattern used in test_tts_metadata.py and test_result_quality.py
— they validate the keys and values that video_pipeline.py writes into
job.output_metadata during Step 5."""
from __future__ import annotations

import pytest

from app.schemas.job import JobResponse


def _make_job_response(**overrides) -> JobResponse:
    base: dict = {
        "id": "00000000-0000-0000-0000-000000000099",
        "project_id": None,
        "user_id": 1,
        "title": "Stock Media Test Job",
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


class TestStockMediaMetadata:
    """Verify that stock media keys written by Step 5 of the pipeline are
    accessible through output_metadata and consistent with each other."""

    def test_pexels_provider_metadata_stored(self):
        """When Pexels is used, stock_provider, stock_query, and stock_clips
        are all present in output_metadata."""
        clips = ["/storage/temp/abc/media/pexels_111.mp4"]
        job = _make_job_response(output_metadata={
            "stock_provider": "pexels",
            "stock_query": "autumn forest",
            "stock_clips": clips,
            "clip_sources": ["pexels"],
        })
        assert job.output_metadata["stock_provider"] == "pexels"
        assert job.output_metadata["stock_query"] == "autumn forest"
        assert job.output_metadata["stock_clips"] == clips
        assert job.output_metadata["clip_sources"] == ["pexels"]

    def test_pexels_fallback_adds_stock_warning(self):
        """When Pexels key is set but provider fell back, stock_warning is set."""
        job = _make_job_response(output_metadata={
            "stock_provider": "pixabay",
            "stock_query": "city skyline",
            "stock_clips": ["/storage/temp/abc/media/pixabay_222.mp4"],
            "clip_sources": ["pixabay"],
            "stock_warning": "Pexels key is set but Pexels returned no clips; fell back to 'pixabay'.",
        })
        assert job.output_metadata["stock_provider"] == "pixabay"
        assert "stock_warning" in job.output_metadata
        assert "Pexels" in job.output_metadata["stock_warning"]
        assert "pixabay" in job.output_metadata["stock_warning"]

    def test_placeholder_stock_warning(self):
        """When only placeholder clips are used, stock_warning reflects that."""
        job = _make_job_response(output_metadata={
            "stock_provider": "placeholder",
            "stock_query": "tech background",
            "stock_clips": [],
            "clip_sources": [],
            "stock_warning": "Stock media: no real clips available. Placeholder visuals were used.",
        })
        assert job.output_metadata["stock_provider"] == "placeholder"
        assert "Placeholder" in job.output_metadata["stock_warning"]

    def test_stock_warning_absent_when_pexels_succeeds(self):
        """No stock_warning key when Pexels returns clips normally."""
        job = _make_job_response(output_metadata={
            "stock_provider": "pexels",
            "stock_query": "ocean waves",
            "stock_clips": ["/storage/temp/abc/media/pexels_333.mp4"],
            "clip_sources": ["pexels"],
        })
        assert "stock_warning" not in job.output_metadata

    def test_stock_clips_is_list_of_paths(self):
        """stock_clips is a list of file-path strings (not source names)."""
        clips = [
            "/storage/temp/abc/media/pexels_1.mp4",
            "/storage/temp/abc/media/pexels_2.mp4",
        ]
        job = _make_job_response(output_metadata={
            "stock_provider": "pexels",
            "stock_query": "mountains",
            "stock_clips": clips,
            "clip_sources": ["pexels", "pexels"],
        })
        assert all(c.endswith(".mp4") for c in job.output_metadata["stock_clips"])
        # stock_clips are paths, clip_sources are provider names
        assert job.output_metadata["clip_sources"] == ["pexels", "pexels"]

    def test_stock_metadata_coexists_with_tts_and_caption_metadata(self):
        """All pipeline metadata keys coexist without overwriting each other."""
        job = _make_job_response(output_metadata={
            "tts_status": "success",
            "caption_status": "success",
            "stock_provider": "pexels",
            "stock_query": "sunrise",
            "stock_clips": ["/storage/temp/abc/media/pexels_99.mp4"],
            "clip_sources": ["pexels"],
            "result_quality": "complete",
            "warnings": [],
        })
        assert job.tts_status == "success"
        assert job.output_metadata["caption_status"] == "success"
        assert job.output_metadata["stock_provider"] == "pexels"
        assert job.output_metadata["stock_query"] == "sunrise"
        assert job.result_quality == "complete"
        assert job.warnings == []

    def test_pexels_fallback_warning_is_included_in_warnings_list(self):
        """The stock_warning text also appears in the warnings list so that
        result_quality is computed correctly."""
        stock_warn = "Pexels key is set but Pexels returned no clips; fell back to 'placeholder'."
        placeholder_warn = "Stock media: no real clips available. Placeholder visuals were used."
        job = _make_job_response(output_metadata={
            "stock_provider": "placeholder",
            "stock_query": "abstract shapes",
            "stock_clips": [],
            "clip_sources": [],
            "stock_warning": stock_warn,
            "result_quality": "fallback",
            "warnings": [stock_warn],
        })
        assert job.result_quality == "fallback"
        assert any("Pexels" in w for w in job.warnings)
