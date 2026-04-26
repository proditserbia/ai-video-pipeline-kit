"""Tests for brand-asset resolution and builder argument passing."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from worker.tasks.video_pipeline import _resolve_brand_assets


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_asset(asset_id: int, file_path: str) -> MagicMock:
    """Return a mock Asset ORM object."""
    a = MagicMock()
    a.id = asset_id
    a.file_path = file_path
    return a


def _make_project(
    watermark_asset_id=None,
    background_music_asset_id=None,
) -> MagicMock:
    p = MagicMock()
    p.watermark_asset_id = watermark_asset_id
    p.background_music_asset_id = background_music_asset_id
    return p


def _make_job(project_id=None) -> MagicMock:
    j = MagicMock()
    j.project_id = project_id
    return j


def _make_db(assets: dict[int, MagicMock], project: MagicMock | None = None) -> MagicMock:
    """Return a mock synchronous DB session.

    ``assets`` maps asset_id → mock Asset.
    Queries for Asset.id filter returns the matching asset or None.
    Queries for Project.id filter returns ``project``.
    """
    from app.models.asset import Asset
    from app.models.project import Project

    def fake_query(model):
        mock_q = MagicMock()
        if model is Asset:
            def filter_asset(condition):
                # Extract the right-hand value of the == comparison.
                # condition is a sqlalchemy BinaryExpression; we compare
                # its right-hand side against known asset IDs.
                result_mock = MagicMock()
                result_mock.first.return_value = None
                for aid, asset in assets.items():
                    try:
                        # SQLAlchemy column == value stores value in .right.value
                        if condition.right.value == aid:
                            result_mock.first.return_value = asset
                            break
                    except AttributeError:
                        pass
                return result_mock
            mock_q.filter = filter_asset
        elif model is Project:
            def filter_project(condition):
                result_mock = MagicMock()
                result_mock.first.return_value = project
                return result_mock
            mock_q.filter = filter_project
        return mock_q

    db = MagicMock()
    db.query = fake_query
    return db


# ---------------------------------------------------------------------------
# Unit tests for _resolve_brand_assets
# ---------------------------------------------------------------------------


class TestResolveBrandAssetsInputDataOverride:
    """input_data keys take priority over project settings."""

    def test_flat_watermark_asset_id_used(self, tmp_path):
        wm_file = tmp_path / "wm.png"
        wm_file.touch()
        asset = _make_asset(10, str(wm_file))
        db = _make_db({10: asset})
        job = _make_job(project_id=None)

        wm_id, wm_path, bg_id, bg_path = _resolve_brand_assets(
            db, {"watermark_asset_id": 10}, job
        )
        assert wm_id == 10
        assert wm_path == Path(str(wm_file))
        assert bg_id is None
        assert bg_path is None

    def test_flat_bg_music_asset_id_used(self, tmp_path):
        bg_file = tmp_path / "bg.mp3"
        bg_file.touch()
        asset = _make_asset(20, str(bg_file))
        db = _make_db({20: asset})
        job = _make_job(project_id=None)

        wm_id, wm_path, bg_id, bg_path = _resolve_brand_assets(
            db, {"bg_music_asset_id": 20}, job
        )
        assert bg_id == 20
        assert bg_path == Path(str(bg_file))
        assert wm_id is None
        assert wm_path is None

    def test_nested_brand_watermark_asset_id_used(self, tmp_path):
        wm_file = tmp_path / "logo.png"
        wm_file.touch()
        asset = _make_asset(7, str(wm_file))
        db = _make_db({7: asset})
        job = _make_job(project_id=None)

        wm_id, wm_path, bg_id, bg_path = _resolve_brand_assets(
            db, {"brand": {"watermark_asset_id": 7}}, job
        )
        assert wm_id == 7
        assert wm_path == Path(str(wm_file))

    def test_input_data_overrides_project(self, tmp_path):
        """When input_data specifies an asset ID the project setting is ignored."""
        job_wm = tmp_path / "job_wm.png"
        job_wm.touch()
        proj_wm = tmp_path / "proj_wm.png"
        proj_wm.touch()

        job_asset = _make_asset(5, str(job_wm))
        proj_asset = _make_asset(99, str(proj_wm))
        db = _make_db({5: job_asset, 99: proj_asset}, project=_make_project(watermark_asset_id=99))
        job = _make_job(project_id=1)

        wm_id, wm_path, _, _ = _resolve_brand_assets(
            db, {"watermark_asset_id": 5}, job
        )
        assert wm_id == 5
        assert wm_path == Path(str(job_wm))


class TestResolveBrandAssetsProjectFallback:
    """When input_data has no override, project brand settings are used."""

    def test_project_watermark_used_when_no_override(self, tmp_path):
        wm_file = tmp_path / "brand_wm.png"
        wm_file.touch()
        asset = _make_asset(3, str(wm_file))
        project = _make_project(watermark_asset_id=3)
        db = _make_db({3: asset}, project=project)
        job = _make_job(project_id=42)

        wm_id, wm_path, bg_id, bg_path = _resolve_brand_assets(db, {}, job)
        assert wm_id == 3
        assert wm_path == Path(str(wm_file))
        assert bg_id is None
        assert bg_path is None

    def test_project_bg_music_used_when_no_override(self, tmp_path):
        bg_file = tmp_path / "brand_bg.mp3"
        bg_file.touch()
        asset = _make_asset(8, str(bg_file))
        project = _make_project(background_music_asset_id=8)
        db = _make_db({8: asset}, project=project)
        job = _make_job(project_id=1)

        _, _, bg_id, bg_path = _resolve_brand_assets(db, {}, job)
        assert bg_id == 8
        assert bg_path == Path(str(bg_file))

    def test_no_project_id_returns_none_paths(self):
        db = _make_db({})
        job = _make_job(project_id=None)
        wm_id, wm_path, bg_id, bg_path = _resolve_brand_assets(db, {}, job)
        assert wm_id is None
        assert wm_path is None
        assert bg_id is None
        assert bg_path is None


class TestResolveBrandAssetsMissingOrInvalid:
    def test_missing_asset_row_returns_none_path(self):
        """Asset ID exists in input_data but not in the DB → path is None."""
        db = _make_db({})  # No assets in DB
        job = _make_job(project_id=None)
        wm_id, wm_path, _, _ = _resolve_brand_assets(db, {"watermark_asset_id": 99}, job)
        assert wm_id == 99
        assert wm_path is None

    def test_invalid_asset_id_string_returns_none(self):
        db = _make_db({})
        job = _make_job(project_id=None)
        wm_id, wm_path, _, _ = _resolve_brand_assets(db, {"watermark_asset_id": "not-an-int"}, job)
        assert wm_id is None
        assert wm_path is None

    def test_none_asset_id_returns_none(self):
        db = _make_db({})
        job = _make_job(project_id=None)
        wm_id, wm_path, bg_id, bg_path = _resolve_brand_assets(
            db, {"watermark_asset_id": None, "bg_music_asset_id": None}, job
        )
        assert wm_id is None
        assert wm_path is None


# ---------------------------------------------------------------------------
# Integration-level: builder receives correct watermark/bg_music paths
# ---------------------------------------------------------------------------


class TestBuilderReceivesBrandAssets:
    """Verify that _compose is called with the resolved paths."""

    def _run_compose(self, srt_path, watermark_path, bg_music_path, audio_path=None):
        """Call _compose with _run mocked; return captured command."""
        from worker.modules.video_builder.ffmpeg_builder import FFmpegVideoBuilder

        captured: list[list[str]] = []

        def fake_run(cmd):
            captured.append(cmd)
            return MagicMock(returncode=0)

        builder = FFmpegVideoBuilder()
        output = srt_path.parent / "out.mp4" if srt_path else Path("/tmp/out.mp4")
        video = Path("/tmp/input.mp4")

        with patch("worker.modules.video_builder.ffmpeg_builder._run", side_effect=fake_run):
            builder._compose(
                video=video,
                audio_path=audio_path,
                srt_path=srt_path,
                output_path=output,
                use_nvenc=False,
                watermark_path=watermark_path,
                bg_music_path=bg_music_path,
                bg_music_volume=0.15,
                caption_style=None,
            )
        return captured[0]

    def test_watermark_path_added_as_input(self, tmp_path):
        """A real watermark file triggers an extra -i flag in the command."""
        wm = tmp_path / "wm.png"
        wm.write_bytes(b"\x89PNG")  # non-empty so .exists() is True

        cmd = self._run_compose(None, wm, None)
        assert str(wm) in cmd

    def test_bg_music_path_added_as_input(self, tmp_path):
        bg = tmp_path / "bg.mp3"
        bg.write_bytes(b"ID3")
        # bg_music_path is only included when an audio (voice) track is also present
        audio = tmp_path / "voice.mp3"
        audio.write_bytes(b"audio")

        cmd = self._run_compose(None, None, bg, audio_path=audio)
        assert str(bg) in cmd

    def test_missing_watermark_file_not_in_command(self, tmp_path):
        """Non-existent watermark path should not appear in the command."""
        missing = tmp_path / "ghost.png"  # Never created

        cmd = self._run_compose(None, missing, None)
        assert str(missing) not in cmd

    def test_both_assets_appear_in_command(self, tmp_path):
        wm = tmp_path / "wm.png"
        wm.write_bytes(b"\x89PNG")
        bg = tmp_path / "bg.mp3"
        bg.write_bytes(b"ID3")
        audio = tmp_path / "voice.mp3"
        audio.write_bytes(b"audio")

        cmd = self._run_compose(None, wm, bg, audio_path=audio)
        assert str(wm) in cmd
        assert str(bg) in cmd
