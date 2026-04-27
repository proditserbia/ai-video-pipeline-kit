#!/usr/bin/env python3
"""
Pexels API diagnostic tool
===========================

Verifies that PEXELS_API_KEY is configured and downloads at least one video
result for the given search query.

Usage (from repo root):
    python scripts/test_pexels.py "nature"
    python scripts/test_pexels.py "city skyline" --count 3

Exit codes:
    0 – at least one clip downloaded successfully
    1 – configuration error or no clips returned
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# ── Bootstrap: make backend/ importable ────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent   # scripts/
_REPO_ROOT = _SCRIPT_DIR.parent                 # repo root
_BACKEND = _REPO_ROOT / "backend"

if _BACKEND.is_dir() and str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Point pydantic-settings at the root-level .env file if it exists.
import os
if (_REPO_ROOT / ".env").exists():
    os.chdir(_REPO_ROOT)
elif (_BACKEND / ".env").exists():
    os.chdir(_BACKEND)

# ── Colour helpers ──────────────────────────────────────────────────────────

_USE_COLOUR = sys.stdout.isatty()
_C = {
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "reset": "\033[0m",
}


def _c(text: str, colour: str) -> str:
    if not _USE_COLOUR:
        return text
    return f"{_C.get(colour, '')}{text}{_C['reset']}"


def _ok(msg: str) -> None:
    print(f"  {_c('✓', 'green')} {msg}")


def _warn(msg: str) -> None:
    print(f"  {_c('!', 'yellow')} {msg}")


def _fail(msg: str) -> None:
    print(f"  {_c('✗', 'red')} {msg}")


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test Pexels API key and video search.",
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="nature",
        help="Search query (default: 'nature')",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        metavar="N",
        help="Number of clips to fetch (default: 1)",
    )
    args = parser.parse_args()

    print()
    print("Pexels API Diagnostic")
    print("─" * 40)

    # 1. Load settings
    try:
        from app.config import settings  # noqa: PLC0415
    except Exception as exc:
        _fail(f"Could not import app.config.settings: {exc}")
        print(
            "\n  Make sure you run this script from the repo root:\n"
            "    python scripts/test_pexels.py \"nature\"\n",
            file=sys.stderr,
        )
        return 1

    # 2. Check key
    if not settings.PEXELS_API_KEY:
        _fail("PEXELS_API_KEY is not set.")
        print(
            "\n  Add it to your .env file:\n"
            "    PEXELS_API_KEY=your_key_here\n"
            "\n  Get a free API key at https://www.pexels.com/api/\n",
        )
        return 1
    _ok(f"PEXELS_API_KEY is set (length={len(settings.PEXELS_API_KEY)})")

    # 3. Run fetch
    print(f"\n  Searching Pexels for: {args.query!r}  (count={args.count})")
    with tempfile.TemporaryDirectory(prefix="pexels_test_") as tmp:
        try:
            from worker.modules.stock_media.pexels_provider import PexelsProvider  # noqa: PLC0415

            provider = PexelsProvider()
            assets = provider.fetch(args.query, args.count, tmp)
        except Exception as exc:
            _fail(f"PexelsProvider raised an unexpected error: {exc}")
            return 1

        if not assets:
            _fail("Pexels returned no clips. Check your API key and query.")
            _warn("Rate limit: free tier allows 200 requests/hour and 20,000/month.")
            return 1

        _ok(f"{len(assets)} clip(s) downloaded successfully:")
        for asset in assets:
            size_kb = Path(asset.path).stat().st_size // 1024
            print(
                f"    • {Path(asset.path).name}"
                f"  ({asset.width}×{asset.height}, {asset.duration:.1f}s, {size_kb} KB)"
            )

    print()
    _ok("Pexels integration is working correctly.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
