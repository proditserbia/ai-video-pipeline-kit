from __future__ import annotations

import io
import pytest


@pytest.mark.asyncio
async def test_upload_asset_requires_auth(client):
    data = {"file": ("test.jpg", io.BytesIO(b"fake-image-data"), "image/jpeg")}
    response = await client.post("/api/assets/upload", files=data)
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_upload_asset_returns_201(client, admin_token, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.STORAGE_PATH", str(tmp_path))

    headers = {"Authorization": f"Bearer {admin_token}"}
    data = {"file": ("photo.jpg", io.BytesIO(b"\xff\xd8\xff" + b"0" * 100), "image/jpeg")}
    response = await client.post("/api/assets/upload", files=data, headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "photo.jpg"
    assert body["name"] == "photo.jpg"
    assert body["asset_type"] == "image"
    assert body["file_type"] == "jpg"
    assert body["file_size"] > 0
    assert body["source"] == "local"
    assert "id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_list_assets_empty(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await client.get("/api/assets", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "size" in body
    assert "pages" in body
    assert isinstance(body["items"], list)


@pytest.mark.asyncio
async def test_list_assets_includes_uploaded_asset(client, admin_token, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.STORAGE_PATH", str(tmp_path))

    headers = {"Authorization": f"Bearer {admin_token}"}

    # Upload an asset
    data = {"file": ("clip.mp4", io.BytesIO(b"fake-video-data"), "video/mp4")}
    upload_resp = await client.post("/api/assets/upload", files=data, headers=headers)
    assert upload_resp.status_code == 201
    uploaded_id = upload_resp.json()["id"]

    # List assets — the uploaded asset must appear
    list_resp = await client.get("/api/assets", headers=headers)
    assert list_resp.status_code == 200
    body = list_resp.json()
    ids = [item["id"] for item in body["items"]]
    assert uploaded_id in ids


@pytest.mark.asyncio
async def test_list_assets_filtered_by_asset_type(client, admin_token, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.STORAGE_PATH", str(tmp_path))

    headers = {"Authorization": f"Bearer {admin_token}"}

    # Upload a video asset
    video_data = {"file": ("movie.mp4", io.BytesIO(b"fake-video"), "video/mp4")}
    video_resp = await client.post("/api/assets/upload", files=video_data, headers=headers)
    assert video_resp.status_code == 201

    # Upload an image asset
    image_data = {"file": ("pic.png", io.BytesIO(b"fake-image"), "image/png")}
    image_resp = await client.post("/api/assets/upload", files=image_data, headers=headers)
    assert image_resp.status_code == 201

    # Filter by video only
    list_resp = await client.get("/api/assets?asset_type=video", headers=headers)
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert all(item["asset_type"] == "video" for item in items)


@pytest.mark.asyncio
async def test_upload_asset_disallowed_extension(client, admin_token, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.STORAGE_PATH", str(tmp_path))

    headers = {"Authorization": f"Bearer {admin_token}"}
    data = {"file": ("script.sh", io.BytesIO(b"#!/bin/bash"), "text/plain")}
    response = await client.post("/api/assets/upload", files=data, headers=headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_asset(client, admin_token, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.STORAGE_PATH", str(tmp_path))

    headers = {"Authorization": f"Bearer {admin_token}"}

    # Upload
    data = {"file": ("to_delete.jpg", io.BytesIO(b"data"), "image/jpeg")}
    upload_resp = await client.post("/api/assets/upload", files=data, headers=headers)
    assert upload_resp.status_code == 201
    asset_id = upload_resp.json()["id"]

    # Delete
    del_resp = await client.delete(f"/api/assets/{asset_id}", headers=headers)
    assert del_resp.status_code == 204

    # No longer in list
    list_resp = await client.get("/api/assets", headers=headers)
    ids = [item["id"] for item in list_resp.json()["items"]]
    assert asset_id not in ids
