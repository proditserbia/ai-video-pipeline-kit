from __future__ import annotations

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


# Configure periodic schedule (example)
celery_app.conf.beat_schedule = {
    "discover-trends-hourly": {
        "task": "worker.tasks.scheduled.discover_trends",
        "schedule": 3600.0,
    },
}
