"""
Document Converter — Translation background task. Same DB-row-polled
status pattern as document_converter_tasks.py (the UI polls
document_conversion_jobs directly, not Celery's own result backend).
Runs after a conversion job is already `done` — reads its stored
`extracted_blocks`, never re-runs OCR, so translating to a different
target/provider (or re-translating after a glossary correction) doesn't
cost another conversion pass.
"""
import asyncio
import logging

import psycopg2
import psycopg2.extras

from app.config import get_settings
from app.tasks.celery_app import celery_app

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


def _fetch_glossary(pg) -> list:
    cur = pg.cursor()
    cur.execute("SELECT source_term, target_en, target_id, notes FROM document_glossary_terms")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetch_blocks(pg, job_id: int):
    cur = pg.cursor()
    cur.execute("SELECT extracted_blocks FROM document_conversion_jobs WHERE id = %s", (job_id,))
    row = cur.fetchone()
    return row[0] if row else None


@celery_app.task(name="app.tasks.document_translation_tasks.translate_document")
def translate_document_task(job_id: int, target: str, provider: str, api_key: str = None):
    """target: "en" | "id" | "both". api_key: the calling user's own saved
    key for `provider` if they have one, resolved by the router before
    dispatch (same convention as meeting_notes.py) — None falls back to
    the shared company key inside document_translation_service, or is
    simply unused for provider="onprem"."""
    from app.services.document_translation_service import translate_blocks

    pg = _get_pg()
    try:
        _update(pg, job_id, translate_status="processing", translate_error=None)
        blocks = _fetch_blocks(pg, job_id)
        if not blocks:
            raise ValueError("No extracted content on this job yet — conversion may still be running or failed.")
        glossary = _fetch_glossary(pg)

        targets = ["en", "id"] if target == "both" else [target]
        fields = {"translate_provider": provider}
        warnings = []
        for t in targets:
            translated, qa = asyncio.run(translate_blocks(blocks, t, provider, api_key, glossary))
            fields[f"translated_{t}"] = psycopg2.extras.Json(translated)
            warnings.extend({**w, "target": t} for w in qa)

        fields["translate_qa_warnings"] = psycopg2.extras.Json(warnings)
        fields["translate_status"] = "done"
        _update(pg, job_id, **fields)
        logger.info(f"[document_translation] job {job_id} done ({target}/{provider}, {len(warnings)} QA warnings)")

    except Exception as e:
        logger.error(f"[document_translation] job {job_id} failed: {e}")
        _update(pg, job_id, translate_status="error", translate_error=str(e))
        raise
    finally:
        pg.close()
