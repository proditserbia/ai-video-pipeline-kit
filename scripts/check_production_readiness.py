#!/usr/bin/env python3
"""
AI Video Pipeline Kit — Production Readiness Check
====================================================

Usage (from repo root or backend/):
    python scripts/check_production_readiness.py

Checks each service/dependency and prints a PASS / WARN / FAIL table.
Exits with status 0 when no FAILs are present, 1 otherwise.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Locate repo root & make backend importable ─────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent          # scripts/
_REPO_ROOT = _SCRIPT_DIR.parent                        # repo root
_BACKEND = _REPO_ROOT / "backend"

if _BACKEND.is_dir() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# pydantic-settings reads .env relative to CWD; point it at the repo root so
# docker/local setups with a root-level .env file both work.
if (_REPO_ROOT / ".env").exists():
    os.chdir(_REPO_ROOT)
elif (_BACKEND / ".env").exists():
    os.chdir(_BACKEND)


# ── Colour helpers ──────────────────────────────────────────────────────────

_USE_COLOUR = sys.stdout.isatty()

_COLOUR = {
    "PASS": "\033[32m",  # green
    "WARN": "\033[33m",  # yellow
    "FAIL": "\033[31m",  # red
    "RESET": "\033[0m",
}


def _c(text: str, key: str) -> str:
    if not _USE_COLOUR:
        return text
    return f"{_COLOUR.get(key, '')}{text}{_COLOUR['RESET']}"


# ── Result model ────────────────────────────────────────────────────────────

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class CheckResult:
    name: str
    status: str  # PASS / WARN / FAIL
    detail: str = ""


# ── Individual checks ────────────────────────────────────────────────────────


def _check_postgres(s: Any) -> CheckResult:
    """Attempt a real TCP connect + simple query via psycopg2."""
    try:
        import psycopg2  # noqa: PLC0415

        # SYNC_DATABASE_URL looks like postgresql+psycopg2://…
        dsn = s.SYNC_DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://", 1)
        conn = psycopg2.connect(dsn, connect_timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT current_database()")
        (db_name,) = cur.fetchone()
        conn.close()
        return CheckResult("PostgreSQL connection", PASS, f"Connected (db={db_name})")
    except Exception as exc:
        return CheckResult("PostgreSQL connection", FAIL, str(exc))


def _check_redis(s: Any) -> CheckResult:
    """Ping the Redis instance."""
    try:
        import redis as redis_lib  # noqa: PLC0415

        r = redis_lib.from_url(s.REDIS_URL, socket_connect_timeout=5)
        r.ping()
        return CheckResult("Redis connection", PASS, s.REDIS_URL)
    except Exception as exc:
        return CheckResult("Redis connection", FAIL, str(exc))


def _check_ffmpeg() -> CheckResult:
    path = shutil.which("ffmpeg")
    if path:
        return CheckResult("FFmpeg installed", PASS, path)
    return CheckResult("FFmpeg installed", FAIL, "ffmpeg not found on PATH")


def _check_ffprobe() -> CheckResult:
    path = shutil.which("ffprobe")
    if path:
        return CheckResult("ffprobe installed", PASS, path)
    return CheckResult("ffprobe installed", FAIL, "ffprobe not found on PATH")


def _check_tts(s: Any) -> CheckResult:
    providers: list[str] = []
    if s.EDGE_TTS_ENABLED:
        providers.append("edge-tts")
    if s.ELEVENLABS_API_KEY:
        providers.append("elevenlabs")
    if s.OPENAI_API_KEY:
        providers.append("openai-tts")
    if s.COQUI_TTS_ENABLED:
        providers.append("coqui")

    if providers:
        return CheckResult(
            "TTS provider configured", PASS, ", ".join(providers)
        )
    return CheckResult(
        "TTS provider configured",
        WARN,
        "No TTS provider enabled — set EDGE_TTS_ENABLED=true or supply an API key",
    )


def _check_stock_media(s: Any) -> CheckResult:
    providers: list[str] = []
    if s.PEXELS_API_KEY:
        providers.append("Pexels")
    if s.PIXABAY_API_KEY:
        providers.append("Pixabay")

    local_assets = Path(s.STORAGE_PATH) / "assets"
    local_count = 0
    if local_assets.is_dir():
        local_count = sum(
            1
            for f in local_assets.iterdir()
            if f.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"}
        )
    if local_count:
        providers.append(f"local ({local_count} video files)")

    if providers:
        return CheckResult(
            "Stock media provider", PASS, ", ".join(providers)
        )
    return CheckResult(
        "Stock media provider",
        WARN,
        "No API keys and no local video assets — placeholder clips will be used",
    )


def _check_storage(s: Any) -> CheckResult:
    outputs = Path(s.STORAGE_PATH) / "outputs"
    try:
        outputs.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(dir=outputs, delete=True)
        tmp.close()
        return CheckResult("Output storage writable", PASS, str(outputs))
    except Exception as exc:
        return CheckResult("Output storage writable", FAIL, str(exc))


def _check_whisper(s: Any) -> CheckResult:
    if not s.WHISPER_ENABLED:
        return CheckResult(
            "Whisper / captions",
            WARN,
            "WHISPER_ENABLED=false — captions will be skipped for all jobs",
        )
    try:
        from worker.modules.captions.whisper_provider import (  # noqa: PLC0415
            WhisperCaptionProvider,
            _check_faster_whisper,
        )

        err = _check_faster_whisper()
        if err:
            return CheckResult(
                "Whisper / captions",
                WARN,
                f"faster-whisper unavailable — {err.splitlines()[0]}",
            )
        return CheckResult(
            "Whisper / captions",
            PASS,
            f"faster-whisper available (model={s.WHISPER_MODEL_SIZE}, device={s.WHISPER_DEVICE})",
        )
    except Exception as exc:
        return CheckResult("Whisper / captions", WARN, str(exc))


def _check_secret_key(s: Any) -> CheckResult:
    defaults = {
        "changeme-secret-key-at-least-32-chars-long",
        "changeme",
        "change_me_in_production_min_32_chars_!!",
        "secret",
    }
    key = s.SECRET_KEY or ""
    if key in defaults or key.lower().startswith("changeme") or len(key) < 32:
        return CheckResult(
            "SECRET_KEY changed",
            FAIL,
            "Still using a default/weak value — run: openssl rand -hex 32",
        )
    return CheckResult("SECRET_KEY changed", PASS, "Custom key set (length OK)")


def _check_next_public_api_url() -> CheckResult:
    """Read NEXT_PUBLIC_API_URL from the environment (or .env files)."""
    url = os.environ.get("NEXT_PUBLIC_API_URL", "")
    if not url:
        # Try reading .env manually for this frontend-only variable
        for env_path in [_REPO_ROOT / ".env", _BACKEND / ".env"]:
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("NEXT_PUBLIC_API_URL="):
                        url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            if url:
                break

    if not url:
        return CheckResult(
            "NEXT_PUBLIC_API_URL",
            WARN,
            "Not set — frontend will use its built-in default",
        )
    defaults = {"http://localhost:8000", "http://localhost:8000/api/v1"}
    if url.rstrip("/") in defaults or "localhost" in url:
        return CheckResult(
            "NEXT_PUBLIC_API_URL",
            WARN,
            f"Looks like a local/dev URL: {url}",
        )
    return CheckResult("NEXT_PUBLIC_API_URL", PASS, url)


# ── Table renderer ───────────────────────────────────────────────────────────

_COL_NAME = 34
_COL_STATUS = 6
_COL_DETAIL = 50


def _render(results: list[CheckResult]) -> None:
    width = _COL_NAME + _COL_STATUS + _COL_DETAIL + 6
    bar = "─" * width

    print()
    print(_c("╔" + "═" * (width - 2) + "╗", "RESET"))
    title = "AI Video Pipeline Kit — Production Readiness Check"
    pad = width - 2 - len(title)
    print(_c("║ " + title + " " * (pad - 1) + "║", "RESET"))
    print(_c("╚" + "═" * (width - 2) + "╝", "RESET"))
    print()

    hdr = f"  {'CHECK':<{_COL_NAME}} {'STATUS':<{_COL_STATUS}}  DETAIL"
    print(hdr)
    print(bar)

    for r in results:
        coloured_status = _c(f"{r.status:<{_COL_STATUS}}", r.status)
        # Truncate detail to fit terminal nicely
        detail = r.detail if len(r.detail) <= _COL_DETAIL else r.detail[:_COL_DETAIL - 1] + "…"
        print(f"  {r.name:<{_COL_NAME}} {coloured_status}  {detail}")

    print(bar)

    n_fail = sum(1 for r in results if r.status == FAIL)
    n_warn = sum(1 for r in results if r.status == WARN)
    n_pass = sum(1 for r in results if r.status == PASS)

    summary_parts = []
    if n_fail:
        summary_parts.append(_c(f"{n_fail} FAIL", FAIL))
    if n_warn:
        summary_parts.append(_c(f"{n_warn} WARN", WARN))
    summary_parts.append(_c(f"{n_pass} PASS", PASS))
    print(f"\n  RESULT: {', '.join(summary_parts)}\n")


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    try:
        from app.config import settings  # noqa: PLC0415
    except Exception as exc:
        print(f"[ERROR] Could not import app.config.settings: {exc}", file=sys.stderr)
        print(
            "  Make sure you run this script from the repo root or that the\n"
            "  backend/ directory is on PYTHONPATH.\n"
            "  Example: cd /path/to/ai-video-pipeline-kit && python scripts/check_production_readiness.py",
            file=sys.stderr,
        )
        return 1

    results: list[CheckResult] = [
        _check_postgres(settings),
        _check_redis(settings),
        _check_ffmpeg(),
        _check_ffprobe(),
        _check_tts(settings),
        _check_stock_media(settings),
        _check_storage(settings),
        _check_whisper(settings),
        _check_secret_key(settings),
        _check_next_public_api_url(),
    ]

    _render(results)

    return 1 if any(r.status == FAIL for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
