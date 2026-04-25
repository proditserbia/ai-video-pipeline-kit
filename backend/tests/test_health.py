from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_returns_200(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "features" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_includes_feature_flags(client):
    response = await client.get("/health")
    features = response.json()["features"]
    assert isinstance(features, dict)
    assert "core_video" in features
    assert "tts" in features
