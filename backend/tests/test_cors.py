"""Tests for production-safe CORS configuration.

The CORS_ALLOWED_ORIGINS setting must restrict cross-origin access to the
configured origins only. The test verifies that:
  - an allowed origin receives Access-Control-Allow-Origin in the response
  - a disallowed origin does not receive that header
  - the wildcard ("*") is never used as the reflected origin
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


ALLOWED_ORIGIN = "https://avpk.prodit.rs"
DISALLOWED_ORIGIN = "https://evil.example.com"


@pytest.fixture()
def cors_app():
    """Return the FastAPI application with CORS_ALLOWED_ORIGINS patched to a
    known value so the test is independent of the local .env file."""
    from app.config import settings as app_settings
    original = app_settings.CORS_ALLOWED_ORIGINS
    app_settings.CORS_ALLOWED_ORIGINS = [ALLOWED_ORIGIN]

    from app.main import create_app
    _app = create_app()

    yield _app

    app_settings.CORS_ALLOWED_ORIGINS = original


@pytest.mark.asyncio
async def test_allowed_origin_receives_cors_header(cors_app):
    """A preflight request from the allowed origin must echo that origin back."""
    async with AsyncClient(
        transport=ASGITransport(app=cors_app),
        base_url="http://test",
    ) as ac:
        response = await ac.options(
            "/api/v1/health",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )

    acao = response.headers.get("access-control-allow-origin", "")
    assert acao == ALLOWED_ORIGIN, (
        f"Expected Access-Control-Allow-Origin: {ALLOWED_ORIGIN!r}, got {acao!r}"
    )


@pytest.mark.asyncio
async def test_disallowed_origin_does_not_receive_cors_header(cors_app):
    """A preflight request from a disallowed origin must not receive the ACAO header."""
    async with AsyncClient(
        transport=ASGITransport(app=cors_app),
        base_url="http://test",
    ) as ac:
        response = await ac.options(
            "/api/v1/health",
            headers={
                "Origin": DISALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )

    acao = response.headers.get("access-control-allow-origin", "")
    assert acao != DISALLOWED_ORIGIN, (
        f"Disallowed origin {DISALLOWED_ORIGIN!r} should not be reflected in ACAO header"
    )


@pytest.mark.asyncio
async def test_wildcard_never_used_as_reflected_origin(cors_app):
    """The server must never reflect '*' as the Access-Control-Allow-Origin value."""
    async with AsyncClient(
        transport=ASGITransport(app=cors_app),
        base_url="http://test",
    ) as ac:
        response = await ac.options(
            "/api/v1/health",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )

    acao = response.headers.get("access-control-allow-origin", "")
    assert acao != "*", "CORS must not use wildcard '*' — use explicit origins"


@pytest.mark.asyncio
async def test_cors_origins_config_default_excludes_wildcard():
    """The default CORS_ALLOWED_ORIGINS must not contain '*'."""
    from app.config import Settings
    defaults = Settings()
    assert "*" not in defaults.CORS_ALLOWED_ORIGINS, (
        "Default CORS_ALLOWED_ORIGINS must not contain '*'"
    )
    assert ALLOWED_ORIGIN in defaults.CORS_ALLOWED_ORIGINS, (
        f"Default CORS_ALLOWED_ORIGINS must contain the production origin {ALLOWED_ORIGIN!r}"
    )
