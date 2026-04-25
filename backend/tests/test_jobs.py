from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_job_requires_auth(client):
    response = await client.post("/api/jobs", json={"title": "Test Job"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_jobs_empty(client, admin_token):
    response = await client.get(
        "/api/jobs",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_create_and_get_job(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    create_resp = await client.post(
        "/api/jobs",
        json={"title": "My Test Job", "dry_run": True},
        headers=headers,
    )
    assert create_resp.status_code == 201
    job = create_resp.json()
    assert job["title"] == "My Test Job"
    assert job["status"] == "pending"
    assert job["dry_run"] is True
    job_id = job["id"]

    get_resp = await client.get(f"/api/jobs/{job_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == job_id


@pytest.mark.asyncio
async def test_job_not_found(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    response = await client.get(
        "/api/jobs/00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_pending_job(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    create_resp = await client.post(
        "/api/jobs",
        json={"title": "Cancel Me", "dry_run": True},
        headers=headers,
    )
    job_id = create_resp.json()["id"]

    cancel_resp = await client.post(f"/api/jobs/{job_id}/cancel", headers=headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"
