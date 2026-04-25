from __future__ import annotations

import shutil
from pathlib import Path

from app.config import settings


def safe_storage_path(relative: str) -> Path:
    """Resolve a relative path inside STORAGE_PATH, raising ValueError on traversal."""
    base = Path(settings.STORAGE_PATH).resolve()
    target = (base / relative).resolve()
    target.relative_to(base)  # raises ValueError if outside base
    return target


def copy_to_output(src: Path, dest_rel: str) -> Path:
    dest = safe_storage_path(dest_rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest
