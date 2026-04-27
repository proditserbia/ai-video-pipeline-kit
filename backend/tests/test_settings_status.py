"""Tests for GET /api/v1/settings/status.

Validates:
- The endpoint requires authentication.
- No actual API key values are ever exposed.
- key_present booleans reflect the true presence of each secret.
- Media config fields are rendered correctly.
- Optional providers that are absent appear as False / "none".
- Graceful response when the endpoint is called with a valid token.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Authentication guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_settings_status_requires_auth(client):
    response = await client.get("/api/settings/status")
    # HTTPBearer returns 403 when the Authorization header is absent entirely.
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# No secrets exposed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_settings_status_does_not_expose_openai_key(client, admin_token):
    key = "sk-supersecret-openai-key"
    with patch("app.config.settings.OPENAI_API_KEY", key):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert response.status_code == 200
    body = response.text
    # The real key must never appear anywhere in the response body.
    assert key not in body


@pytest.mark.asyncio
async def test_settings_status_does_not_expose_pexels_key(client, admin_token):
    key = "pexels-real-secret-key-xyz"
    with patch("app.config.settings.PEXELS_API_KEY", key):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert response.status_code == 200
    assert key not in response.text


@pytest.mark.asyncio
async def test_settings_status_does_not_expose_stability_key(client, admin_token):
    key = "stability-super-secret-99"
    with patch("app.config.settings.STABILITY_AI_API_KEY", key):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    assert response.status_code == 200
    assert key not in response.text


# ---------------------------------------------------------------------------
# key_present booleans
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_openai_key_present_true_when_set(client, admin_token):
    with patch("app.config.settings.OPENAI_API_KEY", "sk-real"):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    data = response.json()
    assert data["providers"]["openai_api_key_present"] is True


@pytest.mark.asyncio
async def test_openai_key_present_false_when_not_set(client, admin_token):
    with patch("app.config.settings.OPENAI_API_KEY", None):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    data = response.json()
    assert data["providers"]["openai_api_key_present"] is False


@pytest.mark.asyncio
async def test_pexels_key_present_false_when_not_set(client, admin_token):
    with patch("app.config.settings.PEXELS_API_KEY", None):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    data = response.json()
    assert data["providers"]["pexels_api_key_present"] is False


@pytest.mark.asyncio
async def test_pexels_key_present_true_when_set(client, admin_token):
    with patch("app.config.settings.PEXELS_API_KEY", "px-key-real"):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    data = response.json()
    assert data["providers"]["pexels_api_key_present"] is True


@pytest.mark.asyncio
async def test_elevenlabs_key_present_false_when_not_set(client, admin_token):
    with patch("app.config.settings.ELEVENLABS_API_KEY", None):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    data = response.json()
    assert data["providers"]["elevenlabs_api_key_present"] is False


# ---------------------------------------------------------------------------
# Media config fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_media_mode_reflected(client, admin_token):
    with patch("app.config.settings.MEDIA_MODE", "ai"):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    data = response.json()
    assert data["media"]["media_mode"] == "ai"


@pytest.mark.asyncio
async def test_ai_image_enabled_reflected(client, admin_token):
    with (
        patch("app.config.settings.AI_IMAGE_ENABLED", True),
        patch("app.config.settings.MEDIA_MODE", "ai"),
    ):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    data = response.json()
    assert data["media"]["ai_image_enabled"] is True
    # paragraph_tts_sync_enabled mirrors AI_IMAGE_ENABLED
    assert data["media"]["paragraph_tts_sync_enabled"] is True


@pytest.mark.asyncio
async def test_visual_shot_plan_enabled_reflected(client, admin_token):
    with patch("app.config.settings.VISUAL_SHOT_PLAN_ENABLED", False):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    data = response.json()
    assert data["media"]["visual_shot_plan_enabled"] is False


# ---------------------------------------------------------------------------
# TTS provider inference
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tts_active_provider_openai_when_key_set(client, admin_token):
    with (
        patch("app.config.settings.ELEVENLABS_API_KEY", None),
        patch("app.config.settings.OPENAI_API_KEY", "sk-test"),
    ):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    data = response.json()
    assert data["tts"]["active_provider"] == "openai"
    assert data["tts"]["default_voice"] == "alloy"


@pytest.mark.asyncio
async def test_tts_active_provider_none_when_nothing_configured(client, admin_token):
    with (
        patch("app.config.settings.ELEVENLABS_API_KEY", None),
        patch("app.config.settings.OPENAI_API_KEY", None),
        patch("app.config.settings.COQUI_TTS_ENABLED", False),
        patch("app.config.settings.EDGE_TTS_ENABLED", False),
    ):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    data = response.json()
    assert data["tts"]["active_provider"] == "none"
    assert data["tts"]["default_voice"] is None


@pytest.mark.asyncio
async def test_tts_elevenlabs_takes_priority(client, admin_token):
    with (
        patch("app.config.settings.ELEVENLABS_API_KEY", "el-key"),
        patch("app.config.settings.OPENAI_API_KEY", "sk-test"),
    ):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    data = response.json()
    assert data["tts"]["active_provider"] == "elevenlabs"


# ---------------------------------------------------------------------------
# Captions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_captions_available_styles_present(client, admin_token):
    response = await client.get(
        "/api/settings/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = response.json()
    styles = data["captions"]["available_styles"]
    assert isinstance(styles, list)
    assert "basic" in styles
    assert "none" in styles


@pytest.mark.asyncio
async def test_captions_whisper_model_size_reflected(client, admin_token):
    with patch("app.config.settings.WHISPER_MODEL_SIZE", "large-v3"):
        response = await client.get(
            "/api/settings/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    data = response.json()
    assert data["captions"]["model_size"] == "large-v3"


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_settings_status_response_shape(client, admin_token):
    response = await client.get(
        "/api/settings/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()

    # Top-level keys
    for key in ("app_name", "environment", "storage_path", "media", "script", "tts", "captions", "providers", "jobs", "feature_flags"):
        assert key in data, f"Missing top-level key: {key}"

    # Providers sub-keys must be booleans
    for pk in ("openai_api_key_present", "pexels_api_key_present", "pixabay_api_key_present",
               "stability_api_key_present", "elevenlabs_api_key_present"):
        assert isinstance(data["providers"][pk], bool), f"providers.{pk} is not bool"
