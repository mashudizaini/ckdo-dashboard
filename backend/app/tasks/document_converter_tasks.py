"""
Document Converter background task — runs the (slow, ~73s/page) docling
conversion in the Celery worker instead of inline in a request/SSE stream,
so it survives the browser tab closing or the user's session expiring.
Progress is written directly to document_conversion_jobs (plain psycopg2,
same pattern as eis_etl_tasks.py's _log_start/_log_end) rather than through
Celery's own result backend, since the admin UI polls that table — not
Celery's AsyncResult — for status/progress, exactly like eis_etl_admin.py
polls eis.etl_job_log instead of asking Celery directly.
"""
import os
import logging
import psycopg2
import psycopg2.extras
from app.tasks.celery_app import celery_app
from app.config import get_settings
from app.services.document_converter_service import build_converter, extract_blocks, render_markdown_from_blocks

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_pg():
    return psycopg2.connect(settings.database_url)


def _update(pg, job_id: int, **fields):
    if not fields:
        return
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    cur = pg.cursor()
    cur.execute(
        f"UPDATE document_conversion_jobs SET {set_clause}, updated_at = NOW() WHERE id = %s",
        (*fields.values(), job_id),
    )
    pg.commit()


@celery_app.task(name="app.tasks.document_converter_tasks.convert_document")
def convert_document_task(job_id: int, file_path: str, ext: str, language: str = "auto"):
    pg = _get_pg()
    try:
        _update(pg, job_id, status="processing", status_message="Starting…")
        converter = build_converter(language)

        if ext == ".pdf":
            import fitz
            doc = fitz.open(file_path)
            total = len(doc)
            _update(pg, job_id, total_pages=total)

            blocks = []
            for i in range(total):
                _update(
                    pg, job_id,
                    current_page=i + 1,
                    progress_percent=round(i / total * 100),
                    status_message=f"Processing page {i + 1} of {total}…",
                )
                page_pdf_path = f"{file_path}.page{i + 1}.pdf"
                single_doc = fitz.open()
                single_doc.insert_pdf(doc, from_page=i, to_page=i)
                single_doc.save(page_pdf_path)
                single_doc.close()
                try:
                    blocks.extend(extract_blocks(converter, page_pdf_path))
                finally:
                    if os.path.exists(page_pdf_path):
                        os.remove(page_pdf_path)
                _update(pg, job_id, progress_percent=round((i + 1) / total * 100))
            doc.close()
        else:
            _update(pg, job_id, total_pages=1, current_page=1, status_message="Processing document…")
            blocks = extract_blocks(converter, file_path)
            _update(pg, job_id, progress_percent=100)

        markdown = render_markdown_from_blocks(blocks)
        _update(
            pg, job_id, status="done", progress_percent=100, status_message="Done",
            markdown=markdown, extracted_blocks=psycopg2.extras.Json(blocks),
        )
        logger.info(f"[document_converter] job {job_id} done ({len(markdown)} chars, {len(blocks)} blocks)")

    except Exception as e:
        logger.error(f"[document_converter] job {job_id} failed: {e}")
        _update(pg, job_id, status="error", error_message=str(e), status_message="Failed")
        raise
    finally:
        pg.close()
        if os.path.exists(file_path):
            os.remove(file_path)
