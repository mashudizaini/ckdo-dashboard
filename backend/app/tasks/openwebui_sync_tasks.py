"""
Open WebUI (CoChat) Knowledge Sync — background task.

Runs run_full_sync() in the Celery worker rather than inline in the HTTP
request: live-verified that CoChat's own file-registration call
(files/batch/add, where it actually embeds a file into the collection)
can take several minutes per document on this instance — far past any
reasonable request/response window. Progress/result is written to
openwebui_sync_log (plain psycopg2) — the status endpoint polls that
table, not Celery's own result backend, same convention as
document_converter_tasks.py.
"""
from app.tasks.celery_app import celery_app
from app.services import openwebui_sync_service as svc


@celery_app.task(name="app.tasks.openwebui_sync_tasks.sync_to_openwebui")
def sync_to_openwebui_task(triggered_by: str = "scheduler"):
    return svc.run_full_sync(triggered_by)
