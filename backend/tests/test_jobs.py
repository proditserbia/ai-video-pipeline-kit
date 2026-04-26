from __future__ import annotations

import os
import tempfile

import pytest


@pytest.mark.asyncio
async def test_create_job_requires_auth(client):
    response = await client.post("/api/jobs", json={"title": "Test Job"})
    assert response.status_code == 401


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


# ---------------------------------------------------------------------------
# Download endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_download_valid_returns_200(client, admin_token, session_factory):
    """A completed job whose output file exists returns 200 with video/mp4."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Create a job
    create_resp = await client.post(
        "/api/jobs",
        json={"title": "Download Test", "dry_run": True},
        headers=headers,
    )
    assert create_resp.status_code == 201
    job_id = create_resp.json()["id"]

    # Write a real temp file so FileResponse can serve it, and patch STORAGE_PATH
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_mp4 = os.path.join(tmpdir, "output.mp4")
        with open(fake_mp4, "wb") as f:
            f.write(b"\x00" * 16)

        # Patch the output_path on the job row and STORAGE_PATH in settings
        from sqlalchemy import select, update
        from app.models.job import Job
        from app.config import settings as app_settings

        original_storage = app_settings.STORAGE_PATH
        app_settings.STORAGE_PATH = tmpdir
        try:
            async with session_factory() as db:
                await db.execute(
                    update(Job).where(Job.id == job_id).values(output_path=fake_mp4)
                )
                await db.commit()

            resp = await client.get(
                f"/api/v1/jobs/{job_id}/download",
                headers=headers,
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("video/mp4")
        finally:
            app_settings.STORAGE_PATH = original_storage


@pytest.mark.asyncio
async def test_download_missing_file_returns_404(client, admin_token, session_factory):
    """A job whose output_path points to a non-existent file returns 404."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    create_resp = await client.post(
        "/api/jobs",
        json={"title": "Missing File", "dry_run": True},
        headers=headers,
    )
    job_id = create_resp.json()["id"]

    with tempfile.TemporaryDirectory() as tmpdir:
        nonexistent = os.path.join(tmpdir, "ghost.mp4")

        from sqlalchemy import update
        from app.models.job import Job
        from app.config import settings as app_settings

        original_storage = app_settings.STORAGE_PATH
        app_settings.STORAGE_PATH = tmpdir
        try:
            async with session_factory() as db:
                await db.execute(
                    update(Job).where(Job.id == job_id).values(output_path=nonexistent)
                )
                await db.commit()

            resp = await client.get(
                f"/api/v1/jobs/{job_id}/download",
                headers=headers,
            )
            assert resp.status_code == 404
        finally:
            app_settings.STORAGE_PATH = original_storage


@pytest.mark.asyncio
async def test_download_unauthorized_user_cannot_access(client, session_factory):
    """A second user cannot download a job owned by the first user."""
    from app.core.security import hash_password, create_access_token
    from app.models.user import User
    from sqlalchemy import select

    # Create a second user and get their token
    async with session_factory() as db:
        result = await db.execute(select(User).where(User.email == "other@example.com"))
        other_user = result.scalar_one_or_none()
        if not other_user:
            other_user = User(
                email="other@example.com",
                hashed_password=hash_password("otherpass"),
                is_active=True,
            )
            db.add(other_user)
            await db.commit()
            await db.refresh(other_user)
        other_token = create_access_token(subject=other_user.id)

    # Create a job as the first (admin) user
    from app.core.security import create_access_token as cat
    async with session_factory() as db:
        result = await db.execute(select(User).where(User.email == "test@example.com"))
        admin_user = result.scalar_one_or_none()
    admin_token = cat(subject=admin_user.id)

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    create_resp = await client.post(
        "/api/jobs",
        json={"title": "Owner Job", "dry_run": True},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    job_id = create_resp.json()["id"]

    # Try to download as the second user
    other_headers = {"Authorization": f"Bearer {other_token}"}
    resp = await client.get(f"/api/v1/jobs/{job_id}/download", headers=other_headers)
    assert resp.status_code == 404  # job not found for this user (ownership check)

