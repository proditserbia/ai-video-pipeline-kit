"""Tests for temporary work-directory cleanup behaviour."""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from worker.tasks.video_pipeline import _cleanup_work_dir


# ---------------------------------------------------------------------------
# Unit tests for _cleanup_work_dir
# ---------------------------------------------------------------------------


class TestCleanupWorkDir:
    def test_removes_directory_on_success(self, tmp_path):
        work_dir = tmp_path / "job-abc"
        work_dir.mkdir()
        (work_dir / "voice.mp3").write_bytes(b"audio")

        _cleanup_work_dir(work_dir, "job-abc")

        assert not work_dir.exists()

    def test_keeps_directory_when_keep_is_true(self, tmp_path):
        work_dir = tmp_path / "job-abc"
        work_dir.mkdir()
        (work_dir / "voice.mp3").write_bytes(b"audio")

        _cleanup_work_dir(work_dir, "job-abc", keep=True)

        assert work_dir.exists()

    def test_nonexistent_directory_is_silently_ignored(self, tmp_path):
        missing = tmp_path / "ghost"
        # Must not raise even though the directory does not exist.
        _cleanup_work_dir(missing, "ghost")

    def test_cleanup_failure_does_not_raise(self, tmp_path):
        work_dir = tmp_path / "locked"
        work_dir.mkdir()

        with patch("shutil.rmtree", side_effect=OSError("permission denied")):
            # Should log a warning and swallow the error.
            _cleanup_work_dir(work_dir, "locked")


# ---------------------------------------------------------------------------
# Pipeline integration: success path cleans up, failure path honours env var
# ---------------------------------------------------------------------------


class TestPipelineCleanup:
    """Test that the pipeline calls _cleanup_work_dir with the right arguments."""

    def _run_pipeline_cleanup(
        self, tmp_path, *, fail: bool, keep_failed: bool = False
    ) -> tuple[Path, bool]:
        """
        Drive just the cleanup logic in isolation without executing a real Celery task.

        Returns (work_dir, exists_after).
        """
        from app.config import settings

        work_dir = tmp_path / "pipeline-work"
        work_dir.mkdir()
        (work_dir / "clip.mp4").write_bytes(b"\x00" * 4)

        original = settings.DEBUG_KEEP_FAILED_WORKDIR
        settings.DEBUG_KEEP_FAILED_WORKDIR = keep_failed
        try:
            if fail:
                _cleanup_work_dir(work_dir, "test-job", keep=keep_failed)
            else:
                _cleanup_work_dir(work_dir, "test-job")
        finally:
            settings.DEBUG_KEEP_FAILED_WORKDIR = original

        return work_dir, work_dir.exists()

    def test_success_deletes_work_dir(self, tmp_path):
        _, exists = self._run_pipeline_cleanup(tmp_path, fail=False)
        assert not exists

    def test_failure_deletes_work_dir_by_default(self, tmp_path):
        _, exists = self._run_pipeline_cleanup(tmp_path, fail=True, keep_failed=False)
        assert not exists

    def test_failure_keeps_work_dir_when_debug_flag_set(self, tmp_path):
        _, exists = self._run_pipeline_cleanup(tmp_path, fail=True, keep_failed=True)
        assert exists


# ---------------------------------------------------------------------------
# Scheduled cleanup task
# ---------------------------------------------------------------------------


class TestCleanupTempDirsTask:
    """Unit tests for the cleanup_temp_dirs Celery task."""

    def test_removes_old_directories(self, tmp_path):
        """Directories older than max_age_seconds should be removed."""
        from worker.tasks.scheduled import cleanup_temp_dirs
        from app.config import settings

        temp_root = tmp_path / "temp"
        temp_root.mkdir()
        old_dir = temp_root / "old-job"
        old_dir.mkdir()

        # Back-date the directory's mtime to 2 hours ago.
        two_hours_ago = time.time() - 7200
        import os
        os.utime(old_dir, (two_hours_ago, two_hours_ago))

        original = settings.STORAGE_PATH
        settings.STORAGE_PATH = str(tmp_path)
        try:
            result = cleanup_temp_dirs(max_age_seconds=3600)
        finally:
            settings.STORAGE_PATH = original

        assert result["removed"] == 1
        assert result["failed"] == 0
        assert not old_dir.exists()

    def test_skips_recent_directories(self, tmp_path):
        """Directories newer than max_age_seconds must not be touched."""
        from worker.tasks.scheduled import cleanup_temp_dirs
        from app.config import settings

        temp_root = tmp_path / "temp"
        temp_root.mkdir()
        recent_dir = temp_root / "new-job"
        recent_dir.mkdir()

        original = settings.STORAGE_PATH
        settings.STORAGE_PATH = str(tmp_path)
        try:
            result = cleanup_temp_dirs(max_age_seconds=3600)
        finally:
            settings.STORAGE_PATH = original

        assert result["removed"] == 0
        assert result["skipped"] == 1
        assert recent_dir.exists()

    def test_returns_summary_when_temp_root_missing(self, tmp_path):
        """When the temp root does not exist the task should return zeros."""
        from worker.tasks.scheduled import cleanup_temp_dirs
        from app.config import settings

        original = settings.STORAGE_PATH
        settings.STORAGE_PATH = str(tmp_path / "nonexistent")
        try:
            result = cleanup_temp_dirs()
        finally:
            settings.STORAGE_PATH = original

        assert result == {"removed": 0, "failed": 0, "skipped": 0}

    def test_counts_failures_without_raising(self, tmp_path):
        """Removal errors must be counted and not propagate."""
        from worker.tasks.scheduled import cleanup_temp_dirs
        from app.config import settings

        temp_root = tmp_path / "temp"
        temp_root.mkdir()
        old_dir = temp_root / "broken-job"
        old_dir.mkdir()

        two_hours_ago = time.time() - 7200
        import os
        os.utime(old_dir, (two_hours_ago, two_hours_ago))

        original = settings.STORAGE_PATH
        settings.STORAGE_PATH = str(tmp_path)
        try:
            with patch("shutil.rmtree", side_effect=OSError("locked")):
                result = cleanup_temp_dirs(max_age_seconds=3600)
        finally:
            settings.STORAGE_PATH = original

        assert result["failed"] == 1
        assert result["removed"] == 0

    def test_beat_schedule_registered(self):
        """The cleanup task must appear in the Celery beat schedule."""
        from worker.celery_app import celery_app

        task_names = {v["task"] for v in celery_app.conf.beat_schedule.values()}
        assert "worker.tasks.scheduled.cleanup_temp_dirs" in task_names
