from app.tasks.celery_app import celery_app
from app.services import ap_invoice_gdrive_service as svc


@celery_app.task(name="app.tasks.ap_invoice_gdrive_tasks.sync_gdrive_invoices")
def sync_gdrive_invoices_task(triggered_by: str = "scheduler"):
    return svc.sync_all(triggered_by)
