"""
Report Generation Tasks — Celery
─────────────────────────────────────────
Background tasks untuk generate laporan PDF / Excel.
"""
from app.tasks.celery_app import celery_app
import structlog

logger = structlog.get_logger()


@celery_app.task(bind=True, name="app.tasks.report_gen.generate_report")
def generate_report(self, report_type: str, params: dict):
    """Generate laporan berdasarkan tipe dan parameter yang diberikan."""
    logger.info("report_gen.generate_report.started", report_type=report_type)
    # TODO: implementasi generate report
    logger.info("report_gen.generate_report.finished", report_type=report_type)
    return {"status": "ok", "report_type": report_type}
