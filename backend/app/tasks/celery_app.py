from celery import Celery
from celery.schedules import crontab
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ckdo_dashboard",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.oracle_sync", "app.tasks.report_gen", "app.tasks.eis_etl_tasks", "app.tasks.document_converter_tasks", "app.tasks.document_translation_tasks", "app.tasks.openwebui_sync_tasks", "app.tasks.ap_invoice_gdrive_tasks", "app.tasks.ebs_mart_tasks"],
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
    # Infrastructure snapshots for CoChat's IT tools (tablespace / CPU / disk /
    # Oracle activity). Every 15 min for the same reason as etl-open-pr above:
    # these track live conditions, so a nightly batch would answer yesterday's
    # question. See eis_etl_tasks.etl_it_monitoring.
    "etl-it-monitoring": {"task": "app.tasks.etl_tasks.etl_it_monitoring", "schedule": crontab(minute="*/15")},
    # Daily Sales is refreshed on upload (see _save_store in
    # eis_daily_sales.py); this is the safety net for a dispatch lost because
    # the worker or broker was down, not the primary trigger.
    "etl-daily-sales": {"task": "app.tasks.etl_tasks.etl_daily_sales", "schedule": crontab(minute=20)},
    # EBS Data Mart (CoChat "EBS Analyst" tool server, see
    # app/services/ebs_mart). AP is incremental on a composite watermark, so
    # hourly is cheap; Sunday's full reload is the delete reconciliation.
    # Inventory is a whole on-hand snapshot, so hourly during working hours
    # only. The 00:10 refresh recomputes days_overdue/days_to_expiry for the
    # new day even when no ETL brought new rows.
    "etl-mart-ap": {"task": "app.tasks.etl_tasks.etl_mart_ap", "schedule": crontab(minute=40)},
    "etl-mart-ap-reconcile": {
        "task": "app.tasks.etl_tasks.etl_mart_ap",
        "schedule": crontab(hour=1, minute=0, day_of_week="sunday"),
        "kwargs": {"full_refresh": True},
    },
    "etl-mart-inventory": {"task": "app.tasks.etl_tasks.etl_mart_inventory", "schedule": crontab(minute=50, hour="6-20")},
    "refresh-ebs-marts": {"task": "app.tasks.etl_tasks.refresh_ebs_marts", "schedule": crontab(hour=0, minute=10)},
    # Phase 2. PO/PR hourly like AP (incremental; PR pending is a small full
    # snapshot); Sunday's full reload reconciles deletes. OPM costs change at
    # period close, so once a day is plenty.
    "etl-mart-po": {"task": "app.tasks.etl_tasks.etl_mart_po", "schedule": crontab(minute=25)},
    "etl-mart-po-reconcile": {
        "task": "app.tasks.etl_tasks.etl_mart_po",
        "schedule": crontab(hour=1, minute=30, day_of_week="sunday"),
        "kwargs": {"full_refresh": True},
    },
    "etl-mart-item-cost": {"task": "app.tasks.etl_tasks.etl_mart_item_cost", "schedule": crontab(hour=4, minute=50)},
    # Phase 3: OM and AR hourly (incremental), full reload on Sunday.
    "etl-mart-om": {"task": "app.tasks.etl_tasks.etl_mart_om", "schedule": crontab(minute=10)},
    "etl-mart-om-reconcile": {
        "task": "app.tasks.etl_tasks.etl_mart_om",
        "schedule": crontab(hour=2, minute=0, day_of_week="sunday"),
        "kwargs": {"full_refresh": True},
    },
    "etl-mart-ar": {"task": "app.tasks.etl_tasks.etl_mart_ar", "schedule": crontab(minute=55)},
    # Phase 5: GL hourly (incremental), full reload on Sunday.
    "etl-mart-gl": {"task": "app.tasks.etl_tasks.etl_mart_gl", "schedule": crontab(minute=5)},
    "etl-mart-gl-reconcile": {
        "task": "app.tasks.etl_tasks.etl_mart_gl",
        "schedule": crontab(hour=3, minute=30, day_of_week="sunday"),
        "kwargs": {"full_refresh": True},
    },
    # Phase 4: OPM batches hourly (incremental), full reload on Sunday.
    "etl-mart-opm": {"task": "app.tasks.etl_tasks.etl_mart_opm", "schedule": crontab(minute=35)},
    "etl-mart-opm-reconcile": {
        "task": "app.tasks.etl_tasks.etl_mart_opm",
        "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
        "kwargs": {"full_refresh": True},
    },
    "etl-mart-ar-reconcile": {
        "task": "app.tasks.etl_tasks.etl_mart_ar",
        "schedule": crontab(hour=2, minute=30, day_of_week="sunday"),
        "kwargs": {"full_refresh": True},
    },
    # Nightly reconciliation for CoChat (Open WebUI) Knowledge Sync — the
    # main trigger is event-driven (Setup > AI > Knowledge Base's "Sync to
    # CoChat" button), this just catches anything missed (a doc edited
    # without triggering a manual sync, a CoChat-side hiccup, etc.).
    "openwebui-knowledge-sync": {
        "task": "app.tasks.openwebui_sync_tasks.sync_to_openwebui",
        "schedule": crontab(hour=1, minute=30),
        "kwargs": {"triggered_by": "nightly-scheduler"},
    },
    # AP Autoinvoice — polls each watched Google Drive folder for new PDFs
    # (see ap_invoice_gdrive_service.py). No-ops quickly (is_configured()
    # check) until the service account/Shared Drive are actually set up.
    "ap-invoice-gdrive-sync": {
        "task": "app.tasks.ap_invoice_gdrive_tasks.sync_gdrive_invoices",
        "schedule": crontab(minute="*/10"),
        "kwargs": {"triggered_by": "scheduler"},
    },
}
