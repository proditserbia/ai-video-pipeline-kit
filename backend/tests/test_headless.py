from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


def test_headless_auto_mode_minimal():
    from app.schemas.headless import HeadlessJobCreate, HeadlessMode

    job = HeadlessJobCreate(
        mode=HeadlessMode.auto,
        title="Auto Test",
        script={"topic": "quantum computing"},
    )
    assert job.mode == HeadlessMode.auto
    data = job.to_input_data()
    assert data["headless"] is True
    assert data["mode"] == "auto"
    assert data["script"]["topic"] == "quantum computing"


def test_headless_auto_mode_requires_topic():
    from pydantic import ValidationError
    from app.schemas.headless import HeadlessJobCreate, HeadlessMode

    with pytest.raises(ValidationError, match="topic"):
        HeadlessJobCreate(
            mode=HeadlessMode.auto,
            title="No Topic",
            script={"text": None, "topic": None},
        )


def test_headless_full_control_mode():
    from app.schemas.headless import HeadlessJobCreate, HeadlessMode, CaptionStyle

    job = HeadlessJobCreate(
        mode=HeadlessMode.full_control,
        title="Full Control",
        script={"text": "This is my script.", "duration_seconds": 60},
        caption={"enabled": True, "style": CaptionStyle.bold},
        video={"background_music": True, "background_music_volume": 0.2},
    )
    assert job.caption.style == CaptionStyle.bold
    data = job.to_input_data()
    assert data["caption"]["style"] == "bold"
    assert data["video"]["background_music"] is True


def test_headless_semi_auto_mode():
    from app.schemas.headless import HeadlessJobCreate, HeadlessMode

    job = HeadlessJobCreate(
        mode=HeadlessMode.semi_auto,
        title="Semi Auto",
        script={"topic": "standing desks", "tone": "conversational"},
        voice={"provider": "edge_tts", "voice_id": "en-US-GuyNeural", "rate": "+5%"},
    )
    assert job.voice.voice_id == "en-US-GuyNeural"


def test_headless_defaults_are_sensible():
    from app.schemas.headless import HeadlessJobCreate, HeadlessMode

    job = HeadlessJobCreate(
        mode=HeadlessMode.auto,
        title="Defaults",
        script={"topic": "AI news"},
    )
    assert job.voice.provider.value == "edge_tts"
    assert job.caption.enabled is True
    assert job.upload.destinations[0].value == "local"
    assert job.dry_run is False
    assert job.max_retries == 3


def test_template_job_create_schema():
    from app.schemas.headless import TemplateJobCreate

    t = TemplateJobCreate(
        template_id="quick_explainer",
        props={"topic": "Rust programming language"},
    )
    assert t.template_id == "quick_explainer"
    assert t.props["topic"] == "Rust programming language"


# ---------------------------------------------------------------------------
# Template engine tests
# ---------------------------------------------------------------------------


def test_render_quick_explainer():
    from app.api.templates import render_template

    result = render_template(
        "quick_explainer",
        {"topic": "How does AI work", "tone": "educational"},
    )
    assert "How does AI work" in result["title"]
    assert result["script"]["topic"] == "How does AI work"
    assert result["script"]["tone"] == "educational"


def test_render_uses_default_for_optional_prop():
    from app.api.templates import render_template

    result = render_template("quick_explainer", {"topic": "Test topic"})
    # tone defaults to "educational"
    assert result["script"]["tone"] == "educational"


def test_render_missing_required_prop_raises():
    from app.api.templates import render_template

    with pytest.raises(ValueError, match="Missing required props"):
        render_template("quick_explainer", {})


def test_render_unknown_template_raises():
    from app.api.templates import render_template

    with pytest.raises(ValueError, match="Unknown template"):
        render_template("does_not_exist", {})


def test_render_product_review():
    from app.api.templates import render_template

    result = render_template(
        "product_review",
        {
            "product_name": "AirPods Pro",
            "pros": "great sound",
            "cons": "expensive",
        },
    )
    assert "AirPods Pro" in result["title"]


def test_list_templates():
    from app.api.templates import list_templates

    templates = list_templates()
    ids = [t["id"] for t in templates]
    assert "quick_explainer" in ids
    assert "product_review" in ids
    assert "news_summary" in ids
    assert "tutorial" in ids
    assert "story_hook" in ids


def test_get_template_returns_none_for_unknown():
    from app.api.templates import get_template

    assert get_template("nonexistent") is None


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_headless_job_requires_auth(client):
    response = await client.post(
        "/api/v1/headless/jobs",
        json={
            "mode": "auto",
            "title": "Unauth",
            "script": {"topic": "test"},
        },
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_headless_job_auto_mode(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await client.post(
        "/api/v1/headless/jobs",
        json={
            "mode": "auto",
            "title": "Headless Auto Job",
            "script": {"topic": "Python tips for beginners"},
            "dry_run": True,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["mode"] == "auto"
    assert data["dry_run"] is True
    assert "poll_url" in data
    assert "logs_url" in data


@pytest.mark.asyncio
async def test_create_headless_job_full_control(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await client.post(
        "/api/v1/headless/jobs",
        json={
            "mode": "full_control",
            "title": "Full Control Job",
            "script": {"text": "Hello world script.", "duration_seconds": 30},
            "voice": {"provider": "edge_tts", "voice_id": "en-US-JennyNeural"},
            "caption": {"enabled": True, "style": "basic"},
            "video": {"background_music": False},
            "upload": {"destinations": ["local"]},
            "dry_run": True,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["mode"] == "full_control"


@pytest.mark.asyncio
async def test_create_headless_job_validation_error(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    # auto mode without topic should fail validation
    resp = await client.post(
        "/api/v1/headless/jobs",
        json={
            "mode": "auto",
            "title": "Bad Job",
            "script": {},  # no topic, no text
        },
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_job_from_template(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await client.post(
        "/api/v1/headless/jobs/from-template",
        json={
            "template_id": "quick_explainer",
            "props": {"topic": "How GPUs work"},
            "dry_run": True,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "How GPUs work" in data["title"]


@pytest.mark.asyncio
async def test_create_job_from_unknown_template(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await client.post(
        "/api/v1/headless/jobs/from-template",
        json={
            "template_id": "nonexistent_template",
            "props": {},
        },
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_templates_endpoint(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await client.get("/api/v1/headless/templates", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = [t["id"] for t in data]
    assert "quick_explainer" in ids


@pytest.mark.asyncio
async def test_get_single_template(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await client.get("/api/v1/headless/templates/quick_explainer", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "quick_explainer"
    assert "required_props" in data
    assert "topic" in data["required_props"]


@pytest.mark.asyncio
async def test_get_unknown_template_404(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await client.get("/api/v1/headless/templates/does_not_exist", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_examples(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = await client.get("/api/v1/headless/examples", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "auto" in data
    assert "semi_auto" in data
    assert "full_control" in data
    assert "template" in data
    assert "dry_run" in data
