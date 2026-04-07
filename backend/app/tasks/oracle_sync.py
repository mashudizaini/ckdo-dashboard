"""
Oracle Sync Tasks — Celery
─────────────────────────────────────────
Background tasks untuk sinkronisasi data dari Oracle EBS ke PostgreSQL.
"""
from app.tasks.celery_app import celery_app
import structlog

logger = structlog.get_logger()


@celery_app.task(bind=True, name="app.tasks.oracle_sync.sync_all")
def sync_all(self):
    """Jalankan semua sync Oracle EBS secara berurutan."""
    logger.info("oracle_sync.sync_all.started")
    # TODO: implementasi sync data Oracle EBS
    logger.info("oracle_sync.sync_all.finished")
    return {"status": "ok"}
