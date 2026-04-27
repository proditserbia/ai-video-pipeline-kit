from __future__ import annotations

from celery import Celery
from celery.signals import worker_ready

from app.config import settings

celery_app = Celery(
    "video_pipeline",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["worker.tasks.video_pipeline", "worker.tasks.scheduled"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_max_retries=settings.MAX_JOB_RETRIES,
    task_default_retry_delay=60,
    result_expires=86400,
    task_routes={
        "worker.tasks.video_pipeline.*": {"queue": "pipeline"},
        "worker.tasks.scheduled.*": {"queue": "scheduled"},
    },
)


@worker_ready.connect
def log_worker_config(**kwargs):
    from worker.modules.tts.selector import log_tts_config
    from worker.modules.stock_media.selector import log_media_config
    log_tts_config()
    log_media_config()
