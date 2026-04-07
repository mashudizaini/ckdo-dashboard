from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ckdo_dashboard",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.oracle_sync", "app.tasks.report_gen"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Jakarta",
    enable_utc=True,
    task_track_started=True,
)
