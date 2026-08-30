"""Celery application: broker and result backend are Redis."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "feedback_analyzer",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
