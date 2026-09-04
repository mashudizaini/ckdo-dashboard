from celery import Celery
from celery.schedules import crontab
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ckdo_dashboard",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.oracle_sync", "app.tasks.report_gen", "app.tasks.eis_etl_tasks", "app.tasks.document_converter_tasks", "app.tasks.document_translation_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Jakarta",
    enable_utc=True,
    task_track_started=True,
)

# EIS ETL schedule — ckdo-dashboard-v2 is the sole scheduler for these jobs
# (migrated off the standalone eis-dashboard-v2 app's own celery beat, which
# only ever ran 6 of these 9 and is now retired for ETL duty). Times match
# the cadence already declared in it_etl_admin.py's _JOB_META.
celery_app.conf.beat_schedule = {
    "etl-sales":      {"task": "app.tasks.etl_tasks.etl_sales",      "schedule": crontab(hour=2, minute=0)},
    "etl-cogs":       {"task": "app.tasks.etl_tasks.etl_cogs",       "schedule": crontab(hour=2, minute=15)},
    "etl-ar-ap":      {"task": "app.tasks.etl_tasks.etl_ar_ap",      "schedule": crontab(hour=2, minute=30)},
    "etl-inventory":  {"task": "app.tasks.etl_tasks.etl_inventory",  "schedule": crontab(hour=3, minute=0)},
    "etl-production": {"task": "app.tasks.etl_tasks.etl_production", "schedule": crontab(hour=3, minute=15)},
    "etl-employee":   {"task": "app.tasks.etl_tasks.etl_employee",   "schedule": crontab(hour=2, minute=0, day_of_week="monday")},
    "etl-financial":  {"task": "app.tasks.etl_tasks.etl_financial",  "schedule": crontab(hour=4, minute=0)},
    "etl-budget":     {"task": "app.tasks.etl_tasks.etl_budget",     "schedule": crontab(hour=4, minute=30)},
    "etl-po":         {"task": "app.tasks.etl_tasks.etl_po",         "schedule": crontab(hour=5, minute=0)},
    "etl-po-lines":   {"task": "app.tasks.etl_tasks.etl_po_lines",   "schedule": crontab(hour=5, minute=15)},
    # Every 15 min, not daily — "open" status changes throughout the day;
    # see etl_open_pr's own docstring for why this one can't be a daily
    # batch like everything else here.
    "etl-open-pr":    {"task": "app.tasks.etl_tasks.etl_open_pr",    "schedule": crontab(minute="*/15")},
    "etl-sales-orders": {"task": "app.tasks.etl_tasks.etl_sales_orders", "schedule": crontab(hour=5, minute=30)},
    "etl-inventory-txn": {"task": "app.tasks.etl_tasks.etl_inventory_txn", "schedule": crontab(hour=5, minute=45)},
    "etl-batches": {"task": "app.tasks.etl_tasks.etl_batches", "schedule": crontab(hour=6, minute=0)},
}
