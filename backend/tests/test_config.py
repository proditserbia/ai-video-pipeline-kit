from __future__ import annotations

import pytest

from app.config import Settings
from app.core.feature_flags import FeatureFlags


def test_default_settings():
    s = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/test",
        SYNC_DATABASE_URL="postgresql+psycopg2://u:p@localhost/test",
        SECRET_KEY="a-secret-key-that-is-32-chars!!!",
    )
    assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 30
    assert s.ALGORITHM == "HS256"
    assert s.EDGE_TTS_ENABLED is False
    assert s.COQUI_TTS_ENABLED is False
    assert s.MAX_JOB_RETRIES == 3
    assert s.DRY_RUN is False


def test_feature_flags_defaults():
    flags = FeatureFlags()
    assert flags.is_enabled("core_video") is True
    assert flags.is_enabled("ai_scripts") is True
    assert flags.is_enabled("tts") is True
    assert flags.is_enabled("gpu_rendering") is False
    assert flags.is_enabled("nonexistent_flag") is False


def test_feature_flags_get_all():
    flags = FeatureFlags()
    all_flags = flags.get_all()
    assert isinstance(all_flags, dict)
    assert "core_video" in all_flags
    assert "cloud_storage" in all_flags


def test_feature_flags_json_parsing():
    import json
    raw = json.dumps({"core_video": True, "tts": False})
    s = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/test",
        SYNC_DATABASE_URL="postgresql+psycopg2://u:p@localhost/test",
        SECRET_KEY="a-secret-key-that-is-32-chars!!!",
        FEATURE_FLAGS=raw,
    )
    assert s.FEATURE_FLAGS["core_video"] is True
    assert s.FEATURE_FLAGS["tts"] is False
