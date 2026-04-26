from __future__ import annotations

import shutil
import time
from pathlib import Path

import structlog

from worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="worker.tasks.scheduled.discover_trends")
def discover_trends() -> dict:
    """Scheduled task: discover trending topics and persist to DB."""
    from app.config import settings
    from app.core.feature_flags import FeatureFlags
    from app.database import SyncSessionLocal
    from app.models.topic import Topic

    if not FeatureFlags().is_enabled("trends"):
        return {"skipped": True, "reason": "trends feature disabled"}

    db = SyncSessionLocal()()
    created = 0
    try:
        providers = []
        try:
            from worker.modules.trends.google_trends import GoogleTrendsProvider
            providers.append(GoogleTrendsProvider())
        except Exception:
            pass
        try:
            from worker.modules.trends.rss_provider import RSSProvider
            providers.append(RSSProvider())
        except Exception:
            pass

        for provider in providers:
            try:
                results = provider.fetch(keyword=None, limit=5)
                for item in results:
                    topic = Topic(
                        title=item.title,
                        description=item.description,
                        source=item.source,
                        score=item.score,
                        keywords=item.keywords,
                    )
                    db.add(topic)
                    created += 1
            except Exception as exc:
                logger.warning("trend_provider_failed", error=str(exc))

        db.commit()
        logger.info("trends_discovered", count=created)
        return {"created": created}
    finally:
        db.close()


@celery_app.task(name="worker.tasks.scheduled.cleanup_temp_dirs")
def cleanup_temp_dirs(max_age_seconds: int = 86400) -> dict:
    """Scheduled task: remove temp job work directories older than *max_age_seconds*.

    The default age threshold is 24 hours (86 400 s).  Stale directories are
    those whose ``mtime`` is older than ``now - max_age_seconds``.  Directories
    that cannot be removed (e.g. permission errors) are counted as failures and
    logged as warnings so that the task never causes the beat loop to crash.

    Returns a summary dict: ``{"removed": int, "failed": int, "skipped": int}``.
    """
    from app.config import settings

    temp_root = Path(settings.STORAGE_PATH) / "temp"
    if not temp_root.exists():
        logger.info("cleanup_temp_dirs_skipped", reason="temp_root_not_found", path=str(temp_root))
        return {"removed": 0, "failed": 0, "skipped": 0}

    cutoff = time.time() - max_age_seconds
    removed = failed = skipped = 0

    for entry in temp_root.iterdir():
        if not entry.is_dir():
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            skipped += 1
            continue

        if mtime >= cutoff:
            skipped += 1
            continue

        try:
            shutil.rmtree(entry)
            removed += 1
            logger.info("temp_dir_removed", path=str(entry))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("temp_dir_remove_failed", path=str(entry), error=str(exc))

    logger.info(
        "cleanup_temp_dirs_done",
        removed=removed,
        failed=failed,
        skipped=skipped,
        max_age_seconds=max_age_seconds,
    )
    return {"removed": removed, "failed": failed, "skipped": skipped}



celery_app.conf.beat_schedule = {
    "discover-trends-hourly": {
        "task": "worker.tasks.scheduled.discover_trends",
        "schedule": 3600.0,
    },
    "cleanup-temp-dirs-hourly": {
        "task": "worker.tasks.scheduled.cleanup_temp_dirs",
        "schedule": 3600.0,
    },
}
